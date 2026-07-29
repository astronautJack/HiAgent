# NewPipe 启动崩溃定位报告（MissingResourceException）

> 用例：`/diag`（log-parser → wiki-reader → code-tracer critic 循环 → 报告）
> 日志：`log/NewPipe.nightly.log.d0cba707e674.txt`
> 代码仓：`codebase/NewPipe`
> 生成时间：2026-07-29

## 1. 结果摘要

| 字段 | 值 |
|---|---|
| **根因文件** | `app/src/main/java/org/schabi/newpipe/util/Localization.java` |
| **根因行** | **379** — `return new PrettyTime(getAppLocale());` |
| **触发点** | `app/src/main/java/org/schabi/newpipe/App.kt:104` — `Localization.initPrettyTime(Localization.resolvePrettyTime())` |
| **置信度** | **high（证据链闭合）** |
| **claimed_error** | `java.util.MissingResourceException: Can't find bundle for base name org.ocpsoft.prettytime.i18n.Resources, locale en_US` → `RuntimeException: Unable to create application org.schabi.newpipe.App` |

## 2. 证据链（反向回溯）

1. **症状**：05-17 启动崩溃 **3 次**（PID 20985 @04:25、22792 @04:44:38、22907 @04:44:51），每次栈完全一致 → 硬启动崩溃、可复现。
2. **栈顶（第三方）**：`ResourceBundle.getBundle("org.ocpsoft.prettytime.i18n.Resources", en_US)` 抛 `MissingResourceException` —— APK 中缺少 PrettyTime 的 `en_US`（及 fallback `en`）i18n 资源 bundle。
3. **本仓帧①（根因行）**：`Localization.resolvePrettyTime` `Localization.java:379` `new PrettyTime(getAppLocale())` 构造时触发 bundle 加载。CRG `callers_of` 确认该函数节点存在（`Localization.java::resolvePrettyTime`，378–380）。
4. **本仓帧②（触发链）**：`App.onCreate` `App.kt:104` 调用 `resolvePrettyTime()`。CRG 边 `App.onCreate → resolvePrettyTime`（line 104，confidence 1.0 EXTRACTED）与栈一致。
5. **locale 确证**：崩溃前一行（log:933）`Configuration: Updating configuration, locales updated from [] to [en_US]` —— `getAppLocale()` 返回 `en_US`，闭合。
6. **依赖来源**：`app/build.gradle.kts:299` `implementation(libs.ocpsoft.prettytime)`。

> 注：栈中 `:489`/`:7` 为 R8 混淆行号（r8-map-id），函数名未混淆，源码真实行号由 CRG + 源码读取对齐为 104 / 379。

## 3. digest_preview

- `line_count=1929 / fed=1928 / cluster_count=106`
- `claimed_error: null`（工具未自动断言；人工判读 FATAL 簇为根因）
- `new_cluster_ids: []`（无新簇，已知模板）
- **关键簇**：
  - #30 `RuntimeException: Unable to create application org.schabi.newpipe.App`(18)
  - #33 `MissingResourceException ...prettytime.i18n.Resources en_US`(18)
  - #75 / #107 `FATAL EXCEPTION: main`(49/29)
- 另见 #11 早期 `OutOfMemoryError: ExoPlayer:Playback`(05-13，10) —— 独立次要问题，非本次启动崩溃根因。

## 4. 根因结论

`Localization.java:379` 的 `new PrettyTime(getAppLocale())` 在 `en_US` 下加载 PrettyTime i18n `Resources` bundle 失败（bundle 未打入 APK，疑似 R8 shrinking 移除 `.properties` 或库版本/locale fallback 缺失），异常上抛致 `App.onCreate` 启动失败。

## 5. 修复方向（供人审）

1. **容错降级**：在 `Localization.java:379` 包 try/catch，加载失败时回退默认 `PrettyTime`（无 locale）或返回 null 并在调用方处理。
2. **保留资源**：在打包规则（ProGuard/R8 keep）中显式保留 `org/ocpsoft/prettytime/i18n/**` 资源，防止 shrinking 移除 `.properties`。
3. **locale fallback**：改用不受影响的 locale，或在 `getAppLocale()` 返回的 locale 无对应 bundle 时回退到 `Locale.ROOT`。

## 6. 人审 checkpoint

本报告为定位阶段产物，**未做任何代码改动**。批准后可进入修复阶段。
