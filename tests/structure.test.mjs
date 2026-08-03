import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test from 'node:test'


test('every skill is a SKILL.md with name and description frontmatter', async () => {
  const directory = new URL('../.cac/skills/', import.meta.url)
  const entries = (await readdir(directory, { withFileTypes: true }))
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .sort()
  assert.deepEqual(entries, [
    'bug-trace', 'diag', 'entry', 'exp-archive', 'exp-search',
    'feature-design', 'feature-implement', 'wiki-health',
  ])
  for (const name of entries) {
    const content = await readFile(new URL(`${name}/SKILL.md`, directory), 'utf8')
    const frontmatter = content.split('---')[1]
    assert.match(frontmatter, /\nname: /, `${name}/SKILL.md name`)
    assert.match(frontmatter, /\ndescription: /, `${name}/SKILL.md description`)
    assert.doesNotMatch(frontmatter, /\nmode:|\npermission:|\ntools:/, `${name}/SKILL.md no agent-only fields`)
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

  const skill = await readFile(new URL('../.cac/skills/exp-archive/SKILL.md', import.meta.url), 'utf8')
  assert.doesNotMatch(skill, /log_experience|code_logic|code_summary/)
  assert.match(skill, /target:\s*\{\s*route\s*:/)
})


test('trace investigation review and report writing use isolated roles', async () => {
  const investigator = await readFile(new URL('../.cac/agents/code-tracer.md', import.meta.url), 'utf8')
  const reviewer = await readFile(new URL('../.cac/agents/code-tracer-reviewer.md', import.meta.url), 'utf8')
  const writer = await readFile(new URL('../.cac/agents/trace-report-writer.md', import.meta.url), 'utf8')
  assert.doesNotMatch(investigator.split('---')[1], /Write|Edit/)
  assert.doesNotMatch(reviewer.split('---')[1], /Write|Edit/)
  assert.match(writer.split('---')[1], /tools: Write, Bash/)

  for (const name of ['diag', 'bug-trace']) {
    const skill = await readFile(new URL(`../.cac/skills/${name}/SKILL.md`, import.meta.url), 'utf8')
    assert.match(skill, /code-tracer/)
    assert.match(skill, /code-tracer-reviewer/)
    assert.match(skill, /trace-report-writer/)
  }
})
