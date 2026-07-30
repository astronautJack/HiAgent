---
description: 生成架构文档（建图 → arch-writer 写散文）
---
生成目标仓的架构文档。参数：$ARGUMENTS（代码仓路径 [+ wiki 输出路径]）

编排两步：

1. Task 调 `code-graph` subagent：跑 `code-review-graph build --repo <repo>` 建图（已建则跳过），再跑 `code-review-graph wiki --repo <repo>` 生成结构页，sync 到 wiki 目录。

2. Task 调 `arch-writer` subagent：沿结构页 + CRG 调用图写架构文档（DeepWiki 风散文，每页含职责/组成/工作原理/关键流程+mermaid/模块关系/注意点/下钻锚点），遵循共享 wiki 约定（frontmatter + 增量刷新 + 索引）。

返生成的架构页清单。
