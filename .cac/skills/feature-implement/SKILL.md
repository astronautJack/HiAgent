---
name: feature-implement
description: 代码实现用例。按人工批准的设计执行 coder → CRG 增量刷新 → reviewer → tester 闭环，最多三轮，不提交不推送。用户明确批准 feature-design 的 handoff 后，原样传 args {repo, design, approved:true}。
---

# feature-implement — 实现/审查/测试状态机

本 skill 是编排层，只做批准校验、闭环控制和契约校验；底层能力放 subagent。

## 输入

- `repo`：目标代码仓（必填）。
- `design`：`hiagent.feature-design.v1`（必填）。
- `approved`：必须为 `true`。

## 路径工具

- `isWindowsAbsolutePath(v)`、`hasTraversal(v)`、`isSafeRelativePath(v)`。

## 阶段 1：Gate

1. `repo` 必须 Windows 绝对路径且无穿越，否则 `{implemented:false, stage:'gate', error:'repo 必须是 Windows 绝对路径'}`。
2. `approved !== true` 则 `{implemented:false, stage:'gate', error:'缺少人工批准：approved 必须为 true'}`。
3. `design.schema_version` 必须 `'hiagent.feature-design.v1'`，否则 `error:'design 必须符合 hiagent.feature-design.v1'`。
4. `design.summary` 是字符串、`design.changes` 与 `design.test_plan` 是数组，否则 `error:'design 缺少 summary/changes/test_plan'`。
5. `design.changes` 中每个 `change.file` 必须 `isSafeRelativePath`，否则 `error:'design 包含仓外或非法相对路径'}`。

任一未过则 `{implemented:false, stage:'gate', error}`，不调用任何 subagent。

## 阶段 2-5：实现闭环（最多三轮）

初始化 `implementation=null`、`review={verdict:'revise', findings:[], impact:[]}`、`tests={verdict:'fail', commands:[], failures:[]}`、`feedback=[]`。`attempt` 1..3：

### Implement

调用 `feature-coder`，提示「按已批准设计实现；只改设计范围，不 commit/push。」输入 `{repo, design, feedback}`。校验 `CODE = {summary, changed_files:string[], remaining_issues:string[]}`。`changed_files` 每项必须 `isSafeRelativePath`，否则 `{implemented:false, stage:'implementation-contract', error:'coder 返回仓外或非法路径', implementation, attempts, committed:false}`。`remaining_issues` 非空时 `feedback=remaining_issues`，记录日志，进入下一轮。

### Graph

调用 `code-graph`，提示「执行 hiagent-crg refresh --repo <repo>，用本地 CLI 把当前 working tree 增量写入图；禁止用 MCP build。」校验 `GATE = {ok, error, warning}`。`!ok` 则 `{implemented:false, stage:'crg-refresh', error:graph.error, ...}`。`warning` 非空记录日志。

### Review

调用 `feature-reviewer`，提示「独立审查当前 git diff。」输入 `{repo, design, implementation}`。校验 `REVIEW = {verdict:'pass|revise', findings:array, impact:string[]}`。`verdict==='revise'` 时 `feedback=review.findings`，记录日志，进入下一轮。

### Test

调用 `feature-tester`，提示「自动发现并运行目标仓质量门禁。」输入 `{repo, design, changed_files:implementation.changed_files}`。校验 `TEST = {verdict:'pass|fail', commands:array, failures:string[]}`。`verdict==='pass'` 时返回成功结果；否则 `feedback=tests.failures`，记录日志，进入下一轮。

## 输出

### 成功（tester pass）

```json
{
  "implemented": true,
  "review": "<REVIEW>",
  "tests": "<TEST>",
  "implementation": "<CODE>",
  "attempts": 1,
  "committed": false,
  "next": "请人工检查 git diff；确认后可归档实现经验并由你手动提交。"
}
```

### 三轮未通过

```json
{
  "implemented": false,
  "stage": "quality-gate",
  "review": "<REVIEW>",
  "tests": "<TEST>",
  "implementation": "<CODE>",
  "attempts": 3,
  "committed": false,
  "next": "保留当前工作区供人工处理，未提交、未推送。"
}
```

## 不变量

- 只有用户明确批准、且把 feature-design 的 design 原样传入、`approved=true` 才进入实现。
- CRG mutation 只走本地 `hiagent-crg`/`code-review-graph` CLI；禁止通过 MCP 建图或更新。
- 任何阶段失败都保留工作区，但不 commit/push。
- 实现闭环最多三轮。
