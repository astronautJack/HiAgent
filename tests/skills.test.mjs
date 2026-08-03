import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const skillsUrl = new URL('../.cac/skills/', import.meta.url)
const agentsUrl = new URL('../.cac/agents/', import.meta.url)
async function skill(name) {
  return readFile(new URL(`${name}/SKILL.md`, skillsUrl), 'utf8')
}
async function agent(name) {
  return readFile(new URL(`${name}.md`, agentsUrl), 'utf8')
}

const PROBE = '{available, server, capabilities, error}'

test('diag documents the canonical pipeline with isolated report writer last', async () => {
  const content = await skill('diag')
  for (const phase of ['Validate', 'CRG', 'Triage', 'Knowledge', 'Trace', 'Review', 'Report']) {
    assert.ok(content.includes(phase), `diag must document phase ${phase}`)
  }
  const reportIdx = content.indexOf('trace-report-writer')
  const tracerIdx = content.indexOf('code-tracer')
  const reviewerIdx = content.indexOf('code-tracer-reviewer')
  assert.ok(reportIdx > tracerIdx, 'report writer must come after investigator in the doc')
  assert.ok(reportIdx > reviewerIdx, 'report writer must come after reviewer in the doc')
  assert.match(content, /最多三轮/)
})

test('diag rejects oversized inline logs and non-Windows paths before invoking agents', async () => {
  const content = await skill('diag')
  assert.match(content, /20000/)
  assert.match(content, /Windows 绝对路径/)
  assert.match(content, /穿越|traversal|\.\./)
  const validateIdx = content.indexOf('Validate')
  const crgIdx = content.indexOf('code-graph')
  assert.ok(validateIdx < crgIdx, 'validation must precede any subagent call')
})

test('bug trace carries reviewer findings into the next trace attempt', async () => {
  const content = await skill('bug-trace')
  assert.match(content, /reviewer_findings:\[\.\.\.verdict\.findings, \.\.\.verdict\.contradictions\]/)
  assert.match(content, /最多三轮/)
  assert.match(content, /code-tracer-reviewer/)
  assert.match(content, /trace-report-writer/)
})

test('feature implementation refuses to edit without explicit approval and escapes', async () => {
  const content = await skill('feature-implement')
  assert.match(content, /approved 必须为 true/)
  assert.match(content, /isSafeRelativePath/)
  const gateIdx = content.indexOf('Gate')
  const coderIdx = content.indexOf('feature-coder')
  assert.ok(gateIdx < coderIdx, 'gate must precede coder')
})

test('feature implement loops through coder graph reviewer tester and never commits', async () => {
  const content = await skill('feature-implement')
  for (const agent of ['feature-coder', 'code-graph', 'feature-reviewer', 'feature-tester']) {
    assert.ok(content.includes(agent), `feature-implement must reference ${agent}`)
  }
  assert.match(content, /committed.*false|committed:false/)
  assert.match(content, /最多三轮/)
  assert.match(content, /hiagent-crg refresh/)
  assert.match(content, /禁止用 MCP build/)
})

test('feature design uses wiki only as bounded candidate and returns approval handoff', async () => {
  const content = await skill('feature-design')
  assert.match(content, /hiagent.feature-design.v1/)
  assert.match(content, /是否批准/)
  assert.match(content, /feature-implement/)
  assert.match(content, /approved.*true|approved:true|approved: true/)
  assert.match(content, /原样传递/)
})

test('experience archive fails closed when wiki write cannot be verified', async () => {
  const content = await skill('exp-archive')
  assert.match(content, /written && verified/)
  assert.match(content, /target:\s*\{\s*route/)
  assert.match(content, /humanConfirmed 必须为 true/)
  assert.match(content, /confidence 必须为 high/)
})

test('experience search validates staleness against current repo', async () => {
  const content = await skill('exp-search')
  assert.match(content, /validate-search/)
  assert.match(content, /历史经验仅是候选/)
})

test('wiki health requires search read and write capabilities', async () => {
  const content = await skill('wiki-health')
  assert.match(content, /capabilities.search && capabilities.read && capabilities.write|search && read && write/)
  assert.match(content, /wiki-mcp/)
  assert.match(content, /只读探测/)
})

test('entry classifies and dispatches with low-confidence clarifying fallback', async () => {
  const content = await skill('entry')
  for (const name of ['diag', 'bug-trace', 'feature-design', 'feature-implement', 'exp-archive', 'exp-search', 'wiki-health']) {
    assert.ok(content.includes(name), `entry must reference skill ${name}`)
  }
  assert.match(content, /clarifying_question/)
  assert.match(content, /ask_user/)
})

test('feature reviewer enforces the five-level priority order with named edges', async () => {
  const reviewer = await agent('feature-reviewer')
  const priorities = ['P1 设计', 'P2 功能', 'P3 可读性与可维护性', 'P4 测试覆盖', 'P5 风格与规范']
  let last = -1
  for (let i = 0; i < priorities.length; i++) {
    const idx = reviewer.indexOf(priorities[i])
    assert.ok(idx > last, `${priorities[i]} must appear in order after the previous priority`)
    last = idx
  }
  for (const edge of ['空值', '超时', '并发']) {
    assert.ok(reviewer.includes(edge), `reviewer must name edge case ${edge}`)
  }
  assert.match(reviewer, /圈复杂度/)
  assert.match(reviewer, /拆.*更小/)
  assert.match(reviewer, /Linter/)
  assert.match(reviewer, /P1 \| P2 \| P3 \| P4 \| P5/)
  assert.match(reviewer, /无 blocker 且无 P1 major/)
})

test('feature coder and planner align with the same priority principles', async () => {
  const coder = await agent('feature-coder')
  for (const edge of ['空值', '超时', '并发']) {
    assert.ok(coder.includes(edge), `coder must name edge case ${edge}`)
  }
  assert.match(coder, /圈复杂度|拆为更小/)
  assert.match(coder, /Linter/)

  const planner = await agent('feature-planner')
  assert.match(planner, /架构融入/)
  assert.match(planner, /过度设计/)
  assert.match(planner, /设计不足/)
  for (const edge of ['空值', '超时', '并发']) {
    assert.ok(planner.includes(edge), `planner must name edge case ${edge}`)
  }
})
