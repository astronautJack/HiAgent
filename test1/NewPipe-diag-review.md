# /diag 报告审阅 — NewPipe 夜间启动崩溃

> 审阅对象：`NewPipe-diag-report.md`  
> 对照：issue [#13508](https://github.com/TeamNewPipe/NewPipe/issues/13508)（已关闭，标 regression）+ 修复 PR [#13524](https://github.com/TeamNewPipe/NewPipe/pull/13524)  
> 审阅方式：读源码 + 日志验真 + 对照 maintainer 修复，未跑 diag

## 总体结论

**定位对了，根因机制和修复建议判错了。**

diag 流程成功把崩溃定位到正确代码（`Localization.resolvePrettyTime` → `App.onCreate`），与 issue 标的 regression 范围吻合——这部分能力是真的。但报告对**根因机制**和**修复**的结论与 maintainer 的实际修复相悖：报告把「已在仓内的修复」当成了「不足的缺陷」。

## 对照 maintainer 评阅 / 修复（关键）

PR #13524「proguard-rules: Keep resource **classes** for prettytime」（@theimpulson，@TobiGr 2026-05-22 合入 dev），全量 diff 就 3 行加在 `app/proguard-rules.pro` 末尾：

```pro
# See https://github.com/TeamNewPipe/NewPipe/issues/13508
-keep class org.ocpsoft.prettytime.i18n.Resources* { *; }
```

对照当前代码（已核实）：

| 报告说法 | 实际（核实 + maintainer） | 裁决 |
|---|---|---|
| 缺陷点 `proguard-rules.pro:59` 的 keep 规则「只 keep 类，未保留 `Resources*.properties` 资源束」→ 不足 | maintainer 的修复**就是**这条 keep 类规则（PR #13524 标题「Keep resource **classes**」）；prettytime i18n 是 `ListResourceBundle` **类**，不是 `.properties` | ❌ 报告误判 |
| 修建议改用 `keep.xml` 引用 `org/ocpsoft/prettytime/i18n/*` 或禁用 prettytime 资源剥离 | 修复就是 `-keep class ...Resources* { *; }`，已在 `proguard-rules.pro:59`；maintainer 认为其**充分** | ❌ 报告在解一个不存在的问题 |
| 该 keep 规则是「缺陷点」 | 该规则是**修复**（PR #13524 合入），崩溃的 nightly 1143（05-17）早于合入（05-22） | ❌ 把修复当缺陷 |

**结论**：报告没识别出 `proguard-rules.pro:58-59`（带 `# See #13508` 注释）就是 maintainer 为本 issue 打的补丁。正确结论应是「**修复已在仓内，崩溃 nightly 早于修复，建议重新构建验证**」，而非「规则不足、需另改」。

## 报告正确之处（已验真）

- **崩溃识别**：`RuntimeException: Unable to create application` + `Caused by: MissingResourceException: Can't find bundle ...prettytime.i18n.Resources, locale en_US` ✅
- **触发点 `Localization.java:379`** = `return new PrettyTime(getAppLocale());`（核实一致）✅
- **调用入口 `App.kt:104`** = `Localization.initPrettyTime(Localization.resolvePrettyTime())`（核实一致）✅
- **CRG 反向回溯**：`callers_of resolvePrettyTime` → `App.onCreate`（confidence=EXTRACTED）✅
- **次要崩溃**（ExoPlayer OOM 无 NewPipe 源帧 / 动画 OOM）一并列出 ✅

## 审阅疑点

### 1. 根因机制误判（主要）
报告断言「R8 `shrinkResources` 剥离了 prettytime 的 i18n `ResourceBundle` `.properties` 文件」。但：
- maintainer PR 标题是「Keep resource **classes**」——prettytime i18n 是 `ListResourceBundle` 子类（类），不是 `.properties`。
- `shrinkResources`（aapt）剥离的是 Android `res/` 资源，不剥离 JAR 内 classloader `.properties`；真正剥离类的是 R8 minify。
- 报告把机制说成「`.properties` 被 shrinkResources 剥」，与实际「类被 R8 剥」不符。

### 2. 未识别「修复已在仓内」（主要）
`proguard-rules.pro:58` 的 `# See #13508` 注释 + `:59` 的 keep 规则，正是 PR #13524 的修复。报告读到这条规则却判定「不足」，没意识到它就是 fix。应在报告中加「**fix-already-present** 检测」：缺陷点旁若引用了本 issue 号的注释，优先判定为已修复，再验证是否充分。

### 3. `claimed_error` 误报
digest 的 `claimed_error` = `buffers: main,system,crash,events,kernel`——这是 logcat 的缓冲区元数据行，只因含 `crash`（缓冲区名）被通用 error-keyword 启发式命中，并非真实异常。真实错误应是 `RuntimeException`/`MissingResourceException`。code-tracer 靠 cluster（`#30`/`#33`）兜回来了，但 `claimed_error` 字段本身是假阳性。

### 4. R8 混淆行→源码行 映射未验证
报告写「混淆行 7 = 源码 Localization.java:379」「混淆行 489 = 源码 App.kt:104」。源码行（379/104）经 Grep 核实正确，但「混淆行 → 源码行」的映射**未引用 mapping.txt**——这是 R8 重编号行号的反推，没有对应 `r8-map-id` 的 mapping 文件无法证实。属断言，应标注为「推断」而非「已证」。

### 5. `MissingResourceException` 计数不符
报告称「`MissingResourceException` × 12」。实际 grep 计数 = **24**（`Unable to create application` × 12 属实）。12 与 24 不一致（可能 12 次崩溃 × 每次异常出现 2 处 = 24）。报告应写明计数口径。

## 对 HiAgent 项目的改进建议（基于本次实测）

| 问题 | 改进点 | 落点 |
|---|---|---|
| `claimed_error` 命中 logcat `buffers:` 元数据（含 `crash`） | 关键词权重：`FATAL EXCEPTION`/`Caused by`/`Exception:`/`Error` 栈行优先于裸关键词；过滤已知 logcat 元数据行 | log-parser（`~/.logscope/config.json` 的 `error_keywords` 或 claimed_error 启发式） |
| 把「修复」当「缺陷」 | 加 **fix-already-present** 检测：缺陷点旁若注释引用 issue 号 / `# See` / `# Fix`，先判为已修复，再验证充分性 | code-tracer（回溯时读缺陷点上下文注释） |
| R8 行映射当事实 | 混淆行→源码行若无 mapping.txt，标注「推断（符号 Grep 定位方法，非反混淆）」 | code-tracer（证据链措辞） |
| 未对照 issue tracker | code-tracer 可选：用 issue 号反查仓内是否已有修复 PR/注释 | code-tracer（新增可选步骤） |

## 验证清单（人审确认）

- [ ] `proguard-rules.pro:58-59` 是否即 PR #13524 的修复（已核实：是）
- [ ] 当前 dev 分支 HEAD 是否晚于 2026-05-22（含修复）；崩溃 nightly 1143（05-17）是否早于修复（issue 时间线支持）
- [ ] prettytime 5.0.8 i18n 是类还是 `.properties`（PR 标题「classes」+ `-keep class` 语义支持「类」；可解 jar 确认）
- [ ] 重新构建（带 `proguard-rules.pro:59` 规则）后启动是否还崩——若不崩，证实「修复已在仓内，nightly 早于修复」结论
- [ ] `Localization.java:379` / `App.kt:104` 核实（已核实：一致）
- [ ] `claimed_error` 假阳性复核（已核实：`buffers:` 行含 `crash`）

## 一句话裁决

定位能力可信（找到对的代码行），但**根因机制和修复建议应改写**：根因是 R8 剥离了 prettytime i18n **类**（非 `.properties` 被 shrinkResources 剥），修复 `-keep class ...Resources*` 已在 `proguard-rules.pro:59`（PR #13524），崩溃 nightly 早于修复——报告把修复误判为缺陷，这是本次最主要的偏差。
