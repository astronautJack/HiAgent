---
description: 需求 → 设计（CRG 门 → feature-planner，交人审）
---
把需求转成设计文档交人审。参数：$ARGUMENTS（需求描述 + 代码仓路径）

1. **CRG 新鲜度门**：Task 调 `code-graph`（全程判新鲜/问询/建图/报错）。`{ok:true}`→继续 step 2；`{ok:false}`→workflow 中止，不继续。
2. **设计**：Task 调 `feature-planner`，传需求 + repo（图已新鲜）。读 CRG `get_minimal_context` 拿相关上下文，把需求拆成设计（模块改动/接口/数据流/风险/验证点），返设计文档。**只设计不改码**——交主会话人审，批准后才进 implement。
