// graph-sync — 生成 CRG 结构 wiki：code-graph 建图 + wiki 子命令 + sync 到目标目录（纯结构，无 LLM 介入）
export const meta = {
  name: 'graph-sync',
  description: '生成 CRG 结构 wiki（纯结构，快）',
  whenToUse: '用户要生成/刷新代码仓结构 wiki。传 args {repo, wikiPath?}。',
  phases: [
    { title: 'Build', detail: 'code-graph 建图 + wiki 子命令 + sync' },
  ],
}

export default async function ({ agent, phase, log, args }) {
  const { repo, wikiPath = repo + '/docs/wiki' } = args

  phase('Build')
  const result = await agent(
    `对 ${repo} 跑 CRG build（已存在则 update）+ \`code-review-graph wiki --repo ${repo}\` 生成结构页到 <repo>/.code-review-graph/wiki/，然后 sync 到 ${wikiPath}（覆盖前 Read 检查既有文件，diff 交人审）。返回写入页数。`,
    { agentType: 'code-graph', label: 'graph' }
  )

  return { repo, wikiPath, pages: result }
}
