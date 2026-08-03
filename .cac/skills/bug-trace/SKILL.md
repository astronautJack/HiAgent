---
name: bug-trace
description: 非日志症状定位用例。从 bug 报告/失败现象定位到代码根因行，由独立 reviewer 对抗复核（最多三轮），最后由第三个隔离 subagent 渲染报告。与 diag 共用 trace/review 契约。传 args {report, repo, reportPath?}。
---

# bug-trace — 非日志症状定位状态机

本 skill 是编排层，只做校验、状态机、循环和结构化传值；底层能力放 subagent。严格按下列阶段顺序执行。与 diag 的差异：无 Triage 阶段，输入是症状文本而非日志。

## 输入

- `report`：bug 报告或失败现象文本（必填）。
- `repo`：目标代码仓（必填）。
- `reportPath`：可选。

## 路径与安全工具

- `isWindowsAbsolutePath(v)`：`/^[A-Za-z]:[\\/]/` 或 UNC。
- `hasTraversal(v)`：按 `[\\/]/` 切分后含 `..`。
- `normalizePath(v)`：`/`→`\\`、去尾分隔、小写。
- `isWithinRepo(repo, v)`：均为 Windows 绝对路径、无穿越、normalize 后以 `repo\\` 为前缀。
- `repoPath(repo, ...parts)`：`[repo 去尾分隔, ...parts].join('\\')`。
- `isSafeRelativePath(v)`：非空、非 Windows 绝对路径、无穿越。

## 阶段 1：Validate

1. `repo` 必须是 Windows 绝对路径且无穿越，否则中止。
2. `report` 必须是非空字符串，否则 `{aborted:true, stage:'validate', error:'report 不能为空'}`。
3. `runId = bug-<Date.now()>`，`reportPath = args.reportPath || repoPath(repo,'.hiagent','runs',runId,'report.md')`，必须 Windows 绝对路径且 `isWithinRepo(repo, reportPath)`。

## 阶段 2：CRG

调用 `code-graph`，提示「确保当前代码图新鲜。repo=<repo>。」校验 `GATE = {ok:boolean, error:string, warning:string}`。`ok` 为 false 则 `{aborted:true, stage:'crg', error:gate.error}`。`warning` 非空时记录日志。

## 阶段 3：Knowledge

调用 `wiki-gateway` 执行 probe，校验 `PROBE = {available:boolean, server:string, capabilities:object, error:string}`。`available` 且 `capabilities.search` 为真时，用 `{query:{report, repo}, limit:8}` 调 search，校验 `SEARCH = {matches:array, total:integer}`；否则 `knowledge={matches:[], total:0}`。

## 阶段 4 & 5：Trace ↔ Review（最多三轮）

初始化 `trace=null`、`verdict={verdict:'revise', independent_summary:'', contradictions:[], findings:[], verified_claims:[]}`、`consensus=false`。`attempt` 1..3：

### Trace

调用 `code-tracer`，提示「你是独立 investigator，只定位并返回结构化 trace，禁止写报告。」输入 `{repo, symptom:report, knowledge, reviewer_findings:[...verdict.findings, ...verdict.contradictions]}`。校验 `TRACE`：

- `schema_version='hiagent.trace.v1'`
- `root_cause={file,line,symbol,summary,confidence:'high|medium|low'}`，`file` 必须 `isSafeRelativePath`，否则 `{aborted:true, stage:'trace-contract', error:'trace 返回了非法源码相对路径'}`。
- `evidence[].{kind:'log|code|crg|config|wiki', ref, claim}`、`impact:string[]`、`fix.{summary, changes[].{file,description}}`、`open_questions:string[]`。

### Review

调用 `code-tracer-reviewer`，提示「你是隔离上下文的 adversarial reviewer。报告尚未生成；先独立调查，再核验 trace。」输入 `{repo, symptom:report, trace}`。校验 `VERDICT = {verdict:'pass|revise', independent_summary, contradictions:string[], findings:string[], verified_claims:string[]}`。`pass` 时 `consensus=true` 跳出；否则记录「第 N 轮需修订：<findings>」。

## 阶段 6：Report

调用 `trace-report-writer`，提示「只把已结束的调查与复核结果渲染到报告，禁止改变结论。」输入 `{repo, runId, reportPath, symptom:report, trace, verdict, consensus}`。校验 `REPORT = {written:boolean, report_path:string, error:string}`。`written` 为 false 或路径不合规则 `{aborted:true, stage:'report', error:...}`。

## 输出

```json
{
  "aborted": false,
  "run_id": "bug-<ts>",
  "report_path": "<Windows 绝对路径>",
  "root_cause": "<trace.root_cause>",
  "evidence": "<trace.evidence>",
  "fix": "<trace.fix>",
  "open_questions": "<consensus?trace.open_questions:追加 verdict.findings+contradictions>",
  "review": { "consensus": false, "...verdict" },
  "wiki": { "available": true, "matches": 0 },
  "next": "请人工审阅报告；确认根因和验证结果后再运行 exp-archive。"
}
```

## 不变量

- investigator、reviewer、report writer 是三个独立 subagent、独立上下文；报告在复核结束前不存在。
- 未达一致时 writer 必须醒目标注争议并保留全部 open questions。
- 不自动 commit/push，不绕过人工审阅和归档质量门。
