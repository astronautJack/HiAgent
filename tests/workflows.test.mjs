import assert from 'node:assert/strict'
import test from 'node:test'

import diag from '../.cac/workflows/diag.js'
import bugTrace from '../.cac/workflows/bug-trace.js'
import featureDesign from '../.cac/workflows/feature-design.js'
import featureImplement from '../.cac/workflows/feature-implement.js'
import expArchive from '../.cac/workflows/exp-archive.js'
import expSearch from '../.cac/workflows/exp-search.js'
import wikiHealth from '../.cac/workflows/wiki-health.js'


function harness(responses) {
  const calls = []
  const phases = []
  return {
    calls,
    phases,
    context: {
      phase: value => phases.push(value),
      log: () => {},
      agent: async (prompt, options) => {
        calls.push({ prompt, options })
        const value = responses[options.label]
        assert.notEqual(value, undefined, `missing mock for ${options.label}`)
        return typeof value === 'function' ? value(prompt, options) : value
      },
    },
  }
}

const probe = {
  available: true,
  server: 'wiki-mcp',
  capabilities: { search: true, read: true, write: true },
  error: '',
}

const trace = {
  schema_version: 'hiagent.trace.v1',
  report_path: 'C:\\repo\\.hiagent\\runs\\run\\report.md',
  root_cause: { file: 'src/a.js', line: 7, symbol: 'run', summary: 'bad state', confidence: 'high' },
  evidence: [{ kind: 'code', ref: 'src/a.js:7', claim: 'bad state begins here' }],
  impact: ['caller'],
  fix: { summary: 'guard state', changes: [{ file: 'src/a.js', description: 'guard' }] },
  open_questions: [],
}

test('diag runs canonical pipeline and returns reviewed root cause', async () => {
  const h = harness({
    'crg-gate': { ok: true, error: '', warning: '' },
    triage: {
      schema_version: 'hiagent.log-digest.v1', raw_file: 'C:\\logs\\a.log', log_format: 'auto', drain_mode: 'learn',
      line_count: 2, claimed_error: 'failed', symbols: [], clusters: [], hisysevent_anchors: [], fault_frames: [], key_lines: [1],
      truncated: { clusters: false, hisysevents: false, fault_frames: false, key_lines: false },
    },
    'wiki-probe': probe,
    'wiki-search': { matches: [], total: 0 },
    'trace-1': trace,
    'review-1': { verdict: 'pass', findings: [], verified_claims: ['src/a.js:7'] },
  })

  const result = await diag({ ...h.context, args: { repo: 'C:\\repo', logPath: 'C:\\logs\\a.log' } })

  assert.equal(result.aborted, false)
  assert.equal(result.root_cause.file, 'src/a.js')
  assert.equal(result.review.consensus, true)
  assert.deepEqual(h.phases, ['Validate', 'CRG', 'Triage', 'Knowledge', 'Trace', 'Review', 'Report'])
})

test('diag rejects oversized inline logs before invoking agents', async () => {
  const h = harness({})
  const result = await diag({ ...h.context, args: { repo: 'C:\\repo', logText: 'x'.repeat(20001) } })
  assert.equal(result.aborted, true)
  assert.equal(h.calls.length, 0)
})

test('diag accepts only Windows paths and rejects report traversal', async () => {
  const posix = harness({})
  const posixResult = await diag({ ...posix.context, args: { repo: '/repo', logText: 'failure' } })
  assert.equal(posixResult.aborted, true)
  assert.match(posixResult.error, /Windows/)

  const traversal = harness({})
  const traversalResult = await diag({ ...traversal.context, args: { repo: 'C:\\repo', logText: 'failure', reportPath: 'C:\\repo\\..\\outside.md' } })
  assert.equal(traversalResult.aborted, true)
  assert.match(traversalResult.error, /repo 内/)
  assert.equal(traversal.calls.length, 0)
})

test('bug trace carries reviewer findings into a second trace attempt', async () => {
  const h = harness({
    'crg-gate': { ok: true, error: '', warning: '' },
    'wiki-probe': probe,
    'wiki-search': { matches: [], total: 0 },
    'trace-1': trace,
    'review-1': { verdict: 'revise', findings: ['line mismatch'], verified_claims: [] },
    'trace-2': trace,
    'review-2': { verdict: 'pass', findings: [], verified_claims: ['fixed'] },
  })

  const result = await bugTrace({ ...h.context, args: { repo: 'C:\\repo', report: 'button fails' } })

  assert.equal(result.review.consensus, true)
  assert.equal(h.calls.filter(call => call.options.label.startsWith('trace-')).length, 2)
  assert.match(h.calls.find(call => call.options.label === 'trace-2').prompt, /line mismatch/)
})

test('feature implementation refuses to edit without explicit approval', async () => {
  const h = harness({})
  const result = await featureImplement({ ...h.context, args: { repo: 'C:\\repo', design: {} } })
  assert.equal(result.implemented, false)
  assert.match(result.error, /approved/)
  assert.equal(h.calls.length, 0)
})

test('feature implementation rejects paths escaping the repo', async () => {
  const h = harness({})
  const design = { schema_version: 'hiagent.feature-design.v1', summary: 'bad', changes: [{ file: '..\\outside.txt' }], test_plan: [] }
  const result = await featureImplement({ ...h.context, args: { repo: 'C:\\repo', design, approved: true } })
  assert.equal(result.implemented, false)
  assert.equal(h.calls.length, 0)
})

test('approved feature loops through coder reviewer and tester', async () => {
  const design = { schema_version: 'hiagent.feature-design.v1', summary: 'approved', changes: [], test_plan: [] }
  const h = harness({
    'coder-1': { summary: 'done', changed_files: ['src/a.js'], remaining_issues: [] },
    'graph-1': { ok: true, error: '', warning: '' },
    'reviewer-1': { verdict: 'pass', findings: [], impact: [] },
    'tester-1': { verdict: 'pass', commands: [{ command: 'npm test', status: 0, summary: 'ok' }], failures: [] },
  })
  const result = await featureImplement({ ...h.context, args: { repo: 'C:\\repo', design, approved: true } })
  assert.equal(result.implemented, true)
  assert.equal(result.committed, false)
})

test('feature design uses wiki only as bounded candidate context', async () => {
  const h = harness({
    'crg-gate': { ok: true, error: '', warning: '' }, 'wiki-probe': probe, 'wiki-search': { matches: [], total: 0 },
    planner: { schema_version: 'hiagent.feature-design.v1', summary: 'x', assumptions: [], changes: [], risks: [], test_plan: [], knowledge_updates: [] },
  })
  const result = await featureDesign({ ...h.context, args: { repo: 'C:\\repo', requirement: 'add x' } })
  assert.equal(result.aborted, false)
  assert.equal(result.design.schema_version, 'hiagent.feature-design.v1')
})

test('experience archive fails closed when wiki write cannot be verified', async () => {
  const h = harness({
    curate: { ready: true, reasons: [], page: { external_id: 'hiagent:r:case:x', title: 'x', content: 'x', metadata: {} } },
    'wiki-probe': probe,
    'wiki-upsert': { written: true, action: 'created', id: '1', title: 'x', url: '', verified: false, error: 'readback failed' },
  })
  const caseData = { created_from: 'diag', confidence: 'high', evidence: [{ kind: 'code', ref: 'src/a.js:7' }], validation: 'test passed' }
  const result = await expArchive({ ...h.context, args: { repo: 'C:\\repo', caseData, humanConfirmed: true } })
  assert.equal(result.archived, false)
  assert.match(h.calls.find(call => call.options.label === 'wiki-upsert').prompt, /"route":"diag"/)
})

test('experience search validates staleness against current repo', async () => {
  const h = harness({
    'wiki-probe': probe,
    'wiki-search': { matches: [{ id: '1', metadata: { source_commit: 'abc', source_paths: ['src/a.js'] } }], total: 1 },
    'validate-search': { matches: [{ id: '1', stale: true, stale_files: ['src/a.js'], stale_reason: 'changed' }], total: 1 },
  })
  const result = await expSearch({ ...h.context, args: { repo: 'C:\\repo', query: 'failure' } })
  assert.equal(result.matches[0].stale, true)
  assert.ok(h.phases.includes('Validate'))
})

test('wiki health requires search read and write capabilities', async () => {
  const h = harness({ 'wiki-probe': probe })
  const result = await wikiHealth(h.context)
  assert.equal(result.ready, true)
  assert.equal(result.server, 'wiki-mcp')
})
