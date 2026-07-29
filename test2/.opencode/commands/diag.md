---
description: 日志报错定位（log → 代码行 + 证据链）
subtask: true
---
定位日志报错到代码行。参数：$ARGUMENTS（日志路径 + 代码仓路径 [+ wiki 路径]）

按以下步骤编排，每步用 Task 工具调对应 subagent，中间结果留你这不要逐字回显给主会话，最后只返报告：

1. **CRG 新鲜度门（内联，可问用户）**：跑 `bash: code-review-graph status --repo <repo>`。缺/过时 → 用 question 工具问用户三选一：**build**（建图）/ **update**（增量更新）/ **不跑**（放弃本次定位，workflow 不启动）。选定后刷新图再继续。

2. **压日志**：Task 调 `log-parser` subagent。传日志路径。要它跑 `logscope-triage <file> --top 50 --json --profile diag`，返 digest（claimed_error / new_cluster_ids / clusters / preview）。

3. **取上下文**：若有 wiki → Task 调 `wiki-reader`，传 digest 信号（claimed_error 关键词 + 新见簇），读 `<wiki>/error_index.md` 匹配，返调用链/契约上下文。无 wiki → 跳过（提示「本仓无业务流页，本次无历史经验加持」但不停下，继续）。

4. **回溯（critic 循环，最多 3 次）**：Task 调 `code-tracer`，传 digest + wiki 上下文（无则标「退回源码」），沿 CRG callers_of 反向回溯到 file:line 根因 + 证据链。回溯后自审证据链是否闭合：闭合（confident）→ 进报告；弱 → 指出缺哪环，重跑回溯（最多 3 次）。

5. **报告**：返 `{file, line, confidence, evidence, claimed_error, digest_preview}` 交主会话呈现人审。
