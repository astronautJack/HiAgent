---
description: 生成结构 wiki（建图 + wiki 子命令 + sync）
agent: code-graph
---
为目标仓建 CRG 图 + 生成结构页 + sync 到 wiki 目录。参数：$ARGUMENTS（代码仓路径 + wiki 输出路径）

你是 code-graph。跑 `code-review-graph build --repo <repo>`（建图）、`code-review-graph wiki --repo <repo>`（生成结构页），再把结构页 sync（cp）到目标 wiki 目录。返生成的结构页清单 + wiki 目录路径。

需要时用 question 问用户（如目标目录不存在是否新建）。
