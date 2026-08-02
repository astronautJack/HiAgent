// feature-implement — 已批准设计 → coder/reviewer/tester 闭环，不提交不推送
export const meta = {
  name: 'feature-implement',
  description: '按人工批准的设计实现代码并完成独立审查和测试门禁',
  whenToUse: '传 args {repo, design, approved:true}；必须先完成人审',
  phases: [{ title: 'Gate', detail: '确认人工批准与设计契约' }, { title: 'Implement', detail: '实现或修订' }, { title: 'Graph', detail: 'CLI 增量刷新代码图' }, { title: 'Review', detail: '独立代码审查' }, { title: 'Test', detail: '运行质量门禁' }, { title: 'Result', detail: '交付未提交改动' }],
}

const GATE_SCHEMA = { type: 'object', additionalProperties: false, required: ['ok', 'error', 'warning'], properties: { ok: { type: 'boolean' }, error: { type: 'string' }, warning: { type: 'string' } } }
const CODE_SCHEMA = { type: 'object', additionalProperties: false, required: ['summary', 'changed_files', 'remaining_issues'], properties: { summary: { type: 'string' }, changed_files: { type: 'array', items: { type: 'string' } }, remaining_issues: { type: 'array', items: { type: 'string' } } } }
const REVIEW_SCHEMA = { type: 'object', additionalProperties: false, required: ['verdict', 'findings', 'impact'], properties: { verdict: { type: 'string', enum: ['pass', 'revise'] }, findings: { type: 'array', items: { type: 'object' } }, impact: { type: 'array', items: { type: 'string' } } } }
const TEST_SCHEMA = { type: 'object', additionalProperties: false, required: ['verdict', 'commands', 'failures'], properties: { verdict: { type: 'string', enum: ['pass', 'fail'] }, commands: { type: 'array', items: { type: 'object' } }, failures: { type: 'array', items: { type: 'string' } } } }
function isWindowsAbsolutePath(value) { return typeof value === 'string' && (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)/.test(value)) }
function hasTraversal(value) { return value.split(/[\\/]/).includes('..') }
function isSafeRelativePath(value) { return typeof value === 'string' && value.trim() !== '' && !isWindowsAbsolutePath(value) && !hasTraversal(value) }

export default async function ({ agent, phase, log, args = {} }) {
  const { repo, design, approved = false } = args
  phase('Gate')
  if (!isWindowsAbsolutePath(repo) || hasTraversal(repo)) return { implemented: false, stage: 'gate', error: 'repo 必须是 Windows 绝对路径' }
  if (approved !== true) return { implemented: false, stage: 'gate', error: '缺少人工批准：approved 必须为 true' }
  if (!design || design.schema_version !== 'hiagent.feature-design.v1') return { implemented: false, stage: 'gate', error: 'design 必须符合 hiagent.feature-design.v1' }
  if (typeof design.summary !== 'string' || !Array.isArray(design.changes) || !Array.isArray(design.test_plan)) {
    return { implemented: false, stage: 'gate', error: 'design 缺少 summary/changes/test_plan' }
  }
  if (!design.changes.every(change => change && isSafeRelativePath(change.file))) {
    return { implemented: false, stage: 'gate', error: 'design 包含仓外或非法相对路径' }
  }

  let implementation = null
  let review = { verdict: 'revise', findings: [], impact: [] }
  let tests = { verdict: 'fail', commands: [], failures: [] }
  let feedback = []
  for (let attempt = 1; attempt <= 3; attempt++) {
    phase('Implement')
    implementation = await agent(`按已批准设计实现；只改设计范围，不 commit/push。输入=${JSON.stringify({ repo, design, feedback })}`, {
      agentType: 'feature-coder', schema: CODE_SCHEMA, label: `coder-${attempt}`,
    })
    if (!implementation.changed_files.every(isSafeRelativePath)) {
      phase('Result')
      return { implemented: false, stage: 'implementation-contract', error: 'coder 返回仓外或非法路径', implementation, attempts: attempt, committed: false }
    }
    if (implementation.remaining_issues.length > 0) {
      feedback = implementation.remaining_issues
      log(`第 ${attempt} 轮实现仍有未解决问题`)
      continue
    }

    phase('Graph')
    const graph = await agent(`执行 hiagent-crg refresh --repo ${JSON.stringify(repo)}，用本地 CLI 把当前 working tree 增量写入图；禁止用 MCP build。`, {
      agentType: 'code-graph', schema: GATE_SCHEMA, label: `graph-${attempt}`,
    })
    if (!graph.ok) {
      phase('Result')
      return { implemented: false, stage: 'crg-refresh', error: graph.error, implementation, attempts: attempt, committed: false }
    }
    if (graph.warning) log(graph.warning)

    phase('Review')
    review = await agent(`独立审查当前 git diff。输入=${JSON.stringify({ repo, design, implementation })}`, {
      agentType: 'feature-reviewer', schema: REVIEW_SCHEMA, label: `reviewer-${attempt}`,
    })
    if (review.verdict === 'revise') {
      feedback = review.findings
      log(`第 ${attempt} 轮代码审查未通过`)
      continue
    }

    phase('Test')
    tests = await agent(`自动发现并运行目标仓质量门禁。输入=${JSON.stringify({ repo, design, changed_files: implementation.changed_files })}`, {
      agentType: 'feature-tester', schema: TEST_SCHEMA, label: `tester-${attempt}`,
    })
    if (tests.verdict === 'pass') {
      phase('Result')
      return { implemented: true, review, tests, implementation, attempts: attempt, committed: false, next: '请人工检查 git diff；确认后可归档实现经验并由你手动提交。' }
    }
    feedback = tests.failures
    log(`第 ${attempt} 轮测试未通过`)
  }

  phase('Result')
  return { implemented: false, stage: 'quality-gate', review, tests, implementation, attempts: 3, committed: false, next: '保留当前工作区供人工处理，未提交、未推送。' }
}
