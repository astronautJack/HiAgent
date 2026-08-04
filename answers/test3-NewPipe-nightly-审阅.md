# test3 /diag 报告审阅 — NewPipe nightly（改进版 P1.11 实测）

> 审阅对象：`diag-report-NewPipe-nightly.md`（test3，修复前 NewPipe，改进版 code-tracer + 独立 reviewer + loop）  
> 审阅方式：读报告 + 源码/日志验真（test3 NewPipe pre-fix，Localization.java:379 / App.kt:104 / build.gradle.kts:84-85 已验）  
> 注：`/diag` 职责是**定位 bug**（根因 file:line + 机制 + 证据链），**修 bug 是另一 workflow**——修复建议简略是预期边界，不在苛责范围。本审阅只评「定位」质量。

## 总体结论（已据执行 agent 的反驳重校准）

**报告定位准、证据闭合——是一份合格的 /diag 产出。** 早期审阅对它的几条苛责（机制没点名 R8、漏构建开关、reviewer 没拦）经复核站不住，撤回如下。唯一留的温和改进：纯 hedge 可补一句 R8 minification 候选更可操作，但属锦上添花，非失分项。

## 已核实正确

| 项 | 报告值 | 核实 |
|---|---|---|
| 根因行 | `Localization.java:379` = `return new PrettyTime(getAppLocale());` | ✅ 一致 |
| 触发入口 | `App.kt:104` = `Localization.initPrettyTime(Localization.resolvePrettyTime())` | ✅ 一致 |
| 证据链 | 日志帧 → CRG `callers_of/callees_of` 边 → 源码行，逐环对应 | ✅ 闭合 |
| 计数来源 | `cluster 30/33 size 18`——来自 digest cluster.size | ✅ 确定源，无臆造 |
| claimed_error=null 诚实处理 | digest 无显式 claimed_error，报告自选最可回溯的 FATAL 簇为主根因 | ✅ 合理 |

## 撤回的苛责（经执行 agent 反驳复核）

1. **「机制没点名 R8 shrinking = 失分」——撤（hindsight + 双标）**  
   早期拿 PR #13524 当已知答案倒推「理想结论」罚报告，是 hindsight grading，对 /diag 不公——/diag 输入只有 log+CRG+源码行。且**类型（class/.properties）本仓未构建无法解 jar 实证，是未定的；机制（minify 剥类 vs shrink 剥 .properties）正依赖该未定类型**。类型未定→hedge 算合理；机制（同证据层级、依赖未定类型）→hedge 也该同等合理。早期对同层不确定的两件事给相反裁决（类型 hedge 赞、机制 hedge 罚），是双标，撤。

2. **「漏 build.gradle.kts:84-85 构建开关 = 失分」——撤（越权）**  
   CRG call graph 不索引 `.kts`/`.pro`（tree-sitter 不当代码节点）。要 code-tracer 伸手到 build config 是合理**改进建议**，但提成「缺则失分」是把边界外期望当核心硬门槛，越权。报告不引构建开关不构成定位失分。

3. **「reviewer 没拦住 = 失职」——撤**  
   reviewer 放行一份「file:line 准 + 证据链闭合 + 计数来自 digest + 机制 hedge 合理（因依赖项类型本身就未实证）」的报告，是**正确履职**，非失职。早期判其失职站不住。

> 附：早期审阅自身「理想机制」也不够精确——写「minify+shrink 剥类」，但 isShrinkResources 剥的是 res/ 资源不剥 Java 类，剥 ListResourceBundle 类的是 R8 minification；且俩都在 release block（line 79）内、仅 release/nightly 生效，未标「仅 release」。拿自身不精的机制当标尺罚报告，底气不足。

## 唯一保留的温和改进（非失分）

报告根因写「i18n Resources 资源包失败——属库资源未正确打包 / 该 locale 资源缺失」纯 hedge。**从 `build.gradle.kts:84-85`（minify+shrink on，release block）+ 无 prettytime keep + `MissingResourceException` 可推出「R8 shrinking 剥了 prettytime i18n bundle」这一候选机制**——报告可补一句候选（不必写死类型/具体步骤），更可操作。但这是锦上添花，不点名也不影响「定位」成立。

## 这次实测引出的设计修正（已据此重切职责）

本次 regression（test2 本有点名 R8，test3 hedge 过度反而丢了）根因是——**hedge 规则塞在 code-tracer 提示词里，让它自我审查、一刀切全 hedge**。修正方向（已在 code-tracer/reviewer 落地）：
- **hedge 不归 code-tracer**——code-tracer 只管 assertive 定位（提能推出的机制候选，不憋着）；事实/逻辑核验归 reviewer。
- **reviewer = 事实+逻辑守门**：claim 是假/逻辑断才 revise；**不** hindsight 评分、**不**强制引 build config、**不**强制 hedge 风格、**不**强制机制具体度。

## 一句话裁决

**报告合格（file:line 准 + 证据闭合 + 计数来自 digest + 机制 hedge 在类型未实证下合理），reviewer 放行正确。** 早期苛责（hindsight/双标/越权/「reviewer 失职」）撤回。唯一温和改进：可补 R8 shrinking 候选一句，非失分。本次实测的真正产出是发现了「hedge 规则放错层（code-tracer 而非 reviewer）」的设计缺陷，已据此重切职责。
