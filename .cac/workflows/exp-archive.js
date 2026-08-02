// exp-archive — 人工确认后的经验质量门 → wiki-mcp 幂等写入
export const meta = {
  name: 'exp-archive',
  description: '把已验证案例幂等沉淀到公司 wiki',
  whenToUse: '仅在人确认结果后调用。传 args {caseData, repo, humanConfirmed}',
  phases: [
    { title: 'Curate', detail: '质量门与知识页生成' },
    { title: 'Wiki', detail: '探测 wiki-mcp' },
    { title: 'Publish', detail: '幂等写入并回读核验' },
  ],
}

const PAGE_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['ready', 'reasons', 'page'],
  properties: {
    ready: { type: 'boolean' },
    reasons: { type: 'array', items: { type: 'string' } },
    page: {
      type: ['object', 'null'], additionalProperties: false,
      required: ['external_id', 'title', 'content', 'metadata'],
      properties: {
        external_id: { type: 'string' },
        title: { type: 'string' }, content: { type: 'string' }, metadata: { type: 'object' },
      },
    },
  },
}
const PROBE_SCHEMA = { type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'], properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } } }
const WRITE_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['written', 'action', 'id', 'title', 'url', 'verified', 'error'],
  properties: { written: { type: 'boolean' }, action: { type: 'string', enum: ['created', 'updated', 'none'] }, id: { type: 'string' }, title: { type: 'string' }, url: { type: 'string' }, verified: { type: 'boolean' }, error: { type: 'string' } },
}

function isWindowsAbsolutePath(value) { return typeof value === 'string' && (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)/.test(value)) }
function hasTraversal(value) { return value.split(/[\\/]/).includes('..') }

export default async function ({ agent, phase, args = {} }) {
  const { caseData, repo, humanConfirmed = false } = args
  if (!isWindowsAbsolutePath(repo) || hasTraversal(repo)) return { archived: false, stage: 'validate', error: 'repo 必须是 Windows 绝对路径' }
  if (!caseData || typeof caseData !== 'object') return { archived: false, stage: 'validate', error: 'caseData 必须是对象' }
  if (humanConfirmed !== true) return { archived: false, stage: 'quality-gate', reasons: ['humanConfirmed 必须为 true'] }
  if (caseData.confidence !== 'high') return { archived: false, stage: 'quality-gate', reasons: ['confidence 必须为 high'] }
  if (!Array.isArray(caseData.evidence) || caseData.evidence.length === 0) return { archived: false, stage: 'quality-gate', reasons: ['至少需要一条结构化证据'] }
  if (!caseData.validation) return { archived: false, stage: 'quality-gate', reasons: ['缺少验证证据'] }
  if (JSON.stringify(caseData).length > 100000) return { archived: false, stage: 'validate', error: 'caseData 过大；只传脱敏摘要和证据引用，不传完整日志' }

  phase('Curate')
  const curated = await agent(`执行经验归档质量门并生成页面。输入=${JSON.stringify({ caseData, repo, human_confirmed: humanConfirmed })}`, {
    agentType: 'experience-curator', schema: PAGE_SCHEMA, label: 'curate',
  })
  if (!curated.ready) return { archived: false, stage: 'quality-gate', reasons: curated.reasons }
  if (typeof curated.page.external_id !== 'string' || !curated.page.external_id.startsWith('hiagent:')) {
    return { archived: false, stage: 'quality-gate', error: 'external_id 必须是稳定的 hiagent: 幂等键' }
  }

  phase('Wiki')
  const probe = await agent('执行 probe，探测 wiki-mcp。', { agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe' })
  if (!probe.available || !probe.capabilities.write) {
    return { archived: false, stage: 'wiki', error: probe.error || 'wiki-mcp 不可用或无写入能力', page: curated.page }
  }

  phase('Publish')
  const result = await agent(`执行 upsert 并回读核验。输入=${JSON.stringify({ ...curated.page, target: { route: caseData.created_from || 'default' } })}`, {
    agentType: 'wiki-gateway', schema: WRITE_SCHEMA, label: 'wiki-upsert',
  })
  return {
    archived: result.written && result.verified,
    stage: result.written && result.verified ? 'complete' : 'verify',
    ...result,
    external_id: curated.page.external_id,
  }
}
