// wiki-doc — 生成架构文档：code-graph 建图+结构页 → arch-wiki-writer 下钻源码写可读架构文档（增量）
export const meta = {
  name: 'wiki-doc',
  description: '生成 DeepWiki 风格架构 wiki（知识库级可读文档 + mermaid）',
  whenToUse: '用户要为代码仓生成可读架构文档。传 args {repo, outDir?, community?}。',
  phases: [
    { title: 'Prepare', detail: 'code-graph 建图 + 结构页' },
    { title: 'Write', detail: 'arch-wiki-writer 逐社区写架构文档' },
  ],
}

export default async function ({ agent, phase, log, args }) {
  const { repo, outDir = repo + '/docs/wiki', community } = args

  phase('Prepare')
  await agent(
    `对 ${repo} 跑 CRG build（存在则 update）+ \`code-review-graph wiki --repo ${repo}\` 出结构页。`,
    { agentType: 'code-graph', label: 'graph', phase: 'Prepare' }
  )

  phase('Write')
  const result = await agent(
    `为 ${repo} 生成架构 wiki 到 ${outDir}。${community ? `只写社区 "${community}"。` : '全量或增量（首次全量，已有按 last_sync_commit 增量）。'}\n` +
    `code-graph 已出结构页在 ${repo}/.code-review-graph/wiki/。Read 结构页 Members → 下钻源码 → Write ${outDir}/<slug>.md（职责/组成/原理/流程+mermaid/模块关系/注意点/锚点 + frontmatter）。Write ${outDir}/README.md 索引。只在 ${outDir} 下写。`,
    { agentType: 'arch-wiki-writer', label: 'writer', phase: 'Write' }
  )

  return { repo, outDir, community: community || null, pages: result }
}
