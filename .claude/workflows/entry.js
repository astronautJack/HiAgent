// entry.js — 智能路由：分类用户请求意图 → 调对应用例 workflow
export const meta = {
  name: 'entry',
  description: 'HiAgent 智能路由：分类用户请求意图 → 调对应 workflow',
  whenToUse: '用户请求跨用例或意图模糊，需要先分类再分发。单用例意图清晰时直接调对应 workflow。',
  phases: [
    { title: 'Classify', detail: 'LLM 分类意图 + 消歧' },
    { title: 'Dispatch', detail: '调用例 workflow' },
  ],
}

const INTENT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['workflow', 'args', 'confidence'],
  properties: {
    workflow: { type: 'string', enum: [
      'diag', 'bug-trace', 'feature-design',
      'wiki-map', 'wiki-doc', 'wiki-flow',
      'exp-archive', 'exp-search',
    ] },
    args: { type: 'object' },
    confidence: { type: 'string', enum: ['high', 'low'] },
    clarifying_question: { type: 'string' },
  },
}

export default async function ({ agent, phase, workflow, log, args }) {
  const userInput = args && args.userInput
  if (!userInput) return { error: '传 args.userInput' }

  phase('Classify')
  const intent = await agent(
    `分类用户请求到 workflow。\n\n用户请求：${JSON.stringify(userInput)}\n\n` +
    `workflow 与判据：\n` +
    `- diag：用户给了【日志文件/日志文本】，要定位到代码行\n` +
    `- bug-trace：用户给了【bug 报告/失败现象（非日志）】，要找根因\n` +
    `- feature-design：用户要【实现需求/出设计】\n` +
    `- wiki-map：生成结构 wiki（快，纯结构）\n` +
    `- wiki-doc：生成架构文档（可读，知识库级）\n` +
    `- wiki-flow：生成业务流 wiki（调用链+错误目录）\n` +
    `- exp-archive：归档案例\n` +
    `- exp-search：检索历史案例（"这错见过吗"）\n\n` +
    `模糊（confidence=low）→ 给 clarifying_question。args 里至少含 repo（绝对路径）。`,
    { schema: INTENT_SCHEMA, label: 'classify' }
  )

  if (intent.confidence === 'low') return { ask_user: intent.clarifying_question }

  phase('Dispatch')
  log(`Dispatching to ${intent.workflow}`)
  return workflow(intent.workflow, intent.args)
}
