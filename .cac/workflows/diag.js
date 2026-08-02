// diag — 日志定位：确定性 digest → 权限内经验检索 → 证据回溯 → 独立审阅
export const meta = {
  name: 'diag',
  description: '把日志定位到代码根因行，附证据链、修复建议和独立审阅结论',
  whenToUse: '传 args {logPath|logText, repo, logFormat?, drainMode?, profile?, reportPath?}',
  phases: [
    { title: 'Validate', detail: '校验输入并准备运行目录' },
    { title: 'CRG', detail: '确保代码图新鲜' },
    { title: 'Triage', detail: '生成 hiagent.log-digest.v1' },
    { title: 'Knowledge', detail: '通过 wiki-mcp 检索权限内经验' },
    { title: 'Trace', detail: '独立 investigator 定位' },
    { title: 'Review', detail: '隔离上下文的对抗式核验，最多三轮' },
    { title: 'Report', detail: '第三个 subagent 仅渲染报告' },
  ],
}

const GATE_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['ok', 'error', 'warning'],
  properties: { ok: { type: 'boolean' }, error: { type: 'string' }, warning: { type: 'string' } },
}

const DIGEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'raw_file', 'log_format', 'drain_mode', 'line_count', 'claimed_error', 'symbols', 'clusters', 'hisysevent_anchors', 'fault_frames', 'key_lines', 'truncated'],
  properties: {
    schema_version: { type: 'string', enum: ['hiagent.log-digest.v1'] },
    raw_file: { type: 'string' }, log_format: { type: 'string' }, drain_mode: { type: 'string', enum: ['learn', 'inference'] }, line_count: { type: 'integer' },
    claimed_error: { type: ['string', 'null'] },
    symbols: { type: 'array', items: { type: 'object' } },
    clusters: { type: 'array', items: { type: 'object' } },
    hisysevent_anchors: { type: 'array', items: { type: 'object' } },
    fault_frames: { type: 'array', items: { type: 'object' } },
    key_lines: { type: 'array', items: { type: 'integer' } },
    truncated: { type: 'object' },
  },
}

const PROBE_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'],
  properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } },
}

const SEARCH_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['matches', 'total'],
  properties: { matches: { type: 'array', items: { type: 'object' } }, total: { type: 'integer' } },
}

const TRACE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'root_cause', 'evidence', 'impact', 'fix', 'open_questions'],
  properties: {
    schema_version: { type: 'string', enum: ['hiagent.trace.v1'] },
    root_cause: {
      type: 'object', additionalProperties: false, required: ['file', 'line', 'symbol', 'summary', 'confidence'],
      properties: { file: { type: 'string' }, line: { type: 'integer' }, symbol: { type: 'string' }, summary: { type: 'string' }, confidence: { type: 'string', enum: ['high', 'medium', 'low'] } },
    },
    evidence: {
      type: 'array', items: { type: 'object', additionalProperties: false, required: ['kind', 'ref', 'claim'], properties: { kind: { type: 'string', enum: ['log', 'code', 'crg', 'config', 'wiki'] }, ref: { type: 'string' }, claim: { type: 'string' } } } },
    impact: { type: 'array', items: { type: 'string' } },
    fix: { type: 'object', additionalProperties: false, required: ['summary', 'changes'], properties: { summary: { type: 'string' }, changes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['file', 'description'], properties: { file: { type: 'string' }, description: { type: 'string' } } } } } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['verdict', 'independent_summary', 'contradictions', 'findings', 'verified_claims'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'revise'] },
    independent_summary: { type: 'string' },
    contradictions: { type: 'array', items: { type: 'string' } },
    findings: { type: 'array', items: { type: 'string' } },
    verified_claims: { type: 'array', items: { type: 'string' } },
  },
}
const REPORT_SCHEMA = { type: 'object', additionalProperties: false, required: ['written', 'report_path', 'error'], properties: { written: { type: 'boolean' }, report_path: { type: 'string' }, error: { type: 'string' } } }

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
  const { logPath, logText, repo, logFormat = 'auto', drainMode = 'learn' } = args
  phase('Validate')
  if (!isWindowsAbsolutePath(repo) || hasTraversal(repo)) return { aborted: true, stage: 'validate', error: 'repo 必须是 Windows 绝对路径' }
  if ((!logPath && !logText) || (logPath && logText)) return { aborted: true, stage: 'validate', error: 'logPath 与 logText 必须且只能提供一个' }
  if (logText && logText.length > 20000) return { aborted: true, stage: 'validate', error: '日志文本超过 20000 字符，请先保存为文件并传 logPath，避免灌入 agent 上下文' }
  if (logPath && (!isWindowsAbsolutePath(logPath) || hasTraversal(logPath))) return { aborted: true, stage: 'validate', error: 'logPath 必须是 Windows 绝对路径' }
  if (!['auto', 'harmony', 'generic'].includes(logFormat)) return { aborted: true, stage: 'validate', error: 'logFormat 非法' }
  if (!['learn', 'inference'].includes(drainMode)) return { aborted: true, stage: 'validate', error: 'drainMode 非法' }

  const runId = `diag-${Date.now()}`
  const workDir = repoPath(repo, '.hiagent', 'runs', runId)
  const reportPath = args.reportPath || repoPath(workDir, 'report.md')
  const repoName = repo.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || 'repo'
  const profile = args.profile || `hiagent-${repoName}`
  if (!isWindowsAbsolutePath(reportPath) || !isWithinRepo(repo, reportPath)) {
    return { aborted: true, stage: 'validate', error: 'reportPath 必须位于 repo 内' }
  }

  phase('CRG')
  const gate = await agent(
    `确保 CRG 图可用且对应当前 HEAD。repo=${JSON.stringify(repo)}。缺失或过时则 build；失败返回明确错误。`,
    { agentType: 'code-graph', schema: GATE_SCHEMA, label: 'crg-gate' }
  )
  if (!gate.ok) return { aborted: true, stage: 'crg', error: gate.error }
  if (gate.warning) log(gate.warning)

  phase('Triage')
  const digest = await agent(
    `先执行 hiagent-run prepare，再把输入转换为唯一日志契约并原样返回。` +
    `\ninput=${JSON.stringify({ repo, runId, logPath: logPath || null, logText: logText || null, logFormat, drainMode, profile, workDir })}`,
    { agentType: 'log-parser', schema: DIGEST_SCHEMA, label: 'triage' }
  )

  phase('Knowledge')
  const wiki = await agent('执行 probe，探测服务名准确为 wiki-mcp 的可用能力。', {
    agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe',
  })
  let knowledge = { matches: [], total: 0 }
  if (wiki.available && wiki.capabilities.search) {
    const query = {
      claimed_error: digest.claimed_error,
      symbols: digest.symbols.slice(0, 30),
      templates: digest.clusters.slice(0, 10).map(c => c.template),
      repo,
    }
    knowledge = await agent(`执行 search。输入=${JSON.stringify({ query, limit: 8 })}`, {
      agentType: 'wiki-gateway', schema: SEARCH_SCHEMA, label: 'wiki-search',
    })
  } else {
    log(`wiki-mcp 不可用，本次继续按源码定位：${wiki.error || '无 search 能力'}`)
  }

  let trace = null
  let verdict = { verdict: 'revise', independent_summary: '', contradictions: [], findings: [], verified_claims: [] }
  let consensus = false
  for (let attempt = 1; attempt <= 3; attempt++) {
    phase('Trace')
    trace = await agent(
      `你是独立 investigator，只定位并返回结构化 trace，禁止写报告。输入=${JSON.stringify({ repo, digest, knowledge, reviewer_findings: [...verdict.findings, ...verdict.contradictions] })}`,
      { agentType: 'code-tracer', schema: TRACE_SCHEMA, label: `trace-${attempt}` }
    )
    if (!isSafeRelativePath(trace.root_cause.file)) {
      return { aborted: true, stage: 'trace-contract', error: 'trace 返回了非法源码相对路径' }
    }
    phase('Review')
    verdict = await agent(
      `你是隔离上下文的 adversarial reviewer。报告尚未生成；先独立调查，再核验 trace。输入=${JSON.stringify({ repo, digest, trace })}`,
      { agentType: 'code-tracer-reviewer', schema: VERDICT_SCHEMA, label: `review-${attempt}` }
    )
    if (verdict.verdict === 'pass') { consensus = true; break }
    log(`第 ${attempt} 轮需修订：${verdict.findings.join('；')}`)
  }

  phase('Report')
  const reportResult = await agent(
    `只把已结束的调查与复核结果渲染到报告，禁止改变结论。输入=${JSON.stringify({ repo, runId, reportPath, symptom: digest.claimed_error, digest, trace, verdict, consensus })}`,
    { agentType: 'trace-report-writer', schema: REPORT_SCHEMA, label: 'report-writer' }
  )
  if (!reportResult.written || !isWindowsAbsolutePath(reportResult.report_path) || !isWithinRepo(repo, reportResult.report_path)) {
    return { aborted: true, stage: 'report', error: reportResult.error || '报告未写入 repo 运行目录' }
  }
  return {
    aborted: false,
    run_id: runId,
    report_path: reportResult.report_path,
    root_cause: trace.root_cause,
    evidence: trace.evidence,
    fix: trace.fix,
    open_questions: [...trace.open_questions, ...(consensus ? [] : [...verdict.findings, ...verdict.contradictions])],
    review: { consensus, ...verdict },
    wiki: { available: wiki.available, matches: knowledge.total },
    next: '请人工审阅报告；确认根因和验证结果后再运行 exp-archive。',
  }
}
