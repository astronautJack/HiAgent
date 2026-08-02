// wiki-health — 内网迁移后的零配置验收
export const meta = {
  name: 'wiki-health',
  description: '检查 wiki-mcp 是否可检索、读取和写入，不产生测试页面',
  whenToUse: '项目传入内网后首先运行；无需参数。',
  phases: [{ title: 'Probe', detail: '探测 wiki-mcp 能力' }],
}

const PROBE_SCHEMA = { type: 'object', additionalProperties: false, required: ['available', 'server', 'capabilities', 'error'], properties: { available: { type: 'boolean' }, server: { type: 'string' }, capabilities: { type: 'object' }, error: { type: 'string' } } }

export default async function ({ agent, phase }) {
  phase('Probe')
  const result = await agent('执行 probe。只做只读探测，不创建测试页面。服务名必须准确为 wiki-mcp。', {
    agentType: 'wiki-gateway', schema: PROBE_SCHEMA, label: 'wiki-probe',
  })
  return {
    ...result,
    ready: Boolean(result.available && result.capabilities.search && result.capabilities.read && result.capabilities.write),
    next: result.available ? '可以直接运行 diag、feature-design、exp-search 和 exp-archive。' : '确认内网 CodeAgent 会话已注入 wiki-mcp，然后重启 codeagent。',
  }
}
