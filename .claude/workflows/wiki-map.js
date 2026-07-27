// wiki-map — 生成 CRG 结构 wiki：code-graph 建图+wiki 子命令 → arch-wiki-writer 同步到目标目录
export const meta = {
  name: 'wiki-map',
  description: '生成 CRG 结构 wiki（纯结构，快）',
  whenToUse: '用户要生成/刷新代码仓结构 wiki。传 args {repo, wikiPath?}。',
  phases: [
    { title: 'Build', detail: 'code-graph 建图 + wiki 子命令' },
    { title: 'Sync', detail: 'arch-wiki-writer 同步结构页' },
  ],
}

export default async function ({ agent, phase, log, args }) {
  const { repo, wikiPath = repo + '/docs/wiki' } = args

  phase('Build')
  await agent(
    `对 ${repo} 跑 CRG build（已存在则 update）+ \`code-review-graph wiki --repo ${repo}\` 生成结构页到 <repo>/.code-review-graph/wiki/。`,
    { agentType: 'code-graph', label: 'graph', phase: 'Build' }
  )

  phase('Sync')
  const result = await agent(
    `把 ${repo}/.code-review-graph/wiki/ 下的结构页同步到 ${wikiPath}。覆盖前检查既有文件。返回写入页数。`,
    { agentType: 'arch-wiki-writer', label: 'sync', phase: 'Sync' }
  )

  return { repo, wikiPath, pages: result }
}
