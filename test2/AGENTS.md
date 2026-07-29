# HiAgent — 解耦版 agent 工具集（OpenCode）

按**能力层 + 用例编排层**组织，不按产品模块。可复用能力抽成共享 subagent，用例 command 纯编排（turn-by-turn，主会话/子会话调 Task 串 subagent）。

## 两层架构

### 第 1 层：共享能力（跨 command 复用）

| agent | 职责 | tools |
|---|---|---|
| `code-graph` | CRG 管理：build/update/status/freshness/visualize/wiki 子命令 + 结构页 sync（贵的图操作集中） | Read, Bash, Glob |
| `wiki-reader` | 读 wiki 索引 + 按信号匹配 + 按需取页（所有需 wiki 上下文的用例共用） | Read, Grep, Bash, Glob |
| `code-tracer` | 反向回溯定位根因（输入=症状，log 派生或 bug 报告派生都行；diag 和 bug-trace 共用） | Read, Grep, Bash, Glob |
| `log-parser` | logscope-triage CLI 包装：长日志→有界 digest | Read, Write, Bash |

### 第 2 层：专职 subagent（各被特定 command 调）

**Wiki 生产者家族**（共享 wiki 约定，内容各异）：
| agent | 产出 |
|---|---|
| `arch-writer` | 架构文档（DeepWiki 风，LLM 散文） |
| `flow-writer` | 业务流生命周期页 + 错误目录 + error_index |
| `exp-writer` | 经验案例页 + 索引 |

**feature 实现流水线**（顺序链）：
| agent | 阶段 |
|---|---|
| `feature-planner` | 需求→设计 |
| `feature-coder` | 实现 |
| `feature-reviewer` | 自审 + 影响面 |
| `feature-tester` | 门禁 build/lint/typecheck/test |

## 用例 command（纯编排，turn-by-turn）

每个 command 是 `.opencode/commands/*.md` 提示模板，跑时主会话（或 `subtask:true` 子会话）按步骤调 Task 串 subagent。复杂编排用 `subtask:true`（子会话跑，不污染主上下文）；单 agent 委派用 `agent:<name>`（直接调该 subagent）。

| 命令 | 编排 | 模式 |
|---|---|---|
| `/entry` | 路由：分类意图 → 建议对应命令 | 主会话 |
| `/diag` | log-parser → wiki-reader → code-tracer → critic 循环 → 报告 | subtask |
| `/bug-trace` | wiki-reader → code-tracer → 报告 | subtask |
| `/feature-design` | feature-planner → 设计交人审 | agent:feature-planner |
| `/graph-sync` | code-graph（build+wiki 子命令+sync） | agent:code-graph |
| `/arch-doc` | code-graph（build+wiki）→ arch-writer 写架构文档 | subtask |
| `/flow-doc` | flow-writer（沿 CRG flows 写业务流页 + error_index） | agent:flow-writer |
| `/exp-archive` | exp-writer（归档门只存 high + 写案例页） | agent:exp-writer |
| `/exp-search` | wiki-reader（查索引 + 全文 + 验过期） | agent:wiki-reader |

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

## 共享预检：CRG 新鲜度门（内联进 command）

启动 `/diag` / `/bug-trace` / `/feature-design` / `/flow-doc` 时**在 command 内**确认 CRG 图新鲜（OpenCode 有 question 工具，可中途问用户）：
1. `bash: code-review-graph status --repo <repo>` 判新鲜。
2. 缺/过时 → question 问用户三选一，问询文本须写清后果：
   - **build**：建图（首次/图库损坏）
   - **update**：增量更新（图过时，代码已变）
   - **不跑**：放弃本次定位（不建图，command 不继续）
3. 用户选定后刷新图，再继续编排。

`/graph-sync` / `/arch-doc` 自己会建图，不额外检查。

## 人审 checkpoint 是 command 边界

`/feature-design` / `/bug-trace` / `/diag` 返回报告后交主会话呈现人审；批准后才进 implement/fix（未来加）。`subtask:true` 的命令在子会话跑完只返最终报告，中间步骤不污染主上下文。

## setup（一次性，不占日常上下文）

**首次部署或重装**：见 `README.md`「安装」段（真实 clone 地址 + uv / CRG / logscope-triage / PATH / 验证步骤）。装完重启 OpenCode 让 `opencode.json` 的 MCP 生效。日常工作时不需要这些内容在上下文里。
