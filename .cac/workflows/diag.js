// diag — 日志问题定位：log-parser 压日志 → wiki-reader 取上下文 → code-tracer 写报告 → reviewer 独立审 loop → 报告
// CRG 新鲜度由会话在启动前确认
export const meta = {
  name: 'diag',
  description: '日志问题定位到代码行',
  whenToUse: '用户给了日志文件/文本，要定位到代码行。传 args {logPath|logText, repo, wiki?, logFormat?, reportPath?}。CRG 图须新鲜。',
  phases: [
    { title: 'Triage', detail: 'log-parser 压日志' },
    { title: 'Context', detail: 'wiki-reader 取契约' },
    { title: 'Trace', detail: 'code-tracer 写报告' },
    { title: 'Review', detail: 'reviewer 独立审（≤3 loop）' },
    { title: 'Report', detail: '呈现报告' },
  ],
}

const DIGEST_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['raw_file', 'claimed_error', 'symbols', 'hisysevent_anchors', 'preview'],
  properties: {
    raw_file: { type: 'string' },
    claimed_error: { type: 'string' },
    symbols: { type: 'array', items: { type: 'object', properties: { domain: { type: 'string' }, tag: { type: 'string' } } } },
    hisysevent_anchors: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, file_line: { type: 'integer' }, caller: { type: 'string' } } } },
    preview: { type: 'object', properties: { raw_file: { type: 'string' }, key_lines: { type: 'array', items: { type: 'integer' } } } },
  },
}
const CONTEXT_SCHEMA = { type: ['object', 'null'], properties: { matched: { type: 'array' } } }
const TRACE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['report_path', 'file', 'line', 'confidence'],
  properties: {
    report_path: { type: 'string' },
    file: { type: 'string' }, line: { type: 'integer' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'revise'] },
    findings: { type: 'array', items: { type: 'string' } },
  },
}

export default async function ({ agent, phase, log, args }) {
  const { logPath, logText, repo, wiki, logFormat = 'auto', reportPath = './diag-report.md' } = args

  phase('Triage')
  const digest = await agent(
    `压日志成 digest。日志：${logPath || '(文本) ' + logText}。格式：${logFormat}。跑 \`logscope-triage <file> --top 50 --json --profile diag --log-format ${logFormat}\`。`,
    { agentType: 'log-parser', schema: DIGEST_SCHEMA, label: 'triage' }
  )
  log(`Digest: ${digest.symbols.length} symbols, claimed="${digest.claimed_error}"`)

  phase('Context')
  let context = null
  if (wiki) {
    context = await agent(
      `读 ${wiki}/error_index.md 匹配 digest 错误信号。符号：${JSON.stringify(digest.symbols)}；claimed：${digest.claimed_error}。未命中返 null。`,
      { agentType: 'wiki-reader', schema: CONTEXT_SCHEMA, label: 'wiki' }
    )
  } else {
    log('提示：本仓无业务流页（error_index），本次定位无历史经验加持；可先跑 /flow-doc 生成后再定位')
  }

  let trace = null
  let verdict = null
  let consensus = false
  for (let attempt = 0; attempt < 3; attempt++) {
    phase('Trace')
    const findingsInput = (attempt > 0 && verdict) ? `\nreviewer 上一轮 findings（据此修订）：${JSON.stringify(verdict.findings)}` : ''
    trace = await agent(
      `沿 CRG 调用图反向回溯定位 file:line + 写报告。repo: ${repo}（图已新鲜）。report_path: ${reportPath}。\ndigest: ${JSON.stringify(digest)}\n${context ? 'wiki 契约: ' + JSON.stringify(context) : '无 wiki，退回源码'}${findingsInput}\n沿 callers_of 回溯到 file:line 根因 + 证据链（计数用 digest cluster size）+ 构建开关（涉剥离时）+ 修复建议（具体文件+确切语法），Write 报告到 ${reportPath}，返 report_path + file/line/confidence。`,
      { agentType: 'code-tracer', schema: TRACE_SCHEMA, label: `trace-${attempt}` }
    )
    phase('Review')
    verdict = await agent(
      `独立审报告 ${reportPath}（repo: ${repo}，digest: ${JSON.stringify(digest)}）。重跑 CRG/grep + 重读源码 + 对 digest 验计数 + 验修复可 apply，返 verdict（pass/revise）+ findings。`,
      { agentType: 'code-tracer-reviewer', schema: VERDICT_SCHEMA, label: `review-${attempt}` }
    )
    if (verdict.verdict === 'pass') { log(`Attempt ${attempt}: pass`); consensus = true; break }
    log(`Attempt ${attempt}: revise — ${JSON.stringify(verdict.findings)}`)
  }

  if (!consensus) {
    log('max loop 未共识，追加存疑点')
    await agent(
      `max loop 未共识。在 ${reportPath} 末尾加 \`## 存疑点\` 段，列 reviewer 指出但未解决的点：${JSON.stringify(verdict.findings)}。`,
      { agentType: 'code-tracer', label: 'open-questions' }
    )
  }

  phase('Report')
  return { report_path: reportPath, file: trace.file, line: trace.line, confidence: trace.confidence, claimed_error: digest.claimed_error, consensus, has_open_questions: !consensus }
}
