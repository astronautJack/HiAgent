// feature-design — 需求→设计：CRG 门 → feature-planner 读 wiki+CRG 图出设计 → 返回交人审
// 人审 checkpoint 在 workflow 返回后；批准后启动 feature-implement（未来）
export const meta = {
  name: 'feature-design',
  description: '需求→设计（feature 流水线第 1 步）',
  whenToUse: '用户要按需求做端到端实现，先出设计。传 args {requirement, repo, wiki}。',
  phases: [
    { title: 'CRG', detail: 'code-graph 判新鲜/自动建图' },
    { title: 'Design', detail: 'feature-planner 出设计' },
  ],
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

  phase('CRG')
  const crg = await agent(
    `CRG 门：status 判新鲜→{ok:true}；缺/过时→自动 build（Bash CLI，不走 MCP，全量含 flows，不 skip），超时/报错→{ok:false,error}。repo: ${repo}。`,
    { agentType: 'code-graph', schema: { type: 'object', required: ['ok'], properties: { ok: { type: 'boolean' }, error: { type: 'string' } } }, label: 'crg-gate' }
  )
  if (!crg.ok) {
    log(`CRG gate aborted: ${crg.error || ''}`)
    return { aborted: true, error: crg.error }
  }

  phase('Design')
  const design = await agent(
    `需求："${requirement}"\nrepo: ${repo}\nwiki: ${wiki}\n\n先 Read wiki 理解架构与约定，再用 CRG 图定位改动触点。出设计：改动点清单、方案、风险、测试计划、要更新的 wiki 页。`,
    { agentType: 'feature-planner', schema: DESIGN_SCHEMA, label: 'planner' }
  )
  log(`Design: ${design.changes.length} changes, ${design.risks.length} risks`)

  return { requirement, repo, wiki, design }
}
