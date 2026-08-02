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
      'diag', 'bug-trace', 'feature-design', 'feature-implement',
      'exp-archive', 'exp-search', 'wiki-health',
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
    `- feature-design：用户提出需求，需要先出设计并人审\n` +
    `- feature-implement：用户已明确批准 hiagent.feature-design.v1 设计，要开始改代码\n` +
    `- exp-archive：归档案例\n` +
    `- exp-search：检索历史案例（"这错见过吗"）\n\n` +
    `- wiki-health：检查内网 wiki-mcp 是否已经可用\n\n` +
    `模糊（confidence=low）→ 给 clarifying_question。涉及目标代码的 workflow，repo 必须是 Windows 绝对路径；wiki-health 无参数，exp-search 的 repo 可选。feature-design 返回 ask_user/handoff 后必须询问用户；只有用户明确批准，并把该结果中的 design 原样传入时，feature-implement 才能分类命中。`,
    { schema: INTENT_SCHEMA, label: 'classify' }
  )

  if (intent.confidence === 'low') return { ask_user: intent.clarifying_question }

  phase('Dispatch')
  log(`Dispatching to ${intent.workflow}`)
  return workflow(intent.workflow, intent.args)
}
