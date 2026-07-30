# HiAgent — 解耦版 agent 工具集（OpenCode）

按**能力层 + 用例编排层**组织，不按产品模块。可复用能力抽成共享 subagent，用例 command 纯编排（turn-by-turn，主会话/子会话调 Task 串 subagent）。

## 两层架构

### 第 1 层：共享能力（跨 command 复用）

| agent | 职责 | tools |
|---|---|---|
| `code-graph` | CRG 管理：build/update/status/freshness/visualize/wiki 子命令 + 结构页 sync（贵的图操作集中） | Read, Bash, Glob |
| `wiki-reader` | 读 wiki 索引 + 按信号匹配 + 按需取页（所有需 wiki 上下文的用例共用） | Read, Grep, Bash, Glob |
| `code-tracer` | 反向回溯定位根因（输入=症状，log 派生或 bug 报告派生都行；diag 和 bug-trace 共用）；**写报告文件交 reviewer 审**，不自审 | Read, Grep, Bash, Glob, Edit |
| `code-tracer-reviewer` | 独立审阅 code-tracer 报告：重跑 CRG/grep + 重读源码 + 对 digest 验计数 + 验修复可 apply，返 verdict。验证能力同 code-tracer，但 edit:deny 禁改报告（强制分离，防自审自圆其说） | Read, Grep, Bash, Glob |
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

每个 command 是 `.opencode/commands/*.md` 提示模板，跑时**主会话**按步骤调 Task 串 subagent。多 subagent 编排（diag/bug-trace/feature-design/flow-doc/arch-doc）由主会话 turn-by-turn 跑——**不用 `subtask:true`**（opencode 子会话没 Task 工具、不能 spawn subagent）；单 agent 委派用 `agent:<name>`（直接调该 subagent）。

| 命令 | 编排 | 模式 |
|---|---|---|
| `/entry` | 路由：分类意图 → 建议对应命令 | 主会话 |
| `/diag` | **CRG 门** → log-parser → wiki-reader → **code-tracer 写报告 → reviewer 独立审 → loop 最多 3 次 → 存疑点** → 报告 | 主会话 |
| `/bug-trace` | **CRG 门** → wiki-reader → code-tracer → 报告 | 主会话 |
| `/feature-design` | **CRG 门** → feature-planner → 设计交人审 | 主会话 |
| `/graph-sync` | code-graph（build+wiki 子命令+sync） | agent:code-graph |
| `/arch-doc` | code-graph（build+wiki）→ arch-writer 写架构文档 | 主会话 |
| `/flow-doc` | **CRG 门** → flow-writer（沿 CRG flows 写业务流页 + error_index） | 主会话 |
| `/exp-archive` | exp-writer（归档门只存 high + 写案例页） | agent:exp-writer |
| `/exp-search` | wiki-reader（查索引 + 全文 + 验过期） | agent:wiki-reader |

## 人审 checkpoint 是 command 边界

`/feature-design` / `/bug-trace` / `/diag` 返回报告后交主会话呈现人审；批准后才进 implement/fix（未来加）。`/diag` 用「code-tracer 写报告 + 独立 reviewer 审」双 agent loop（最多 3 次），防 code-tracer 自审自圆其说；max loop 未共识则在报告末尾加 `## 存疑点` 段。

## setup（一次性，不占日常上下文）

**首次部署或重装**：见 `README.md`「安装」段（真实 clone 地址 + uv / CRG / logscope-triage / PATH / 验证步骤）。装完重启 OpenCode 让 `opencode.json` 的 MCP 生效。日常工作时不需要这些内容在上下文里。
