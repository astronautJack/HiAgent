import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test from 'node:test'


test('every workflow is an importable ESM module with metadata', async () => {
  const directory = new URL('../.cac/workflows/', import.meta.url)
  const files = (await readdir(directory)).filter(name => name.endsWith('.js')).sort()
  assert.deepEqual(files, [
    'bug-trace.js', 'diag.js', 'entry.js', 'exp-archive.js', 'exp-search.js',
    'feature-design.js', 'feature-implement.js', 'wiki-health.js',
  ])
  for (const file of files) {
    const module = await import(new URL(file, directory))
    assert.equal(typeof module.default, 'function', file)
    assert.equal(typeof module.meta?.name, 'string', file)
    assert.ok(Array.isArray(module.meta?.phases), file)
  }
})


test('agent frontmatter uses one CodeAgent-compatible style', async () => {
  const directory = new URL('../.cac/agents/', import.meta.url)
  const files = (await readdir(directory)).filter(name => name.endsWith('.md'))
  assert.equal(files.length, 11)
  for (const file of files) {
    const content = await readFile(new URL(file, directory), 'utf8')
    const frontmatter = content.split('---')[1]
    assert.match(frontmatter, /\nname: /, file)
    assert.match(frontmatter, /\ndescription: /, file)
    assert.doesNotMatch(frontmatter, /\nmode:|\npermission:/, file)
  }
})


test('wiki categories and routes are data-driven', async () => {
  const config = JSON.parse(await readFile(new URL('../.cac/wiki-targets.json', import.meta.url), 'utf8'))
  assert.equal(config.schema_version, 'hiagent.wiki-targets.v2')
  assert.equal(typeof config.base_url, 'string')
  assert.ok(Array.isArray(config.categories))
  assert.ok(config.categories.length > 0)
  const keys = new Set(config.categories.map(category => category.key))
  assert.equal(keys.size, config.categories.length)
  assert.ok(config.routes.default)
  for (const key of Object.values(config.routes)) assert.ok(keys.has(key), `unknown category key: ${key}`)

  const workflow = await readFile(new URL('../.cac/workflows/exp-archive.js', import.meta.url), 'utf8')
  assert.doesNotMatch(workflow, /log_experience|code_logic|code_summary/)
  assert.match(workflow, /target: \{ route:/)
})


test('trace investigation review and report writing use isolated roles', async () => {
  const investigator = await readFile(new URL('../.cac/agents/code-tracer.md', import.meta.url), 'utf8')
  const reviewer = await readFile(new URL('../.cac/agents/code-tracer-reviewer.md', import.meta.url), 'utf8')
  const writer = await readFile(new URL('../.cac/agents/trace-report-writer.md', import.meta.url), 'utf8')
  assert.doesNotMatch(investigator.split('---')[1], /Write|Edit/)
  assert.doesNotMatch(reviewer.split('---')[1], /Write|Edit/)
  assert.match(writer.split('---')[1], /tools: Write, Bash/)

  for (const file of ['diag.js', 'bug-trace.js']) {
    const workflow = await readFile(new URL(`../.cac/workflows/${file}`, import.meta.url), 'utf8')
    assert.match(workflow, /agentType: 'code-tracer'/)
    assert.match(workflow, /agentType: 'code-tracer-reviewer'/)
    assert.match(workflow, /agentType: 'trace-report-writer'/)
  }
})
