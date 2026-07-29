# /diag 定位报告 — NewPipe 夜间日志启动崩溃

> **置信度：高** · 编排：CRG 全量建图（5975 节点）→ log-parser 压日志（1929 行 → 107 簇）→ 无 wiki（跳过，退回源码）→ code-tracer 反向回溯，证据链 1 次自审通过

## 结论

App 启动即崩，根因是 **R8 `shrinkResources` 剥离了 prettytime 的 i18n `ResourceBundle` `.properties` 文件**，导致运行期 `ResourceBundle.getBundle` 找不到 en_US 束。该崩溃在日志中确定性重复 **12 次**（`Unable to create application` × 12，`MissingResourceException` × 12），是阻断 App 启动的首要缺陷。

## 根因定位（file:line）

| 角色 | 文件:行 | 代码 / 说明 |
|---|---|---|
| **缺陷点（打包配置）** | `app/proguard-rules.pro:59` | `-keep class org.ocpsoft.prettytime.i18n.Resources* { *; }` — 只 keep **类**，未保留 `Resources*.properties` 资源束 |
| **构建开关** | `app/build.gradle.kts:78-79` | `isMinifyEnabled = true` + `isShrinkResources = true`（R8 资源剥离启用） |
| **触发点** | `app/src/main/java/org/schabi/newpipe/util/Localization.java:379` | `return new PrettyTime(getAppLocale());` — 用 en_US 构造 PrettyTime，内部 `ResourceBundle.getBundle(...)` 找不到束 |
| **调用入口** | `app/src/main/java/org/schabi/newpipe/App.kt:104` | `Localization.initPrettyTime(Localization.resolvePrettyTime())`（在 `App.onCreate` 内，App.kt:78-127） |

## 证据链（症状 → 源码 → 图，闭合）

1. 日志 `:937` — `RuntimeException: Unable to create application org.schabi.newpipe.App`
2. 日志 `:949` — `Caused by: java.util.MissingResourceException: Can't find bundle for base name org.ocpsoft.prettytime.i18n.Resources, locale en_US`
3. 日志 `:955-957` — prettytime 内部 `ResourcesTimeFormat.setLocale$1 → PrettyTime.addUnit → PrettyTime.<init>`
4. 日志 `:958` — `at org.schabi.newpipe.util.Localization.resolvePrettyTime(r8-map-id…:7)`（混淆行 7 = 源码 Localization.java:379）
5. 日志 `:959` — `at org.schabi.newpipe.App.onCreate(r8-map-id…:489)`（混淆行 489 = 源码 App.kt:104）
6. 源码 `Localization.java:379` 证实 `new PrettyTime(getAppLocale())`
7. 源码 `App.kt:104` 证实启动期调用
8. **CRG 反向回溯**（callers_of `resolvePrettyTime`）：`App.onCreate (App.kt:104)` → `resolvePrettyTime`，confidence=EXTRACTED；另一定位器 `MainActivity.onResume (MainActivity.java:519)` 也会触发（本次崩溃是启动期路径）
9. 依赖确认：`org.ocpsoft.prettytime:prettytime:5.0.8.Final`（`gradle/libs.versions.toml:54,160`，`app/build.gradle.kts:309`）
10. 缺陷点证实：`proguard-rules.pro:58` 注释引用 issue #13508，说明此前已知有问题但 keep 规则不足 —— R8 `shrinkResources` 会剥离 `Resources*.properties`，导致运行期 `ResourceBundle` 找不到 en_US 束

## digest

- **claimed_error**：`buffers: main,system,crash,events,kernel`
- **digest_preview**：1929 行 → 107 簇。首要新见簇：
  - `#30` (size 9) — `RuntimeException: Unable to create application org.schabi.newpipe.App`
  - `#33` (size 9) — `Caused by: MissingResourceException: Can't find bundle ... prettytime.i18n.Resources, locale en_US`
  - `#9` (size 14) — `FATAL EXCEPTION: ExoPlayer:Playback`
  - `#11` (size 5) — `OutOfMemoryError`
  - `#75` / `#96` / `#107` (各 size 24) — 重复的 `ActivityThread.-$$Nest$mhandleBindApplication` 崩溃堆栈

## 次要崩溃（非本报告首要根因，供人审一并知晓）

### ExoPlayer OOM
- 位置：日志 `:11`, `:54`，cluster `#9` / `#11`，重复 2 次
- 栈：`OutOfMemoryError` at `Pair.create` → `AbstractConcatenatedTimeline.getConcatenatedUid` → `ExoPlayerImplInternal.updatePlaybackPositions`
- 栈帧全在 `com.google.android.exoplayer2.*` 库内，无 `org.schabi.newpipe` 源帧 —— 属库内 OOM / 内存压力，非 NewPipe 源码可直接定位点
- 建议：另起排查（concat timeline 在大播放列表下的内存放大）

### 动画 OOM
- 位置：日志 `:72`，cluster `#14`
- 栈：`org.schabi.newpipe.ktx.ViewUtils$$ExternalSyntheticLambda0.onAnimationUpdate(:17)` 触发 `Float.valueOf` OOM
- 有 NewPipe 帧，属内存压力性偶发，非确定性根因

## 修复建议（供人审决策，不自动改）

- 修 `app/proguard-rules.pro`：保留 prettytime 资源束。可用 `-keep` 不够时改用 AGP `keep.xml` 引用 `org/ocpsoft/prettytime/i18n/*` 或禁用对 prettytime 包的资源剥离；或升级 prettytime / 用其 Android 适配。
- 修后回归：启动后 `App.onCreate` 不再抛 `MissingResourceException`，12 次重复崩溃应清零。

---

## 附录：编排过程

| 步骤 | 动作 | 产出 |
|---|---|---|
| 1 | CRG 新鲜度门 | 图缺失 → 全量 build（5975 节点） |
| 2 | log-parser 压日志 | 1929 行 → 107 簇 digest |
| 3 | wiki-reader | 仓无 wiki → 跳过，退回源码 |
| 4 | code-tracer 反向回溯 | 沿 callers_of `resolvePrettyTime` 回溯，证据链闭合 |
| 5 | critic 自审 | 第 1 次循环通过，未进 2/3 次 |
| 6 | 报告 | 交人审 checkpoint |

*输入参数：日志 `/home/dlrow_hl/HiAgent_test/test1/log/NewPipe.nightly.log.d0cba707e674.txt`，代码仓 `/home/dlrow_hl/HiAgent_test/test1/codebase/NewPipe`*
