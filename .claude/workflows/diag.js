// diag — 日志问题定位：log-parser 压日志 → wiki-reader 取上下文 → code-tracer 回溯 → critic 复核 → 报告
// CRG 新鲜度由会话在启动前确认
export const meta = {
  name: 'diag',
  description: '日志问题定位到代码行',
  whenToUse: '用户给了日志文件/文本，要定位到代码行。传 args {logPath|logText, repo, wiki?, logFormat?}。CRG 图须新鲜。',
  phases: [
    { title: 'Triage', detail: 'log-parser 压日志' },
    { title: 'Context', detail: 'wiki-reader 取契约' },
    { title: 'Trace', detail: 'code-tracer 反向回溯' },
    { title: 'Critic', detail: '自校正复核（≤3）' },
    { title: 'Report', detail: '汇总报告' },
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
  required: ['file', 'line', 'confidence', 'evidence'],
  properties: {
    file: { type: 'string' }, line: { type: 'integer' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    evidence: { type: 'array', items: { type: 'object', properties: { kind: { type: 'string' }, ref: { type: 'string' } } } },
  },
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['confident', 'feedback'],
  properties: { confident: { type: 'boolean' }, feedback: { type: 'string' } },
}

export default async function ({ agent, phase, log, args }) {
  const { logPath, logText, repo, wiki, logFormat = 'auto' } = args

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
    log('提示：本仓无 flow-wiki（error_index），本次定位无历史经验加持；可先跑 /wiki-flow 生成后再定位')
  }

  let trace = null
  for (let attempt = 0; attempt < 3; attempt++) {
    phase('Trace')
    trace = await agent(
      `沿 CRG 调用图反向回溯定位 file:line。repo: ${repo}（图已新鲜）。\ndigest: ${JSON.stringify(digest)}\n${context ? 'wiki 契约: ' + JSON.stringify(context) : '无 wiki，退回源码'}`,
      { agentType: 'code-tracer', schema: TRACE_SCHEMA, label: `trace-${attempt}` }
    )
    phase('Critic')
    const verdict = await agent(
      `复核证据链是否闭合。trace: ${JSON.stringify(trace)}。confident=true 放行；弱则 feedback 指出缺哪环。`,
      { schema: VERDICT_SCHEMA, label: `critic-${attempt}` }
    )
    if (verdict.confident) { log(`Attempt ${attempt}: confident`); break }
    log(`Attempt ${attempt}: weak — ${verdict.feedback}`)
  }

  phase('Report')
  return { file: trace.file, line: trace.line, confidence: trace.confidence, evidence: trace.evidence, claimed_error: digest.claimed_error, digest_preview: digest.preview }
}
