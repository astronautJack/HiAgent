---
description: 检索历史经验（附过期检测）
agent: wiki-reader
---
检索经验 Wiki 历史案例。参数：$ARGUMENTS（查询 + wiki 根 + repo 路径）

你是 wiki-reader。Read `<wiki>/cases/index.md`，Grep 匹配查询关键词；命中 → Read 案例页。**验过期**：从 frontmatter 取 source_commit + evidence/source_paths，跑 `git -C <repo> diff <source_commit>..HEAD --name-only -- <证据文件>`；非空 → stale=true + 列变了的文件；空 → stale=false。无 source_commit 的老 case → stale=true（保守）。未命中 → 全文 Grep。按置信度降序返，stale 降权或标注。
