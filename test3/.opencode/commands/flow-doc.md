---
description: 生成业务流 wiki + 错误目录（flow-writer）
agent: flow-writer
---
沿 CRG flows 写业务流生命周期页 + error_index。参数：$ARGUMENTS（代码仓路径 + wiki 输出路径）

你是 flow-writer。跑 `code-review-graph flows --repo <repo>` 列执行流，逐条沿 CRG `flow --name <入口> --source` 写业务流页（frontmatter 含 flows + error_catalog 字段 + 章节 + error_index 表列），覆盖预期错误目录（throw 点 + 错误码 + 触发条件）。遵循共享 wiki 约定（frontmatter + 增量刷新 + 索引）。禁 HTML 注释锚点。

注：若 CRG 图未建，先 `code-review-graph build --repo <repo>`（你可调 bash）。需要时用 question 问用户。
