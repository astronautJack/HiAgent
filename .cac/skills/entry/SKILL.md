---
name: entry
description: 智能路由用例。分类用户请求意图并分发到对应 skill。用户请求跨用例或意图模糊、需要先分类再分发时使用；单用例意图清晰时直接调对应 skill。
---

# entry — 意图分类与分发状态机

本 skill 是编排层，只做分类与分发，不承担领域判断。

## 输入

- `args.userInput`：用户原始请求（必填）。缺失则返回 `{error:'传 args.userInput'}`。

## 阶段 1：Classify

调用 agent 分类用户请求到 skill，返回符合 `INTENT` 契约：

```json
{
  "skill": "diag | bug-trace | feature-design | feature-implement | exp-archive | exp-search | wiki-health",
  "args": {},
  "confidence": "high | low",
  "clarifying_question": "string（可选）"
}
```

分类判据：

- `diag`：用户给了【日志文件/日志文本】，要定位到代码行。
- `bug-trace`：用户给了【bug 报告/失败现象（非日志）】，要找根因。
- `feature-design`：用户提出需求，需要先出设计并人审。
- `feature-implement`：用户已明确批准 `hiagent.feature-design.v1` 设计，要开始改代码。
- `exp-archive`：归档案例。
- `exp-search`：检索历史案例（"这错见过吗"）。
- `wiki-health`：检查内网 wiki-mcp 是否已经可用。

边界规则：

- 涉及目标代码的 skill，`repo` 必须是 Windows 绝对路径。
- `wiki-health` 无参数；`exp-search` 的 `repo` 可选。
- `feature-design` 返回 `ask_user`/handoff 后必须询问用户；只有用户明确批准并把该结果中的 design 原样传入时，`feature-implement` 才能命中。

`confidence==='low'` 时返回 `{ask_user: intent.clarifying_question}`，不进入分发。

## 阶段 2：Dispatch

记录「Dispatching to <skill>」，随后加载并执行命中的 skill，把 `intent.args` 作为其输入。

## 不变量

- 分类模糊时必须先澄清，不得低置信直发。
- 不在单步中暂停等待用户；需人工决策时返回 `ask_user`，由 CodeAgent 在下一轮继续。
