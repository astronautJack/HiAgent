// exp-search — 检索经验：wiki-reader 查索引 + 全文匹配历史案例
export const meta = {
  name: 'exp-search',
  description: '检索经验 Wiki：查历史案例',
  whenToUse: '用户问"这错见过吗"/"查历史案例"。传 args {query, wiki}。',
  phases: [{ title: 'Search', detail: 'wiki-reader 查索引 + 全文' }],
}

const SEARCH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['matches', 'total'],
  properties: {
    matches: { type: 'array', items: { type: 'object', properties: {
      slug: { type: 'string' }, title: { type: 'string' }, summary: { type: 'string' },
      confidence: { type: 'string', enum: ['high', 'medium', 'low'] }, path: { type: 'string' },
    } } },
    total: { type: 'integer' },
  },
}

export default async function ({ agent, phase, log, args }) {
  const { query, wiki } = args

  phase('Search')
  const result = await agent(
    `在经验 Wiki 检索。wiki 根：${wiki}。查询："${query}"\n\n` +
    `1. Read ${wiki}/cases/index.md，Grep 匹配查询关键词。\n` +
    `2. 命中 → Read 对应案例页，返回标题+摘要+置信度+路径。\n` +
    `3. 未命中 → 在 ${wiki}/cases/*.md 批量 Grep 全文搜。\n` +
    `按置信度降序返回。`,
    { agentType: 'wiki-reader', schema: SEARCH_SCHEMA, label: 'search' }
  )
  log(`Search: ${result.total} matches for "${query}"`)

  return result
}
