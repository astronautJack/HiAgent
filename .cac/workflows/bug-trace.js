// bug-trace — BUG 定位（bug 报告驱动）：wiki-reader 取预期 → code-tracer 回溯 → 报告
// CRG 新鲜度由会话在启动前确认
export const meta = {
  name: 'bug-trace',
  description: 'BUG 定位（bug 报告驱动，非日志）',
  whenToUse: '用户给了 bug 报告/失败现象（非日志），要找根因。传 args {report, repo, wiki?}。CRG 图须新鲜。',
  phases: [
    { title: 'Read', detail: 'wiki-reader 取预期行为' },
    { title: 'Trace', detail: 'code-tracer 反向回溯' },
    { title: 'Report', detail: '根因报告' },
  ],
}

const TRACE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['file', 'line', 'confidence', 'evidence'],
  properties: {
    file: { type: 'string' }, line: { type: 'integer' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    evidence: { type: 'array', items: { type: 'object', properties: { kind: { type: 'string' }, ref: { type: 'string' } } } },
    fixSuggestion: { type: 'string' },
  },
}

export default async function ({ agent, phase, log, args }) {
  const { report, repo, wiki } = args

  phase('Read')
  let context = null
  if (wiki) {
    context = await agent(
      `读 ${wiki} 取预期行为与涉及模块。bug 报告："${report}"。用报告里的符号当信号匹配索引。`,
      { agentType: 'wiki-reader', label: 'wiki' }
    )
  } else {
    log('提示：本仓无 wiki，本次定位无历史经验加持；可先跑 /wiki-doc、/wiki-flow 生成后再定位')
  }

  phase('Trace')
  phase('Report')
  const trace = await agent(
    `BUG 报告："${report}"\nrepo: ${repo}（CRG 图已新鲜）\n${context ? 'wiki 预期: ' + JSON.stringify(context) : '无 wiki'}\n` +
    `从报告里的症状符号沿 CRG callers_of 反向回溯到偏离点，定位 file:line 根因 + 证据链 + 修复建议。`,
    { agentType: 'code-tracer', schema: TRACE_SCHEMA, label: 'trace' }
  )
  log(`Root cause: ${trace.file}:${trace.line}, confidence=${trace.confidence}`)

  return { repo, wiki, ...trace }
}
