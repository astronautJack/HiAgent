// flow-doc — 生成业务流 wiki：flow-writer 沿 CRG flows 取执行流→按生命周期分组→写页+error_index
// CRG 新鲜度由会话在启动前确认
export const meta = {
  name: 'flow-doc',
  description: '生成业务流 wiki（调用链+错误目录，给 diag 当直达电梯）',
  whenToUse: '用户要为代码仓生成业务流 wiki。传 args {repo, outDir?, flowPrefix?}。CRG 图须新鲜。',
  phases: [{ title: 'Write', detail: 'flow-writer 生成业务流页 + error_index' }],
}

export default async function ({ agent, phase, log, args }) {
  const { repo, outDir = '.', flowPrefix } = args

  phase('Write')
  const result = await agent(
    `为 ${repo} 生成业务流 wiki 到 ${outDir}。${flowPrefix ? `只生成 ${flowPrefix} 前缀。` : '全部流按前缀分组。'}\n` +
    `1. \`code-review-graph flows --repo ${repo}\` 列流，按前缀分组成生命周期。\n` +
    `2. 每生命周期：\`flow --name <入口> --source\` 拿调用链 → \`query callees_of\` 下钻 → Grep HiSysEvent/hilog/error code → Write ${outDir}/<biz-slug>.md（调用序列 mermaid + 逐步错误上报 + 错误目录表格 + frontmatter）。\n` +
    `3. Write ${outDir}/error_index.md（聚合错误目录，小，给 wiki-reader 索引检索）。\n` +
    `4. Write ${outDir}/README.md（生命周期清单 + last_sync_commit）。路径全相对仓根。只在 ${outDir} 下写。`,
    { agentType: 'flow-writer', label: 'writer' }
  )

  return { repo, outDir, flowPrefix: flowPrefix || null, pages: result }
}
