---
description: 需求 → 设计（CRG 门 → feature-planner，交人审）
subtask: false
---
把需求转成设计文档交人审。参数：$ARGUMENTS（需求描述 + 代码仓路径）

> 你是主会话编排者。禁止把整条 workflow 委派给单个 subagent（subagent 无 Task 工具，会断链）。
> 必须按步骤逐个用 Task 工具调对应 subagent——每步一次 Task 调用，
> 中间 digest/上下文留在本会话上下文里串起来，最后只返报告。

1. **CRG 新鲜度门**：Task 调 `code-graph`（全程判新鲜/问询/建图/报错）。`{ok:true}`→继续 step 2；`{ok:false}`→workflow 中止，不继续。
2. **设计**：Task 调 `feature-planner`，传需求 + repo（图已新鲜）。读 CRG `get_minimal_context` 拿相关上下文，把需求拆成设计（模块改动/接口/数据流/风险/验证点），返设计文档。**只设计不改码**——交主会话人审，批准后才进 implement。
