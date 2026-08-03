import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const skillsUrl = new URL('../.cac/skills/', import.meta.url)
async function skill(name) {
  return readFile(new URL(`${name}/SKILL.md`, skillsUrl), 'utf8')
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
