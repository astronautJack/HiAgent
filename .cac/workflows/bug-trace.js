// bug-trace — 非日志症状定位，与 diag 共用 trace/review 契约
export const meta = {
  name: 'bug-trace',
  description: '从 bug 报告定位到代码根因行并独立审阅',
  whenToUse: '传 args {report, repo, reportPath?}',
  phases: [
    { title: 'Validate', detail: '校验输入' },
    { title: 'CRG', detail: '确保图新鲜' },
    { title: 'Knowledge', detail: '检索权限内历史经验' },
    { title: 'Trace', detail: '根因回溯' },
    { title: 'Review', detail: '独立审阅，最多三轮' },
    { title: 'Report', detail: '交付人审' },
  ],
}

const GATE_SCHEMA = { type: 'object', additionalProperties: false, required: ['ok', 'error', 'warning'], properties: { ok: { type: 'boolean' }, error: { type: 'string' }, warning: { type: 'string' } } }
const PROBE_SCHEMA = { type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'], properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } } }
const SEARCH_SCHEMA = { type: 'object', additionalProperties: false, required: ['matches', 'total'], properties: { matches: { type: 'array', items: { type: 'object' } }, total: { type: 'integer' } } }
const TRACE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'report_path', 'root_cause', 'evidence', 'impact', 'fix', 'open_questions'],
  properties: {
    schema_version: { type: 'string', enum: ['hiagent.trace.v1'] }, report_path: { type: 'string' },
    root_cause: { type: 'object', additionalProperties: false, required: ['file', 'line', 'symbol', 'summary', 'confidence'], properties: { file: { type: 'string' }, line: { type: 'integer' }, symbol: { type: 'string' }, summary: { type: 'string' }, confidence: { type: 'string', enum: ['high', 'medium', 'low'] } } },
    evidence: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['kind', 'ref', 'claim'], properties: { kind: { type: 'string', enum: ['log', 'code', 'crg', 'config', 'wiki'] }, ref: { type: 'string' }, claim: { type: 'string' } } } },
    impact: { type: 'array', items: { type: 'string' } },
    fix: { type: 'object', additionalProperties: false, required: ['summary', 'changes'], properties: { summary: { type: 'string' }, changes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['file', 'description'], properties: { file: { type: 'string' }, description: { type: 'string' } } } } } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['verdict', 'findings', 'verified_claims'],
  properties: { verdict: { type: 'string', enum: ['pass', 'revise'] }, findings: { type: 'array', items: { type: 'string' } }, verified_claims: { type: 'array', items: { type: 'string' } } },
}

function isWindowsAbsolutePath(value) {
  return typeof value === 'string' && (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)/.test(value))
}
function hasTraversal(value) { return value.split(/[\\/]/).includes('..') }
function normalizePath(value) { return value.replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase() }
function isWithinRepo(repo, value) {
  return isWindowsAbsolutePath(repo) && isWindowsAbsolutePath(value) && !hasTraversal(value) && normalizePath(value).startsWith(`${normalizePath(repo)}\\`)
}
function repoPath(repo, ...parts) { return [repo.replace(/[\\/]+$/, ''), ...parts].join('\\') }
function isSafeRelativePath(value) { return typeof value === 'string' && value.trim() !== '' && !isWindowsAbsolutePath(value) && !hasTraversal(value) }

export default async function ({ agent, phase, log, args = {} }) {
  const { report, repo } = args
  phase('Validate')
  if (!isWindowsAbsolutePath(repo) || hasTraversal(repo)) return { aborted: true, stage: 'validate', error: 'repo 必须是 Windows 绝对路径' }
  if (typeof report !== 'string' || !report.trim()) return { aborted: true, stage: 'validate', error: 'report 不能为空' }
  const runId = `bug-${Date.now()}`
  const reportPath = args.reportPath || repoPath(repo, '.hiagent', 'runs', runId, 'report.md')
  if (!isWindowsAbsolutePath(reportPath) || !isWithinRepo(repo, reportPath)) return { aborted: true, stage: 'validate', error: 'reportPath 必须位于 repo 内' }

  phase('CRG')
  const gate = await agent(`确保当前代码图新鲜。repo=${JSON.stringify(repo)}。`, {
    agentType: 'code-graph', schema: GATE_SCHEMA, label: 'crg-gate',
  })
  if (!gate.ok) return { aborted: true, stage: 'crg', error: gate.error }
  if (gate.warning) log(gate.warning)

  phase('Knowledge')
  const wiki = await agent('执行 probe，探测 wiki-mcp。', { agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe' })
  let knowledge = { matches: [], total: 0 }
  if (wiki.available && wiki.capabilities.search) {
    knowledge = await agent(`执行 search。输入=${JSON.stringify({ query: { report, repo }, limit: 8 })}`, {
      agentType: 'wiki-gateway', schema: SEARCH_SCHEMA, label: 'wiki-search',
    })
  }

  let trace = null
  let verdict = { verdict: 'revise', findings: [], verified_claims: [] }
  let consensus = false
  for (let attempt = 1; attempt <= 3; attempt++) {
    phase('Trace')
    trace = await agent(`先执行 hiagent-run prepare，再定位并写报告。输入=${JSON.stringify({ repo, runId, symptom: report, knowledge, reportPath, reviewer_findings: verdict.findings })}`, {
      agentType: 'code-tracer', schema: TRACE_SCHEMA, label: `trace-${attempt}`,
    })
    if (!isWindowsAbsolutePath(trace.report_path) || !isWithinRepo(repo, trace.report_path) || !isSafeRelativePath(trace.root_cause.file)) {
      return { aborted: true, stage: 'trace-contract', error: 'trace 返回了仓外报告路径或非法源码相对路径' }
    }
    phase('Review')
    verdict = await agent(`独立审阅。输入=${JSON.stringify({ repo, symptom: report, trace, reportPath })}`, {
      agentType: 'code-tracer-reviewer', schema: VERDICT_SCHEMA, label: `review-${attempt}`,
    })
    if (verdict.verdict === 'pass') { consensus = true; break }
    log(`第 ${attempt} 轮需修订：${verdict.findings.join('；')}`)
  }

  phase('Report')
  return {
    aborted: false, run_id: runId, report_path: trace.report_path, root_cause: trace.root_cause,
    evidence: trace.evidence, fix: trace.fix,
    open_questions: [...trace.open_questions, ...(consensus ? [] : verdict.findings)],
    review: { consensus, ...verdict }, wiki: { available: wiki.available, matches: knowledge.total },
    next: '请人工审阅报告；确认根因和验证结果后再运行 exp-archive。',
  }
}
