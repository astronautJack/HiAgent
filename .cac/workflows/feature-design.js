// feature-design — 需求→设计：feature-planner 读 wiki+CRG 图出设计 → 返回交人审
// 人审 checkpoint 在 workflow 返回后；批准后启动 feature-implement（未来）
export const meta = {
  name: 'feature-design',
  description: '需求→设计（feature 流水线第 1 步）',
  whenToUse: '用户要按需求做端到端实现，先出设计。传 args {requirement, repo, wiki}。',
  phases: [{ title: 'Design', detail: 'feature-planner 出设计' }],
}

const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['summary', 'changes', 'risks', 'testPlan'],
  properties: {
    summary: { type: 'string' },
    changes: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, description: { type: 'string' }, type: { type: 'string', enum: ['add', 'modify', 'delete'] } } } },
    risks: { type: 'array', items: { type: 'string' } },
    testPlan: { type: 'array', items: { type: 'string' } },
    wikiPagesToUpdate: { type: 'array', items: { type: 'string' } },
  },
}

export default async function ({ agent, phase, log, args }) {
  const { requirement, repo, wiki } = args

  phase('Design')
  const design = await agent(
    `需求："${requirement}"\nrepo: ${repo}\nwiki: ${wiki}\n\n先 Read wiki 理解架构与约定，再用 CRG 图定位改动触点。出设计：改动点清单、方案、风险、测试计划、要更新的 wiki 页。`,
    { agentType: 'feature-planner', schema: DESIGN_SCHEMA, label: 'planner' }
  )
  log(`Design: ${design.changes.length} changes, ${design.risks.length} risks`)

  return { requirement, repo, wiki, design }
}
