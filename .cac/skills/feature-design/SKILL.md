---
name: feature-design
description: 代码设计用例。结合当前源码、CRG 与 wiki 经验候选，生成带源码触点、风险和测试计划的结构化设计，返回 ask_user 和 handoff 交人审。传 args {requirement, repo}。
---

# feature-design — 结构化设计状态机

本 skill 是编排层，只做校验、CRG 新鲜度门、知识检索调度和设计契约校验；底层能力放 subagent。

## 输入

- `requirement`：需求文本（必填）。
- `repo`：目标代码仓（必填）。

## 路径工具

- `isWindowsAbsolutePath(v)`、`hasTraversal(v)`、`isSafeRelativePath(v)`（非空、非 Windows 绝对路径、无穿越）。

## 阶段 1：Validate

`repo` 必须 Windows 绝对路径且无穿越，否则 `{aborted:true, stage:'validate', error:'repo 必须是 Windows 绝对路径'}`。`requirement` 必须非空字符串。

## 阶段 2：CRG

调用 `code-graph`，提示「确保 CRG 图对应当前 HEAD。repo=<repo>」。校验 `GATE = {ok, error, warning}`。`!ok` 则 `{aborted:true, stage:'crg', error:gate.error}`。`warning` 非空记录日志。

## 阶段 3：Knowledge

调用 `wiki-gateway` 执行 probe，校验 `PROBE = {available, server, capabilities, error}`。`available && capabilities.search` 为真时，用 `{query:{requirement, repo, kinds:['architecture','convention','experience']}, limit:8}` 调 search，校验 `SEARCH = {matches, total}`；否则 `knowledge={matches:[], total:0}`。

## 阶段 4：Design

调用 `feature-planner` subagent，提示「生成设计。」输入 `{requirement, repo, knowledge}`。校验 `DESIGN` 契约：

```json
{
  "schema_version": "hiagent.feature-design.v1",
  "summary": "",
  "assumptions": [],
  "changes": [{"file":"","symbol":"","description":"","type":"add|modify|delete"}],
  "risks": [],
  "test_plan": [],
  "knowledge_updates": []
}
```

`design.changes` 中每个 `change.file` 必须 `isSafeRelativePath`，否则 `{aborted:true, stage:'design-contract', error:'设计包含仓外或非法相对路径'}`。

## 输出

`approvalQuestion = '设计已经完成。是否批准按此设计进入 feature-implement，开始修改代码并执行独立审查和测试？'`。返回：

```json
{
  "aborted": false,
  "requirement": "",
  "repo": "",
  "design": "<hiagent.feature-design.v1>",
  "wiki": { "available": true, "matches": 0 },
  "ask_user": "<approvalQuestion>",
  "handoff": {
    "schema_version": "hiagent.skill-handoff.v1",
    "status": "awaiting_user_approval",
    "question": "<approvalQuestion>",
    "on_approve": {
      "skill": "feature-implement",
      "args": { "repo": "", "approved": true },
      "design_source": "本次 feature-design 返回值中的 design，必须原样传递"
    },
    "on_reject": "保留设计，不修改代码；根据用户意见重新运行 feature-design 或结束。"
  }
}
```

## 不变量

- 返回 `ask_user` 和 `hiagent.skill-handoff.v1`；用户明确批准后，才把同一份 design 原样传给要求 `approved=true` 的 `feature-implement`。
- 不修改代码，不 commit/push。
- 不在单步中暂停等待用户；返回 `ask_user` 和 handoff，由 CodeAgent 在下一轮继续。
