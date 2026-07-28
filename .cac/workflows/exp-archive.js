// exp-archive — 归档经验案例：归档门（只存 high）→ exp-writer 写案例页 + 更新索引
export const meta = {
  name: 'exp-archive',
  description: '归档经验案例到 Wiki Markdown（只存高置信）',
  whenToUse: '会话在 diag/bug-trace/feature-design 返回结果后，调用此 workflow 把案例归档。传 args {caseData, wiki}。caseData 须含 confidence + evidence + source_commit。',
  phases: [{ title: 'Gate', detail: '归档门：confidence=high?' }, { title: 'Archive', detail: 'exp-writer 写案例页 + 索引' }],
}

export default async function ({ agent, phase, log, args }) {
  const { caseData, wiki } = args

  // 归档质量门：只存 high confidence（CTIM-Rover 警示——噪声 case 反而降性能）
  phase('Gate')
  if (caseData.confidence !== 'high') {
    log(`归档门拦截：confidence=${caseData.confidence}（非 high），不归档避免噪声污染经验库`)
    return { archived: false, reason: 'low_confidence', confidence: caseData.confidence }
  }

  phase('Archive')
  const result = await agent(
    `归档经验案例到 Wiki。wiki 根：${wiki}。\n案例数据：${JSON.stringify(caseData, null, 2)}\n\n` +
    `1. slug = ${caseData.module}-${caseData.type}-<简述>，Write ${wiki}/cases/<slug>.md（frontmatter 含 source_commit/evidence/confidence/created_from + 问题/根因/证据/修复/验证/相关章节）。\n` +
    `2. Read ${wiki}/cases/index.md → 追加条目（含置信度列）→ Write 回去。\n` +
    `3. 更新 ${wiki}/README.md 统计。slug 用 kebab-case。证据链别丢（frontmatter evidence + source_commit 是过期检测依据）。`,
    { agentType: 'exp-writer', label: 'archive' }
  )
  log(`Archived: ${caseData.module}-${caseData.type} (confidence=high)`)

  return { archived: true, ...result }
}
