---
description: 生成业务流 wiki + 错误目录（CRG 门 → flow-writer）
subtask: false
---
沿 CRG flows 写业务流生命周期页 + error_index。参数：$ARGUMENTS（代码仓路径 + wiki 输出路径）

> 你是主会话编排者。禁止把整条 workflow 委派给单个 subagent（subagent 无 Task 工具，会断链）。
> 必须按步骤逐个用 Task 工具调对应 subagent——每步一次 Task 调用，
> 中间 digest/上下文留在本会话上下文里串起来，最后只返报告。

1. **CRG 新鲜度门**：Task 调 `code-graph`（全程判新鲜/问询/建图/报错）。`{ok:true}`→继续 step 2；`{ok:false}`→workflow 中止，不继续。
2. **写业务流页**：Task 调 `flow-writer`，传 repo + wikiPath（图已新鲜）。跑 `code-review-graph flows --repo <repo>` 列执行流，逐条沿 `flow --name <入口> --source` 写业务流页（frontmatter + error_catalog + error_index），遵循共享 wiki 约定（frontmatter + 增量刷新 + 索引）。禁 HTML 注释锚点。
