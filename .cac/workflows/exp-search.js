// exp-search — wiki-mcp 权限内检索，历史经验只作候选
export const meta = {
  name: 'exp-search',
  description: '从当前用户有权限的公司 wiki 中检索历史案例',
  whenToUse: '传 args {query, repo?, limit?}',
  phases: [{ title: 'Wiki', detail: '探测服务' }, { title: 'Search', detail: '权限内有界检索' }, { title: 'Validate', detail: '对照当前代码检查过期' }],
}

const PROBE_SCHEMA = { type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'], properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } } }
const SEARCH_SCHEMA = { type: 'object', additionalProperties: false, required: ['matches', 'total'], properties: { matches: { type: 'array', items: { type: 'object' } }, total: { type: 'integer' } } }
const VALIDATED_SCHEMA = { type: 'object', additionalProperties: false, required: ['matches', 'total'], properties: { matches: { type: 'array', items: { type: 'object' } }, total: { type: 'integer' } } }
function isWindowsAbsolutePath(value) { return typeof value === 'string' && (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)/.test(value)) }
function hasTraversal(value) { return value.split(/[\\/]/).includes('..') }

export default async function ({ agent, phase, args = {} }) {
  const { query, repo = null, limit = 8 } = args
  if (typeof query !== 'string' || !query.trim()) return { matches: [], total: 0, error: 'query 不能为空' }
  if (repo && (!isWindowsAbsolutePath(repo) || hasTraversal(repo))) return { matches: [], total: 0, error: 'repo 必须是 Windows 绝对路径' }
  const boundedLimit = Math.max(1, Math.min(Number(limit) || 8, 20))

  phase('Wiki')
  const probe = await agent('执行 probe，探测 wiki-mcp。', { agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe' })
  if (!probe.available || !probe.capabilities.search) return { matches: [], total: 0, error: probe.error || 'wiki-mcp 不可用或无检索能力' }

  phase('Search')
  const result = await agent(`执行 search。输入=${JSON.stringify({ query: { text: query, repo }, limit: boundedLimit })}`, {
    agentType: 'wiki-gateway', schema: SEARCH_SCHEMA, label: 'wiki-search',
  })
  let validated = result
  if (repo) {
    phase('Validate')
    validated = await agent(`action=validate-search。对照当前仓验证搜索结果 metadata。输入=${JSON.stringify({ repo, matches: result.matches })}`, {
      agentType: 'experience-curator', schema: VALIDATED_SCHEMA, label: 'validate-search',
    })
  }
  return {
    ...validated,
    warning: '历史经验仅是候选；应用到修复前必须对照当前源码重新验证。',
  }
}
