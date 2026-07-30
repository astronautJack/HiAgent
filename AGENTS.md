# HiAgent — 解耦版 agent 工具集（CodeAgent）

按**能力层 + 用例编排层**组织，不按产品模块。可复用能力抽成共享 subagent，用例 workflow 纯编排。

## 两层架构

### 第 1 层：共享能力（跨 workflow 复用）

| agent | 职责 | tools |
|---|---|---|
| `code-graph` | CRG 管理：build/update/status/freshness/visualize/wiki 子命令 + 结构页 sync（贵的图操作集中） | Read, Bash, Glob |
| `wiki-reader` | 读 wiki 索引 + 按信号匹配 + 按需取页（所有需 wiki 上下文的用例共用） | Read, Grep, Bash, Glob |
| `code-tracer` | 反向回溯定位根因（输入=症状，log 派生或 bug 报告派生都行；diag 和 bug-trace 共用）；**写报告文件交 reviewer 审**，不自审 | Read, Grep, Bash, Glob, Edit |
| `code-tracer-reviewer` | 独立审阅 code-tracer 报告：重跑 CRG/grep + 重读源码 + 对 digest 验计数 + 验修复可 apply，返 verdict/findings。验证能力同 code-tracer，但 edit:deny 禁改报告（强制分离，防自审自圆其说） | Read, Grep, Bash, Glob |
| `log-parser` | logscope-triage CLI 包装：长日志→有界 digest | Read, Write, Bash |

### 第 2 层：专职 subagent（各被特定 workflow 调）

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

## 用例 workflow（纯编排）

| workflow | 编排 |
|---|---|
| `entry` | 路由：分类意图 → 调用例 workflow |
| `diag` | **CRG 门** → log-parser → wiki-reader → **code-tracer 写报告 → reviewer 独立审 → loop 最多 3 次 → 存疑点** → 报告 |
| `bug-trace` | **CRG 门** → wiki-reader → code-tracer → 报告 |
| `feature-design` | **CRG 门** → feature-planner → 设计交人审 |
| `graph-sync` | code-graph（build+wiki 子命令+sync 到目标目录） |
| `arch-doc` | code-graph（build+wiki）→ arch-writer 写架构文档 |
| `flow-doc` | **CRG 门** → flow-writer（沿 CRG flows 写业务流页 + error_index） |
| `exp-archive` | exp-writer（写案例页 + 索引） |
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

## 人审 checkpoint 是 workflow 边界

workflow 不能中途暂停问用户。`feature-design` / `bug-trace` / `diag` 返回报告后会话呈现交人审；批准后才进 implement/fix workflow（未来加）。`diag` 用「code-tracer 写报告 + 独立 reviewer 审」双 agent loop（最多 3 次），防 code-tracer 自审自圆其说；max loop 未共识则在报告末尾加 `## 存疑点` 段。

## setup（一次性，不占日常上下文）

**首次部署或重装**：见 `README.md`「安装」段（真实 clone 地址 + uv / CRG / logscope-triage / PATH / 验证步骤）。装完重启 CodeAgent 让 `settings.json` 的 MCP 生效。日常工作时不需要这些内容在上下文里。
