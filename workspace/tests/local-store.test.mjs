import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { stringify } from 'yaml'
import { execute, initialize, buildSnapshot, writeAtomic } from '../scripts/local-store.mjs'
import { checkDocuments } from '../scripts/check.mjs'
import { documents, regeneratedIndex, repoRoot } from '../scripts/content.mjs'

test('当前页面需求及其链接可进入内部阅读快照，不初始化或发布实际工作台', () => {
  const publicPaths = JSON.parse(fs.readFileSync(path.join(repoRoot, 'workspace/public-documents.json'), 'utf8')).documents
  const snapshot = buildSnapshot(repoRoot)
  const byPath = new Map(snapshot.documents.map(document => [document.path, document]))
  for (const relative of publicPaths) {
    assert.ok(byPath.has(relative), `内部快照缺少已登记资料：${relative}`)
  }
  const prd = byPath.get('product/prd/03-PRD-全站页面需求.md')
  assert.ok(prd.reading_markdown.includes('/workspace/docs/product/pages/'))
  const index = byPath.get('index.md')
  for (const relative of publicPaths.filter(relative => relative.startsWith('product/pages/'))) {
    const destination = '/workspace/docs/' + relative.split('/').map(encodeURIComponent).join('/')
    assert.ok(prd.reading_markdown.includes(destination), `总表的页面链接没有被解析：${relative}`)
    assert.ok(index.reading_markdown.includes(destination), `首页的页面链接没有被解析：${relative}`)
  }
  for (const document of snapshot.documents) {
    assert.ok(!document.reading_markdown.includes('#unregistered-document'), `内部阅读链接未登记：${document.path}`)
  }
})

const hash = value => crypto.createHash('sha256').update(value).digest('hex')
const owner = '11111111-1111-4111-8111-111111111111'
const prd = 'product/prd/01-PRD.md'
function fixture(t) {
  const temporary = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'hotkey-workspace-test-')))
  const source = path.join(temporary, 'source'), store = path.join(temporary, 'store')
  fs.mkdirSync(source)
  t.after(() => fs.rmSync(temporary, { recursive: true, force: true }))
  const write = (file, body) => writeAtomic(path.join(source, file), body)
  const git = (...args) => {
    const value = spawnSync('git', ['-C', source, ...args], { encoding: 'utf8' })
    assert.equal(value.status, 0, value.stderr)
    return value.stdout.trim()
  }
  const meta = { title: '测试文档', summary: '权限与版本', updated: '2026-10-06' }
  const doc = (fm, body = '# 测试文档\n\n原文\n') => `---\n${stringify({ ...meta, ...fm })}---\n\n${body}`
  write('workspace/content/' + prd, doc({ type: 'prd', status: '生效', custom: { keep: true } }))
  write('workspace/content/assets/decision.txt', '原决策的附件')
  write('workspace/content/decisions/01-原决策.md', doc({ type: 'decision', status: '生效', decided: '2026-10-06', related: [prd] }, '# 测试文档\n\n[附件](../assets/decision.txt)\n'))
  write('PROJECT.md', '# 架构\n\n唯一原文\n')
  write('workspace/content/product/reference/02-技术架构.md', doc({ type: 'pointer', source: '../../../../PROJECT.md' }, '# 来源\n'))
  write('workspace/content/index.md', doc({ type: 'index' }, '# 导航\n\n<!-- index:start -->\n<!-- index:end -->\n'))
  const paths = [prd, 'decisions/01-原决策.md', 'product/reference/02-技术架构.md', 'index.md']
  write('workspace/public-documents.json', JSON.stringify({ version: 1, documents: paths }))
  write('workspace/internal-documents.json', JSON.stringify({ version: 1, documents: paths }))
  const index = path.join(source, 'workspace/content/index.md')
  fs.writeFileSync(index, regeneratedIndex(fs.readFileSync(index, 'utf8'), documents(path.join(source, 'workspace/content'))))
  git('init'); git('add', '.'); git('-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'fixture')
  assert.deepEqual(checkDocuments(path.join(source, 'workspace/content'), source).errors, [])
  const initial = initialize(source, store)
  const run = command => execute(source, store, { owner_id: owner, ...command })
  const draft = () => run({ action: 'draft', path: prd })
  const save = (markdown, extra = {}) => { const d = draft(); return run({ action: 'save', path: prd, markdown, source_hash: d.current_source_hash, draft_revision: d.revision, operation_id: crypto.randomUUID(), ...extra }) }
  const publish = (extra = {}) => { const d = draft(); return run({ action: 'publish', path: prd, source_hash: d.source_hash, draft_revision: d.revision, operation_id: crypto.randomUUID(), ...extra }) }
  return { source, store, initial, run, draft, save, publish, write, git, doc }
}

test('快照确定性、根文件映射、原文与章节 hash；损坏不可静默读取', t => {
  const f = fixture(t)
  assert.equal(buildSnapshot(f.source).snapshot_id, f.initial.snapshot_id)
  const root = f.run({ action: 'read', path: 'product/reference/02-技术架构.md' })
  assert.equal(root.markdown, '# 架构\n\n唯一原文\n')
  assert.deepEqual(root.sections.map(item => item.title), ['来源', '架构'])
  const raw = f.run({ action: 'raw', path: prd, anchor: '测试文档' })
  assert.equal(raw.source_hash, hash(raw.markdown))
  const file = path.join(f.store, 'snapshots', f.initial.snapshot_id + '.json')
  const snapshot = JSON.parse(fs.readFileSync(file)); snapshot.documents[0].markdown += '篡改'
  fs.writeFileSync(file, JSON.stringify(snapshot))
  assert.throws(() => f.run({ action: 'list' }), { code: 'workspace_unavailable' })
})

test('重复保存只生成一版；操作属于本人；崩溃后补齐已准备的草稿', t => {
  const f = fixture(t), d = f.draft(), operation = crypto.randomUUID()
  const command = { action: 'save', path: prd, markdown: d.markdown + '\n网页\n', source_hash: d.source_hash, draft_revision: 0, operation_id: operation }
  const saved = f.run(command)
  assert.deepEqual(f.run(command), saved)
  assert.equal(f.run({ action: 'operation', operation_id: operation }).status, 'saved')
  assert.throws(() => f.run({ action: 'operation', operation_id: operation, owner_id: 'other' }), { code: 'resource_not_found' })
  fs.rmSync(path.join(f.store, 'drafts'), { recursive: true })
  assert.equal(f.run({ action: 'operation', operation_id: operation }).draft.revision, 1)
  assert.equal(f.draft().markdown, saved.markdown)
})

test('Obsidian 并发修改保留双方，合并后发布；仅提交文档和生成索引', t => {
  const f = fixture(t), original = f.draft().markdown
  const web = f.save(original + '\n网页草稿\n')
  f.write('workspace/content/' + prd, original + '\n本地修改\n')
  assert.equal(f.draft().conflicted, true)
  assert.throws(() => f.publish(), { code: 'workspace_version_conflict' })
  assert.equal(f.draft().markdown, web.markdown)
  const merged = f.save(original + '\n网页草稿\n本地修改\n')
  const result = f.publish()
  assert.equal(result.status, 'published')
  assert.equal(f.git('status', '--porcelain'), '')
  assert.equal(f.git('show', 'HEAD:workspace/content/' + prd), merged.markdown.trim())
  assert.equal(f.run({ action: 'read', path: prd }).markdown, merged.markdown)
  assert.equal(f.run({ action: 'read', path: prd, snapshot_id: f.initial.snapshot_id }).markdown, original)
  assert.ok(f.run({ action: 'history', path: prd, history: true }).items.length >= 2)
})

test('无效发布不改来源和 HEAD；其他修改与私密未跟踪文件不混入', t => {
  const f = fixture(t), before = f.git('rev-parse', 'HEAD'), original = f.draft().markdown
  f.save('无元数据')
  assert.equal(f.publish().status, 'failed')
  assert.equal(f.git('rev-parse', 'HEAD'), before)
  assert.equal(fs.readFileSync(path.join(f.source, 'workspace/content/' + prd), 'utf8'), original)
  assert.equal(f.run({ action: 'list' }).snapshot_id, f.initial.snapshot_id)
  f.save(original + '\n网页\n'); f.write('unrelated.txt', '其他工作')
  assert.throws(() => f.publish(), { code: 'workspace_version_conflict' })
  fs.rmSync(path.join(f.source, 'unrelated.txt'))
  fs.writeFileSync(path.join(f.source, '.git/info/exclude'), '.private\n')
  f.write('.private', 'ignored fixture')
  assert.equal(f.publish().status, 'published')
  assert.ok(!f.git('ls-tree', '-r', '--name-only', 'HEAD').includes('.private'))
})

test('决策须替代，旧记录保留且默认隐藏，新记录登记但不进入公开清单', t => {
  const f = fixture(t), path = 'decisions/01-原决策.md', replacement = 'decisions/02-替代决策.md'
  const old = f.run({ action: 'draft', path })
  const next = f.doc({ type: 'decision', status: '生效', decided: '2026-10-06', related: [], title: '新决策' }, '# 新决策\n\n采用新的方案，保留替代原因。\n')
  const d = f.run({ action: 'save', path, markdown: next, source_hash: old.source_hash, draft_revision: 0, operation_id: crypto.randomUUID() })
  const command = { path, source_hash: old.source_hash, draft_revision: d.revision, operation_id: crypto.randomUUID() }
  assert.throws(() => f.run({ ...command, action: 'publish' }), { code: 'workspace_decision_requires_replacement' })
  const result = f.run({ ...command, operation_id: crypto.randomUUID(), action: 'replace', replacement_path: replacement })
  assert.equal(result.status, 'published')
  assert.equal(f.git('status', '--porcelain'), '')
  assert.throws(() => f.run({ action: 'read', path }), { code: 'resource_not_found' })
  assert.equal(f.run({ action: 'read', path, history: true }).status, '废弃')
  assert.ok(f.run({ action: 'read', path: replacement }).related.includes(path))
  const attachment = hash('原决策的附件')
  assert.throws(() => f.run({ action: 'attachment', attachment_id: attachment }), { code: 'resource_not_found' })
  assert.equal(f.run({ action: 'attachment', attachment_id: attachment, history: true }).mime, 'text/plain')
  assert.ok(!JSON.parse(fs.readFileSync(pathJoin(f.source, 'workspace/public-documents.json'))).documents.includes(replacement))
})
function pathJoin(...parts) { return path.join(...parts) }

test('越界和符号链接拒绝；提交后中断的操作可恢复快照且不重复提交', t => {
  const f = fixture(t)
  assert.throws(() => f.run({ action: 'read', path: '../PROJECT.md' }), { code: 'resource_not_found' })
  const target = path.join(f.source, 'workspace/content/' + prd)
  fs.rmSync(target); fs.symlinkSync('/etc/hosts', target)
  assert.throws(() => f.draft(), { code: 'workspace_invalid_input' })
  fs.rmSync(target); f.git('restore', 'workspace/content/' + prd)
  f.save(f.draft().markdown + '\n发布\n')
  const op = crypto.randomUUID(), result = f.publish({ operation_id: op })
  const head = f.git('rev-parse', 'HEAD'), receipt = path.join(f.store, 'operations', op + '.json')
  const data = JSON.parse(fs.readFileSync(receipt)); data.candidate_revision = head; data.candidate_snapshot_id = result.snapshot_id; data.source_path = 'workspace/content/' + prd; data.result = { status: 'pending', operation_id: op }
  fs.writeFileSync(receipt, JSON.stringify(data))
  fs.writeFileSync(path.join(f.store, 'current.json'), JSON.stringify({ snapshot_id: f.initial.snapshot_id }))
  assert.equal(f.run({ action: 'operation', operation_id: op }).status, 'published')
  assert.equal(f.git('rev-parse', 'HEAD'), head)
  assert.equal(f.run({ action: 'list' }).snapshot_id, result.snapshot_id)
})
