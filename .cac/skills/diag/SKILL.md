---
name: diag
description: 日志定位用例。把日志压缩成有界 digest，沿 CRG 调用图定位根因代码行，由独立 reviewer 对抗复核（最多三轮），最后由第三个隔离 subagent 渲染报告。传 args {logPath|logText, repo, logFormat?, drainMode?, profile?, reportPath?}。
---

# diag — 日志定位状态机

本 skill 是编排层，只做校验、状态机、循环和结构化传值；底层能力放 subagent（`.cac/agents/`）。严格按下列阶段顺序执行，不得跳过或重排。

## 输入

- `logPath` 或 `logText`，二选一。
- `repo`：目标代码仓（必填）。
- `logFormat`：`auto | harmony | generic`，默认 `auto`。
- `drainMode`：`learn | inference`，默认 `learn`。
- `profile`：模板库名称，默认 `hiagent-<repoName>`。
- `reportPath`：可选，缺省由本 skill 计算。

## 路径与安全工具

下列校验贯穿全流程，所有阶段复用：

- `isWindowsAbsolutePath(v)`：`/^[A-Za-z]:[\\/]/` 或 UNC `/^\\\\[^\\/]+[\\/][^\\/]+/`。
- `hasTraversal(v)`：按 `[\\/]/` 切分后包含 `..` 即为穿越。
- `normalizePath(v)`：`/` 替换为 `\\`、去尾分隔、小写。
- `isWithinRepo(repo, v)`：repo 与 v 都是 Windows 绝对路径、无穿越、且 normalize 后以 `repo\\` 为前缀。
- `repoPath(repo, ...parts)`：`[repo 去尾分隔, ...parts].join('\\')`。
- `isSafeRelativePath(v)`：非空、非 Windows 绝对路径、无穿越——用于校验 subagent 返回的源码相对路径。

## 阶段 1：Validate

1. `repo` 必须是 Windows 绝对路径且无穿越，否则 `{aborted:true, stage:'validate', error:'repo 必须是 Windows 绝对路径'}`。
2. `logPath` 与 `logText` 必须且只能提供一个；同时提供或都缺失则中止。
3. `logText` 超过 20000 字符则中止，提示先存为文件传 `logPath`，避免灌入上下文。
4. `logPath` 必须是 Windows 绝对路径且无穿越。
5. `logFormat` 必须属于 `['auto','harmony','generic']`，`drainMode` 必须属于 `['learn','inference']`。
6. 计算 `runId = diag-<Date.now()>`，`workDir = repoPath(repo,'.hiagent','runs',runId)`，`reportPath = args.reportPath || repoPath(workDir,'report.md')`，`repoName = repo 去尾分隔后按 `[\\/]` 切分取末段或 'repo'`，`profile = args.profile || hiagent-<repoName>`。
7. `reportPath` 必须是 Windows 绝对路径且 `isWithinRepo(repo, reportPath)`，否则中止。

## 阶段 2：CRG

调用 `code-graph` subagent，提示「确保 CRG 图可用且对应当前 HEAD。repo=<repo>。缺失或过时则 build；失败返回明确错误。」，校验返回符合 `GATE` 契约。

- `GATE = { ok:boolean, error:string, warning:string }`
- `ok` 为 false 则 `{aborted:true, stage:'crg', error:gate.error}`。
- `warning` 非空时记录到日志。

## 阶段 3：Triage

调用 `log-parser` subagent，提示「先执行 hiagent-run prepare，再把输入转换为唯一日志契约并原样返回。」输入 `{repo, runId, logPath, logText, logFormat, drainMode, profile, workDir}`，校验返回符合 `DIGEST` 契约。

`DIGEST` 必填字段：`schema_version='hiagent.log-digest.v1'`、`raw_file`、`log_format`、`drain_mode`、`line_count`、`claimed_error`（可为 null）、`symbols`、`clusters`、`hisysevent_anchors`、`fault_frames`、`key_lines`、`truncated`。

## 阶段 4：Knowledge

调用 `wiki-gateway` subagent 执行 probe，校验返回符合 `PROBE` 契约：

- `PROBE = { available:boolean, server:string, capabilities:object, error:string }`

`available` 且 `capabilities.search` 为真时，构造 query `{claimed_error, symbols(前30), templates(clusters 前10 的 template), repo}`，调用 `wiki-gateway` 执行 search，校验返回符合 `SEARCH = { matches:array, total:integer }`。否则记录「wiki-mcp 不可用，按源码定位」并继续。

## 阶段 5 & 6：Trace ↔ Review（最多三轮）

初始化 `trace=null`、`verdict={verdict:'revise', independent_summary:'', contradictions:[], findings:[], verified_claims:[]}`、`consensus=false`。`attempt` 从 1 到 3：

### Trace

调用 `code-tracer` subagent，提示「你是独立 investigator，只定位并返回结构化 trace，禁止写报告。」输入 `{repo, digest, knowledge, reviewer_findings:[...verdict.findings, ...verdict.contradictions]}`，校验返回符合 `TRACE` 契约：

- `TRACE.schema_version='hiagent.trace.v1'`
- `root_cause = {file:string, line:integer, symbol:string, summary:string, confidence:'high|medium|low'}`，且 `root_cause.file` 必须通过 `isSafeRelativePath`，否则 `{aborted:true, stage:'trace-contract', error:'trace 返回了非法源码相对路径'}`。
- `evidence[].{kind:'log|code|crg|config|wiki', ref, claim}`
- `impact: string[]`、`fix.{summary, changes[].{file,description}}`、`open_questions: string[]`

### Review

调用 `code-tracer-reviewer` subagent，提示「你是隔离上下文的 adversarial reviewer。报告尚未生成；先独立调查，再核验 trace。」输入 `{repo, digest, trace}`，校验返回符合 `VERDICT` 契约：

- `VERDICT = {verdict:'pass|revise', independent_summary, contradictions:string[], findings:string[], verified_claims:string[]}`

`verdict==='pass'` 时 `consensus=true` 并跳出循环。否则记录「第 N 轮需修订：<findings>」，进入下一轮。

## 阶段 7：Report

调用 `trace-report-writer` subagent，提示「只把已结束的调查与复核结果渲染到报告，禁止改变结论。」输入 `{repo, runId, reportPath, symptom:digest.claimed_error, digest, trace, verdict, consensus}`，校验返回符合 `REPORT = {written:boolean, report_path:string, error:string}`。

`written` 为 false、`report_path` 非 Windows 绝对路径或不在 repo 内时，`{aborted:true, stage:'report', error:...}`。

## 输出

```json
{
  "aborted": false,
  "run_id": "diag-<ts>",
  "report_path": "<Windows 绝对路径>",
  "root_cause": "<trace.root_cause>",
  "evidence": "<trace.evidence>",
  "fix": "<trace.fix>",
  "open_questions": "<trace.open_questions 合并 consensus=false 时 verdict.findings+contradictions>",
  "review": { "consensus": false, "...verdict" },
  "wiki": { "available": true, "matches": 0 },
  "next": "请人工审阅报告；确认根因和验证结果后再运行 exp-archive。"
}
```

`open_questions`：consensus 为真时取 `trace.open_questions`；否则 `trace.open_questions` 追加 `verdict.findings` 与 `verdict.contradictions`。

## 不变量

- investigator、reviewer、report writer 是三个独立 subagent、独立上下文；报告在复核结束前不存在。
- 未达一致时 writer 必须醒目标注争议并保留全部 open questions，不通过措辞掩盖分歧。
- 不自动 commit/push，不绕过人工审阅和归档质量门。
