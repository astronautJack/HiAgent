# HiAgent — 解耦版 agent 工具集（Claude Code）

按**能力层 + 用例编排层**组织，不按产品模块。可复用能力抽成共享 subagent，用例 workflow 纯编排。

## 两层架构

### 第 1 层：共享能力（跨 workflow 复用）

| agent | 职责 | tools |
|---|---|---|
| `code-graph` | CRG 管理：build/update/status/freshness/visualize/wiki 子命令 + 结构页 sync（贵的图操作集中） | Read, Bash, Glob |
| `wiki-reader` | 读 wiki 索引 + 按信号匹配 + 按需取页（所有需 wiki 上下文的用例共用） | Read, Grep, Bash, Glob |
| `code-tracer` | 反向回溯定位根因（输入=症状，log 派生或 bug 报告派生都行；diag 和 bug-trace 共用） | Read, Grep, Bash, Glob |
| `log-parser` | logscope-triage CLI 包装：长日志→有界 digest | Read, Write, Bash |

### 第 2 层：专职 subagent（各被特定 workflow 调）

**Wiki 生产者家族**（共享 wiki 约定，内容各异）：
| agent | 产出 |
|---|---|
| `arch-wiki-writer` | 架构文档（DeepWiki 风，LLM 散文） |
| `flow-wiki-writer` | 业务流生命周期页 + 错误目录 + error_index |
| `exp-wiki-writer` | 经验案例页 + 索引 |

**feature 实现流水线**（顺序链）：
| agent | 阶段 |
|---|---|
| `feature-planner` | 需求→设计 |
| `feature-coder` | 实现 |
| `feature-reviewer` | 自审 + 影响面 |
| `feature-tester` | 门禁 build/lint/typecheck/test |

## 用例 workflow（纯编排）

| workflow | 编排 |
|---|---|
| `entry` | 路由：分类意图 → 调用例 workflow |
| `diag` | log-parser → wiki-reader → code-tracer → critic 循环 → 报告 |
| `bug-trace` | wiki-reader → code-tracer → 报告 |
| `feature-design` | feature-planner → 设计交人审 |
| `wiki-map` | code-graph（build+wiki 子命令+sync 到目标目录） |
| `wiki-doc` | code-graph（build+wiki）→ arch-wiki-writer 写架构文档 |
| `wiki-flow` | flow-wiki-writer（沿 CRG flows 写业务流页 + error_index） |
| `exp-archive` | exp-wiki-writer（写案例页 + 索引） |
| `exp-search` | wiki-reader（查索引 + 全文匹配） |

## Wiki 约定（所有 wiki 生产者遵循）

**frontmatter**：
```yaml
id: <slug>
title: <人类可读>
level: L2
parent: <repo>-wiki
related: [<slug>, ...]
source_paths: [相对路径, ...]
last_sync_commit: <git -C <repo> rev-parse HEAD>
```

**增量刷新**（避免无谓重写未变页）：
1. 无旧 wiki（首次）→ 全量。
2. 否则逐页：Read 旧页 frontmatter `last_sync_commit`（无 → 重做）。
3. `git -C <repo> diff <last_sync>..HEAD --name-only` 拿变化文件。
4. 该页 `source_paths` 与变化文件取交集；非空 → 重做，空 → 跳过保留。
5. `last_sync_commit` 刷新为当前 HEAD。

**索引格式**：markdown 表格（小，可全量入上下文给 wiki-reader 检索）。禁 HTML 注释锚点。

## 共享预检：CRG 新鲜度门

启动 `diag` / `bug-trace` / `feature-design` / `wiki-flow` 前会话先确认 CRG 图新鲜：
1. `Bash(code-review-graph status --repo <repo>)` 判新鲜。
2. 缺/过时 → 问用户三选一，问询文本须写清后果：
   - **build**：建图（首次/图库损坏）
   - **update**：增量更新（图过时，代码已变）
   - **不跑**：放弃本次定位（不建图，workflow 不启动）
3. 用户选定后刷新图，再启动 workflow。

`wiki-map` / `wiki-doc` 自己会建图，不额外检查。

## 人审 checkpoint 是 workflow 边界

workflow 不能中途暂停问用户。`feature-design` / `bug-trace` / `diag` 返回报告后会话呈现交人审；批准后才启动 implement/fix workflow（未来加）。

## setup（一次性，不占日常上下文）

**首次部署或重装**：见 `README.md`「安装」段（真实 clone 地址 + uv / CRG / logscope-triage / PATH / 验证步骤）。装完重启 Claude Code 让 `settings.json` 的 MCP 生效。日常工作时不需要这些内容在上下文里。
