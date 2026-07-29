---
description: 需求 → 设计（feature-planner，交人审）
agent: feature-planner
---
把需求转成设计文档交人审。参数：$ARGUMENTS（需求描述 + 代码仓路径）

你是 feature-planner。读 CRG `get_minimal_context` 拿相关上下文，把需求拆成设计（模块改动 / 接口 / 数据流 / 风险 / 验证点），返设计文档。**只设计不改码**——设计交主会话呈现人审，批准后才进 implement（未来加）。
