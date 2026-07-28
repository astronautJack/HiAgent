// exp-archive — 归档经验案例：exp-writer 写案例页 + 更新索引
export const meta = {
  name: 'exp-archive',
  description: '归档经验案例到 Wiki Markdown',
  whenToUse: '会话在 diag/bug-trace/feature-design 返回结果后，调用此 workflow 把案例归档。传 args {caseData, wiki}。',
  phases: [{ title: 'Archive', detail: 'exp-writer 写案例页 + 索引' }],
}

export default async function ({ agent, phase, log, args }) {
  const { caseData, wiki } = args

  phase('Archive')
  const result = await agent(
    `归档经验案例到 Wiki。wiki 根：${wiki}。\n案例数据：${JSON.stringify(caseData, null, 2)}\n\n` +
    `1. slug = ${caseData.module}-${caseData.type}-<简述>，Write ${wiki}/cases/<slug>.md（frontmatter + 问题/根因/证据/修复/相关）。\n` +
    `2. Read ${wiki}/cases/index.md → 追加条目 → Write 回去。\n` +
    `3. 更新 ${wiki}/README.md 统计。slug 用 kebab-case。`,
    { agentType: 'exp-writer', label: 'archive' }
  )
  log(`Archived: ${caseData.module}-${caseData.type}`)

  return result
}
