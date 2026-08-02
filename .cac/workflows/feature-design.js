// feature-design — 当前源码 + CRG + wiki 经验候选 → 可执行设计 → 人审
export const meta = {
  name: 'feature-design',
  description: '生成带源码触点、风险和测试计划的结构化设计',
  whenToUse: '传 args {requirement, repo}',
  phases: [{ title: 'Validate', detail: '校验输入' }, { title: 'CRG', detail: '确保图新鲜' }, { title: 'Knowledge', detail: '检索架构约定' }, { title: 'Design', detail: '生成设计交人审' }],
}

const GATE_SCHEMA = { type: 'object', additionalProperties: false, required: ['ok', 'error', 'warning'], properties: { ok: { type: 'boolean' }, error: { type: 'string' }, warning: { type: 'string' } } }
const PROBE_SCHEMA = { type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'], properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } } }
const SEARCH_SCHEMA = { type: 'object', additionalProperties: false, required: ['matches', 'total'], properties: { matches: { type: 'array', items: { type: 'object' } }, total: { type: 'integer' } } }
const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'summary', 'assumptions', 'changes', 'risks', 'test_plan', 'knowledge_updates'],
  properties: {
    schema_version: { type: 'string', enum: ['hiagent.feature-design.v1'] }, summary: { type: 'string' },
    assumptions: { type: 'array', items: { type: 'string' } },
    changes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['file', 'symbol', 'description', 'type'], properties: { file: { type: 'string' }, symbol: { type: 'string' }, description: { type: 'string' }, type: { type: 'string', enum: ['add', 'modify', 'delete'] } } } },
    risks: { type: 'array', items: { type: 'string' } }, test_plan: { type: 'array', items: { type: 'string' } },
    knowledge_updates: { type: 'array', items: { type: 'string' } },
  },
}
function isWindowsAbsolutePath(value) { return typeof value === 'string' && (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)/.test(value)) }
function hasTraversal(value) { return value.split(/[\\/]/).includes('..') }
function isSafeRelativePath(value) { return typeof value === 'string' && value.trim() !== '' && !isWindowsAbsolutePath(value) && !hasTraversal(value) }

export default async function ({ agent, phase, log, args = {} }) {
  const { requirement, repo } = args
  phase('Validate')
  if (!isWindowsAbsolutePath(repo) || hasTraversal(repo)) return { aborted: true, stage: 'validate', error: 'repo 必须是 Windows 绝对路径' }
  if (typeof requirement !== 'string' || !requirement.trim()) return { aborted: true, stage: 'validate', error: 'requirement 不能为空' }

  phase('CRG')
  const gate = await agent(`确保 CRG 图对应当前 HEAD。repo=${JSON.stringify(repo)}`, { agentType: 'code-graph', schema: GATE_SCHEMA, label: 'crg-gate' })
  if (!gate.ok) return { aborted: true, stage: 'crg', error: gate.error }
  if (gate.warning) log(gate.warning)

  phase('Knowledge')
  const probe = await agent('执行 probe，探测 wiki-mcp。', { agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe' })
  let knowledge = { matches: [], total: 0 }
  if (probe.available && probe.capabilities.search) {
    knowledge = await agent(`执行 search。输入=${JSON.stringify({ query: { requirement, repo, kinds: ['architecture', 'convention', 'experience'] }, limit: 8 })}`, {
      agentType: 'wiki-gateway', schema: SEARCH_SCHEMA, label: 'wiki-search',
    })
  }

  phase('Design')
  const design = await agent(`生成设计。输入=${JSON.stringify({ requirement, repo, knowledge })}`, {
    agentType: 'feature-planner', schema: DESIGN_SCHEMA, label: 'planner',
  })
  if (!design.changes.every(change => isSafeRelativePath(change.file))) {
    return { aborted: true, stage: 'design-contract', error: '设计包含仓外或非法相对路径' }
  }
  return { aborted: false, requirement, repo, design, wiki: { available: probe.available, matches: knowledge.total }, next: '请人工审阅；批准后把 design 原样传给 feature-implement，并设置 approved=true。' }
}
