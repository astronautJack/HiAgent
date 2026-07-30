---
description: 日志报错定位（log → 代码行 + 证据链；code-tracer 写报告，独立 reviewer 审 + loop）
subtask: true
---
定位日志报错到代码行。参数：$ARGUMENTS（日志路径 + 代码仓路径 [+ wiki 路径]）

按以下步骤编排，每步用 Task 工具调对应 subagent，中间结果留你这不要逐字回显给主会话，最后只返报告文件路径 + 一行结论：

1. **CRG 新鲜度门（Bash CLI，不走 MCP——避免 RPC 超时）**：
   - 跑 `bash: code-review-graph status --repo <repo>`。fresh → 继续。
   - 缺/过时 → 用 question 工具问用户三选一：**build**（建图）/ **update**（增量更新）/ **不跑**（放弃本次定位，workflow 不启动）。
   - build/update：跑 `bash: code-review-graph build --repo <repo>`（Bash 直跑，无 MCP RPC；全量建图含 flows）。
     - 成功（`status` 转 fresh）→ 继续。
     - **超时或报错**（大仓 build 超 Bash 工具超时阈值，或 build 失败）→ **中止 /diag**：返报错 + 提示「CRG 建图超时/失败，请先在 shell 手动跑 `code-review-graph build --repo <repo>` 完成建图，再重跑 /diag」。**不继续**后续步骤。

2. **压日志**：Task 调 `log-parser` subagent。传日志路径 + 格式（auto/harmony/generic）。要它跑 `logscope-triage <file> --top 50 --json --profile diag --log-format <fmt>`，返 digest（claimed_error / anchors / symbols / fault_frames / preview）。

3. **取上下文**：若有 wiki → Task 调 `wiki-reader`，传 digest 信号（symbols + claimed_error），读 `<wiki>/error_index.md` 匹配，返调用链/契约上下文。无 wiki → 跳过（提示「本仓无业务流页，本次无历史经验加持」但不停下，继续）。

4. **code-tracer 写报告**：定 `report_path = ./diag-report.md`。Task 调 `code-tracer`，传 digest + wiki 上下文（无则标「退回源码」）+ `report_path`。code-tracer 沿 CRG callers_of 反向回溯到 file:line 根因 + 证据链 + 构建开关（涉剥离时）+ 修复建议（具体文件+确切语法），**Write 报告到 `report_path`**，返 `report_path`。

5. **reviewer 独立审**：Task 调 `code-tracer-reviewer`，传 `report_path` + repo + digest。它独立重跑 CRG/grep + 重读源码 + 对 digest 验计数 + 验修复可 apply，返 `{verdict, findings}`。

6. **loop（最多 3 次）**：`verdict="revise"` → Task 调 `code-tracer` 带 `findings` 修订 `report_path` → reviewer 复审。循环最多 3 次。

7. **收尾**：
   - `verdict="pass"`（或第 3 次后共识）→ 呈现 `report_path` 交人审。
   - 3 次到仍未共识 → Task 调 `code-tracer` 告知「max loop 未共识」，让它在 `report_path` 末尾加 `## 存疑点` 段（列 reviewer 指出但未解决的点）→ 呈现。
   返 `report_path` + 一行结论（confidence + 是否含存疑点）。
