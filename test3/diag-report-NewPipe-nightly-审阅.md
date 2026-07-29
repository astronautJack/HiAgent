# test3 /diag 报告审阅 — NewPipe nightly（改进版 P1.11 实测）

> 审阅对象：`diag-report-NewPipe-nightly.md`（test3，修复前 NewPipe，改进版 code-tracer + 独立 reviewer + loop）  
> 对照：4 条改进（确定源/实证/链到构建配置）+ 独立 reviewer + 已知答案 PR [#13524](https://github.com/TeamNewPipe/NewPipe/pull/13524)  
> 审阅方式：读报告 + 源码/日志验真（test3 NewPipe pre-fix，Localization.java:379 / App.kt:104 / build.gradle.kts:84-85 已验）  
> 注：`/diag` 职责是**定位 bug**（根因 file:line + 机制 + 证据链），**修 bug 是另一 workflow**——故报告里修复建议偏简是预期，不在本审阅苛责范围。本审阅只评「定位」质量。

## 总体结论

**定位准、证据闭合——改进版的「确定源 + 不臆断类型」两条落地；但根因机制点名（R8 shrinking）和构建开关引用两条仍欠，独立 reviewer 没拦住。**

报告把崩溃定位到正确代码行（Localization.java:379 / App.kt:104），证据链日志帧→CRG 边→源码行逐环闭合，confidence=high 合理。计数用 cluster.size、不臆断资源类型——这是改进版的进步。但根因机制只 hedge 成「资源未正确打包/缺失」，没点名 R8 shrinking，也没引 `build.gradle.kts:84-85` 的 minify/shrink 开关；reviewer 本该对这两条判 revise，却放行了（无 `## 存疑点`）。

## 已核实正确（读源码 + 日志验真）

| 项 | 报告值 | 核实 |
|---|---|---|
| 根因行 | `Localization.java:379` = `return new PrettyTime(getAppLocale());` | ✅ 一致 |
| 触发入口 | `App.kt:104` = `Localization.initPrettyTime(Localization.resolvePrettyTime())` | ✅ 一致 |
| 证据链 | 日志帧 → CRG `callers_of/callees_of` 边 → 源码行，逐环对应 | ✅ 闭合 |
| 计数来源 | `cluster 30/33 size 18`、`#9 (20×)`、`#11 (13×)`——来自 digest cluster.size | ✅ 确定源，无臆造 |
| 资源类型 | 「i18n Resources 资源包失败」未断言 `.properties` | ✅ 不臆断（hedge） |

## 定位维度的审阅（仅评 /diag 职责内）

### ✅ 落地：确定源（计数用 cluster.size）
报告引「cluster 30/33，size 18」——计数来自 digest 的 cluster.size，无手挑 PID、无臆造计数。

### ⚠️ 部分落地：实证/hedge（类型不臆断 ✓，机制点名 ✗）
- **类型不臆断**：报告未断言 `.properties`，改为 hedge「资源包失败/缺失」——避了类型臆断，好。
- **但机制也一并模糊**：根因只说「资源未正确打包/缺失」，**没点名 R8 shrinking**（minify+shrink 剥离 i18n 类）。对 /diag 而言，「为什么缺」是定位根因的一部分——机制该点名（R8 shrinking 剥了类），hedge 是兜底不是默认。报告 hedge 过度，丢了机制。
- 注：prettytime i18n 是类（ListResourceBundle）还是 .properties，本仓未构建无法解 jar 实证；但「R8 shrinking 剥离」这个机制可从 `build.gradle.kts:84-85` 开关 + `MissingResourceException` 推出，不必靠解 jar。

### ❌ 未落地：链到构建配置（漏 minify/shrink 开关）
报告**未引** `build.gradle.kts:84-85` 的 `isMinifyEnabled=true` / `isShrinkResources=true`（实测在，已核实）——这两个开关正是启用 R8 shrinking 的根因环节。根因链缺「构建开关启用 shrinking」一环，只泛泛说「gradle 配置」。对 /diag，根因在构建配置时，引其行是定位的应有环节。

## 独立 reviewer 的表现（关键）

报告**无 `## 存疑点` 段** → reviewer 判 `verdict="pass"` 放行。但定位质量有两处欠（机制没点名 R8 shrinking + 漏构建开关），reviewer **没拦住**。

- reviewer 应把「根因机制是否点名（非纯 hedge）」+「根因涉剥离时是否引构建开关」作 **hard 验证项**——缺则 `verdict="revise"` 打回。
- 当前 reviewer 放行了机制模糊 + 漏开关的报告，说明这两条验证不够硬。
- （注：修复建议是否具体**不在** reviewer 验证范围——修 bug 是另一 workflow，/diag 不负责给确切修复规则。）

## 对照已知答案（PR #13524）

| 答案要素 | test3 报告 | 裁决 |
|---|---|---|
| 根因机制：R8 shrinking（minify+shrink）剥 i18n 类 | 「资源未正确打包/缺失」（hedge，未点名 R8） | ⚠️ 机制模糊 |
| 构建开关：`build.gradle.kts:84-85` | 未引 | ❌ 漏 |
| file:line：Localization.java:379 / App.kt:104 | ✅ 正确 | ✅ |
| 证据链闭合 | ✅ 逐环对应 | ✅ |

理想定位结论应是「R8 shrinking（开关 84-85）剥了 prettytime i18n 类 → `getBundle` 失败 → 崩在 Localization.java:379」——test3 给准了 file:line + 证据链，但机制只 hedge 到「资源缺失」，没点名 R8 shrinking + 开关。

## 对 HiAgent 项目的建议（基于本次）

| 问题 | 改进 | 落点 |
|---|---|---|
| reviewer 放行机制模糊的报告 | reviewer hard 验证项加：「根因机制不能纯 hedge——能从构建开关+依赖+异常推出时要点名（如 R8 shrinking），否则 verdict=revise」 | code-tracer-reviewer.md |
| reviewer 没强制构建开关 | reviewer 加：「根因涉剥离/资源缺失时，报告必须引构建开关（minify/shrink/keep）行，否则 verdict=revise」 | code-tracer-reviewer.md |
| code-tracer hedge 过度 | code-tracer 原则补：「hedge 是兜底非默认——能从构建开关+依赖推出机制时点名（R8 shrinking），别全 hedge」 | code-tracer.md |

## 验证清单（人审确认）

- [ ] Localization.java:379 / App.kt:104（已核实：一致）
- [ ] build.gradle.kts:84-85 构建开关（已核实：minify+shrink 开；报告未引）
- [ ] cluster.size 引用（已核实：18，来自 digest，无臆造）
- [ ] 报告无 `## 存疑点` → reviewer 判 pass（已核实：放行了机制模糊+漏开关的报告）
- [ ] 报告是否点名 R8 shrinking 机制（已核实：未点名，只 hedge「资源缺失」）

## 一句话裁决

**定位准（file:line + 证据链闭合），但根因机制只 hedge 没点名（R8 shrinking）+ 漏构建开关，reviewer 没拦住。** 改进版「确定源 + 不臆断类型」见效；下一步把 reviewer 的「机制点名」和「构建开关」做成 hard 验证项，并让 code-tracer 别过度 hedge（能推出机制就点名）。修 bug 建议简略是 /diag 的预期边界，不在苛责范围。
