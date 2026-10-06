import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import GithubSlugger from 'github-slugger'
import { parseDocument } from 'yaml'
import { visit } from 'unist-util-visit'
import { readDocument, markdown, documents, regeneratedIndex, splitLink } from './content.mjs'
import { checkDocuments } from './check.mjs'

const sha = value => crypto.createHash('sha256').update(value).digest('hex')
const fail = code => { throw Object.assign(new Error(code), { code }) }
const text = node => node.value ?? (node.children ?? []).map(text).join('')
const privateModes = { mode: 0o700 }
export function writeAtomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, ...privateModes })
  const temporary = `${file}.${crypto.randomUUID()}.tmp`
  fs.writeFileSync(temporary, value, { mode: 0o600 })
  fs.renameSync(temporary, file)
}
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')) }
function git(source, ...args) {
  const result = spawnSync('git', ['-C', source, ...args], { encoding: 'utf8', timeout: 30000 })
  if (result.status !== 0) fail('workspace_unavailable')
  return result.stdout.trimEnd()
}
function safe(root, relative) {
  if (typeof relative !== 'string' || relative.length > 300 || relative.includes('\\') ||
    path.posix.normalize(relative) !== relative || path.isAbsolute(relative) ||
    relative.split('/').some(part => !part || part.startsWith('.') || ['templates', 'views'].includes(part))) fail('workspace_invalid_input')
  const target = path.resolve(root, relative)
  if (!target.startsWith(path.resolve(root) + path.sep)) fail('workspace_invalid_input')
  let ancestor = target
  while (!fs.existsSync(ancestor)) ancestor = path.dirname(ancestor)
  if (fs.realpathSync(ancestor) !== fs.realpathSync(root) && !fs.realpathSync(ancestor).startsWith(fs.realpathSync(root) + path.sep)) fail('workspace_invalid_input')
  return target
}
function sourceFor(source, relative) { return safe(source, relative) }
function readSource(source, relative) { return fs.readFileSync(sourceFor(source, relative), 'utf8') }
function documentPaths(source) {
  const config = readJson(path.join(source, 'workspace/internal-documents.json'))
  if (config.version !== 1 || !Array.isArray(config.documents) || new Set(config.documents).size !== config.documents.length) fail('workspace_unavailable')
  return config.documents.map(relative => {
    if (!relative.endsWith('.md')) fail('workspace_unavailable')
    safe(path.join(source, 'workspace/content'), relative)
    return relative
  }).sort()
}
function sourcePath(document) {
  const pointer = { 'product/01-进度与优先级.md': 'BACKLOG.md', 'product/02-技术架构.md': 'PROJECT.md', 'product/03-工程规范.md': 'AGENTS.md' }
  if (document.frontmatter.source) {
    const candidate = pointer[document.relative]
    if (!candidate || document.frontmatter.source !== '../../../' + candidate) fail('workspace_invalid_input')
    return candidate
  }
  return 'workspace/content/' + document.relative
}
function sections(body) {
  const result = [], slugger = new GithubSlugger()
  visit(markdown.parse(body), 'heading', node => { result.push({ title: text(node), anchor: slugger.slug(text(node)), level: node.depth, offset: node.position.start.offset }) })
  return result.map((section, index) => ({ ...section, content: body.slice(section.offset, result[index + 1]?.offset ?? body.length) }))
}
function renderBody(source, origin, body, bySource, assets) {
  const patches = []
  visit(markdown.parse(body), node => {
    if (!['link', 'image', 'definition'].includes(node.type) || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(node.url) || !node.url) return
    const [relative, suffix] = splitLink(node.url)
    if (!relative) return
    const resolved = path.resolve(source, path.dirname(origin), decodeURIComponent(relative))
    const target = path.relative(source, resolved).split(path.sep).join('/')
    let url = bySource.get(target)
    if (url) url = '/workspace/docs/' + url.split('/').map(encodeURIComponent).join('/') + suffix
    else if (/\.(png|jpe?g|gif|webp|pdf|txt)$/i.test(target)) {
      const file = sourceFor(source, target), bytes = fs.readFileSync(file)
      if (bytes.length > 10 * 1024 * 1024) fail('workspace_invalid_input')
      const id = sha(bytes), ext = path.extname(target).slice(1).toLowerCase()
      assets[id] = { filename: path.basename(target), body: bytes.toString('base64'), sha256: id, mime: ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', pdf: 'application/pdf', txt: 'text/plain' })[ext] }
      url = 'workspace-attachment:' + id + suffix
    } else if (target.startsWith('workspace/content/') && !target.startsWith('workspace/content/templates/')) url = '#unregistered-document'
    else if (!target.startsWith('../') && fs.existsSync(resolved) && (fs.realpathSync(resolved) === fs.realpathSync(source) || fs.realpathSync(resolved).startsWith(fs.realpathSync(source) + path.sep))) url = 'https://github.com/StephenQiu30/hotkey-server/blob/main/' + target.split('/').map(encodeURIComponent).join('/') + suffix
    else fail('workspace_invalid_input')
    const start = node.position.start.offset, end = node.position.end.offset
    const chunk = body.slice(start, end), index = chunk.indexOf(node.url)
    if (index >= 0) patches.push([start + index, start + index + node.url.length, url])
  })
  return patches.sort((a, b) => b[0] - a[0]).reduce((value, [start, end, url]) => value.slice(0, start) + url + value.slice(end), body)
}
export function buildSnapshot(source, sourceRevision = git(source, 'rev-parse', 'HEAD')) {
  const paths = documentPaths(source), documents = paths.map(relative => readDocument(safe(path.join(source, 'workspace/content'), relative), path.join(source, 'workspace/content')))
  const bySource = new Map(documents.flatMap(doc => [['workspace/content/' + doc.relative, doc.relative], [sourcePath(doc), doc.relative]]))
  const assets = {}, items = documents.map(doc => {
    const origin = sourcePath(doc), raw = readSource(source, origin)
    const reading = origin.startsWith('workspace/content/') ? renderBody(source, origin, doc.body, bySource, assets) : renderBody(source, 'workspace/content/' + doc.relative, doc.body, bySource, assets) + '\n\n' + renderBody(source, origin, raw, bySource, assets)
    const f = doc.frontmatter
    if (!f.type || !f.title || !f.summary || !f.updated || f.status === '草稿') fail('workspace_invalid_input')
    return { path: doc.relative, source_path: origin, title: String(f.title), summary: String(f.summary), type: String(f.type), status: f.status ?? null, updated: String(f.updated), related: f.related ?? [], markdown: raw, reading_markdown: reading, source_hash: sha(raw), reading_hash: sha(reading), sections: sections(reading).map(({ offset, ...s }) => s) }
  })
  const snapshot = { version: 1, source_revision: sourceRevision, documents: items, attachments: assets }
  return { snapshot_id: sha(JSON.stringify(snapshot)), ...snapshot }
}
function snapshotAt(store, id, prepared = false) {
  if (!/^[a-f\d]{64}$/.test(id)) fail('workspace_invalid_input')
  if (!prepared && !fs.existsSync(path.join(store, 'published', id + '.json'))) fail('resource_not_found')
  const file = path.join(store, 'snapshots', id + '.json')
  if (!fs.existsSync(file)) fail('resource_not_found')
  const snapshot = readJson(file), { snapshot_id, ...content } = snapshot
  if (snapshot_id !== id || sha(JSON.stringify(content)) !== id || snapshot.documents.some(doc => sha(doc.markdown) !== doc.source_hash || sha(doc.reading_markdown) !== doc.reading_hash) || Object.values(snapshot.attachments).some(asset => sha(Buffer.from(asset.body, 'base64')) !== asset.sha256)) fail('workspace_unavailable')
  return snapshot
}
function installSnapshot(store, snapshot) {
  writeAtomic(path.join(store, 'snapshots', snapshot.snapshot_id + '.json'), JSON.stringify(snapshot))
  writeAtomic(path.join(store, 'published', snapshot.snapshot_id + '.json'), JSON.stringify({ source_revision: snapshot.source_revision }))
  writeAtomic(path.join(store, 'current.json'), JSON.stringify({ snapshot_id: snapshot.snapshot_id }))
}
function locked(store, work) {
  const lock = path.join(store, '.lock')
  fs.mkdirSync(store, { recursive: true, ...privateModes })
  try { fs.mkdirSync(lock, privateModes) } catch {
    const owner = path.join(lock, 'owner.json')
    if (!fs.existsSync(owner)) fail('workspace_busy')
    const pid = readJson(owner).pid
    try { process.kill(pid, 0); fail('workspace_busy') } catch (error) {
      if (error.code !== 'ESRCH') fail('workspace_busy')
      fs.rmSync(lock, { recursive: true }); fs.mkdirSync(lock, privateModes)
    }
  }
  fs.writeFileSync(path.join(lock, 'owner.json'), JSON.stringify({ pid: process.pid }), { mode: 0o600 })
  try { return work() } finally { fs.rmSync(lock, { recursive: true }) }
}
function validate(source) {
  const previous = process.cwd()
  // checkDocuments resolves repository links using the tool checkout. Dedicated
  // clones retain the same repository layout; internal registration stays separate.
  try {
    process.chdir(path.join(source, 'workspace'))
    const { errors } = checkDocuments(path.join(source, 'workspace/content'), source)
    if (errors.length) fail('workspace_invalid_input')
  } finally { process.chdir(previous) }
}
export function initialize(source, store) {
  if (git(source, 'status', '--porcelain')) fail('workspace_version_conflict')
  validate(source)
  const snapshot = buildSnapshot(source)
  installSnapshot(store, snapshot)
  return { snapshot_id: snapshot.snapshot_id, source_revision: snapshot.source_revision, documents: snapshot.documents.length }
}
export function execute(source, store, command) {
  if (command.operation_id && !/^[a-f\d]{8}-[a-f\d]{4}-[1-8][a-f\d]{3}-[89ab][a-f\d]{3}-[a-f\d]{12}$/i.test(command.operation_id)) fail('workspace_invalid_input')
  if (!fs.existsSync(path.join(source, '.git')) || !fs.existsSync(path.join(store, 'current.json'))) fail('workspace_unavailable')
  const id = command.snapshot_id || readJson(path.join(store, 'current.json')).snapshot_id
  const snapshot = snapshotAt(store, id)
  const visible = snapshot.documents.filter(doc => command.history || doc.status !== '废弃')
  const doc = command.path ? visible.find(item => item.path === command.path) : null
  if (command.path && !doc) fail('resource_not_found')
  const metadata = ({ markdown, reading_markdown, sections, ...item }) => item
  if (command.action === 'list') return { snapshot_id: id, source_revision: snapshot.source_revision, documents: visible.map(metadata) }
  if (command.action === 'read') return { snapshot_id: id, source_revision: snapshot.source_revision, ...doc }
  if (command.action === 'raw') {
    const value = command.anchor ? doc.sections.find(section => section.anchor === command.anchor)?.content ?? fail('resource_not_found') : doc.markdown
    return { markdown: value, snapshot_id: id, source_hash: sha(value) }
  }
  if (command.action === 'attachment') {
    const attachment = snapshot.attachments[command.attachment_id]
    if (!visible.some(item => item.reading_markdown.includes('workspace-attachment:' + command.attachment_id)) || !attachment) fail('resource_not_found')
    return attachment
  }
  if (command.action === 'search') {
    const query = command.query.normalize('NFKC').trim().toLowerCase()
    if (!query || query.length > 200) fail('workspace_invalid_input')
    const terms = [...new Set([query, ...query.split(/\s+/), ...query.match(/[\u4e00-\u9fff]{2}/g) ?? []])]
    const items = visible.flatMap(item => (item.sections.length ? item.sections : [{ title: item.title, anchor: '', content: item.reading_markdown }]).map(section => {
      const haystack = (item.title + '\n' + section.title + '\n' + section.content).normalize('NFKC').toLowerCase()
      const score = terms.reduce((sum, term) => sum + (haystack.includes(term) ? (term === query ? 10 : 1) : 0) + (item.title.includes(term) ? 5 : 0), 0)
      const offset = Math.max(0, section.content.toLowerCase().indexOf(query) - 60)
      return { path: item.path, title: item.title, anchor: section.anchor, section_title: section.title, snippet: section.content.slice(offset, offset + 240), score }
    })).filter(item => item.score > 0).sort((a, b) => b.score - a.score || a.path.localeCompare(b.path))
    const counts = new Map()
    const diverse = items.filter(item => { const count = counts.get(item.path) ?? 0; counts.set(item.path, count + 1); return count < 2 }).slice(0, 20)
    return { snapshot_id: id, items: diverse }
  }
  const key = sha(command.owner_id + ':' + command.path), draftFile = path.join(store, 'drafts', key + '.json')
  const sourceRaw = doc ? readSource(source, doc.source_path) : ''
  const draft = () => fs.existsSync(draftFile) ? readJson(draftFile) : { path: doc.path, snapshot_id: id, source_hash: doc.source_hash, revision: 0, markdown: doc.markdown, base_markdown: doc.markdown }
  if (command.action === 'draft') return { ...draft(), snapshot_id: id, source_markdown: sourceRaw, current_source_hash: sha(sourceRaw), conflicted: draft().source_hash !== sha(sourceRaw) }
  if (command.action === 'history') return { items: fs.readdirSync(path.join(store, 'published')).filter(name => /^[a-f\d]{64}\.json$/.test(name)).map(name => snapshotAt(store, name.slice(0, -5))).filter(s => s.documents.some(item => item.path === command.path)).map(s => ({ snapshot_id: s.snapshot_id, source_revision: s.source_revision, source_hash: s.documents.find(item => item.path === command.path).source_hash })) }
  if (command.action === 'operation') {
    const receipt = path.join(store, 'operations', command.operation_id + '.json')
    if (!fs.existsSync(receipt)) fail('resource_not_found')
    const item = readJson(receipt)
    if (item.owner_id !== command.owner_id) fail('resource_not_found')
    if (item.prepared_draft) return locked(store, () => {
      const file = path.join(store, 'drafts', item.draft_key + '.json')
      const current = fs.existsSync(file) ? readJson(file) : { revision: 0 }
      if (current.revision < item.prepared_draft.revision) writeAtomic(file, JSON.stringify(item.prepared_draft))
      return { status: 'saved', operation_id: command.operation_id, draft: item.prepared_draft }
    })
    if (item.candidate_revision && item.candidate_snapshot_id && git(source, 'rev-parse', 'HEAD') === item.candidate_revision && item.result.status !== 'published') {
      return locked(store, () => {
        const prepared = snapshotAt(store, item.candidate_snapshot_id, true)
        installSnapshot(store, prepared)
        git(source, 'restore', '--staged', '--source', item.candidate_revision, '--', ...(item.source_paths ?? [item.source_path]))
        item.result = { status: 'published', operation_id: command.operation_id, snapshot_id: prepared.snapshot_id, source_revision: prepared.source_revision, previous_revision: item.previous_revision }
        writeAtomic(receipt, JSON.stringify(item))
        return item.result
      })
    }
    return item.result.status ? item.result : { status: 'saved', operation_id: command.operation_id, draft: item.result }
  }
  return locked(store, () => {
    if (!/^[a-f\d-]{36}$/i.test(command.operation_id)) fail('workspace_invalid_input')
    const operationFile = path.join(store, 'operations', command.operation_id + '.json'), requestHash = sha(JSON.stringify(command))
    if (fs.existsSync(operationFile)) {
      const receipt = readJson(operationFile)
      if (receipt.owner_id !== command.owner_id || receipt.request_hash !== requestHash) fail('idempotency_conflict')
      if (receipt.prepared_draft) {
        if (draft().revision < receipt.prepared_draft.revision) writeAtomic(draftFile, JSON.stringify(receipt.prepared_draft))
        return receipt.prepared_draft
      }
      return receipt.result
    }
    const existing = draft()
    if (command.action !== 'save' && id !== readJson(path.join(store, 'current.json')).snapshot_id) fail('workspace_version_conflict')
    if (command.action === 'save') {
      const currentSource = readSource(source, doc.source_path)
      if (existing.revision !== command.draft_revision || sha(currentSource) !== command.source_hash) fail('workspace_version_conflict')
      if (typeof command.markdown !== 'string' || Buffer.byteLength(command.markdown) > 200000) fail('workspace_invalid_input')
      const result = { path: doc.path, snapshot_id: id, source_hash: command.source_hash, revision: existing.revision + 1, markdown: command.markdown, base_markdown: command.source_hash === existing.source_hash ? existing.base_markdown : currentSource }
      writeAtomic(operationFile, JSON.stringify({ owner_id: command.owner_id, request_hash: requestHash, result, prepared_draft: result, draft_key: key }))
      writeAtomic(draftFile, JSON.stringify(result))
      return result
    }
    if (!['publish', 'sync', 'restore', 'replace'].includes(command.action)) fail('workspace_invalid_input')
    if (sha(sourceRaw) !== command.source_hash || (command.action !== 'sync' && existing.revision !== command.draft_revision)) fail('workspace_version_conflict')
    let content = command.action === 'sync' ? sourceRaw : existing.markdown
    if (command.action === 'restore') {
      const previous = snapshotAt(store, command.restore_snapshot_id).documents.find(item => item.path === command.path)
      if (!previous) fail('resource_not_found')
      content = previous.markdown
    }
    if (doc.type === 'decision' && content !== doc.markdown && command.action !== 'replace') fail('workspace_decision_requires_replacement')
    const changed = git(source, '-c', 'core.quotepath=false', 'status', '--porcelain', '-z', '--untracked-files=all').split('\0').filter(Boolean)
    if (changed.some(line => line.slice(3) !== doc.source_path)) fail('workspace_version_conflict')
    const before = git(source, 'rev-parse', 'HEAD')
    const pending = { owner_id: command.owner_id, request_hash: requestHash, result: { status: 'pending', operation_id: command.operation_id }, previous_revision: before }
    writeAtomic(operationFile, JSON.stringify(pending))
    const candidate = path.join(store, 'candidates', command.operation_id), indexFile = path.join(store, 'indexes', command.operation_id)
    try {
      fs.mkdirSync(candidate, { recursive: true, ...privateModes })
      // Materialize committed bytes only: ignored files and other editor changes
      // cannot enter a snapshot labelled with a Git revision.
      const cloned = spawnSync('git', ['clone', '--shared', '--no-checkout', '--', source, candidate], { timeout: 30000, encoding: 'utf8' })
      if (cloned.status !== 0) fail('workspace_unavailable')
      git(candidate, 'checkout', '--detach', before)
      const writes = new Map([[doc.source_path, content]])
      if (command.action === 'replace') {
        if (doc.type !== 'decision' || doc.status !== '生效' || !/^decisions\/\d{2}-[^/]+\.md$/.test(command.replacement_path ?? '') || documentPaths(source).includes(command.replacement_path)) fail('workspace_invalid_input')
        const newPath = 'workspace/content/' + command.replacement_path
        if (fs.existsSync(sourceFor(source, newPath))) fail('workspace_version_conflict')
        writeAtomic(sourceFor(candidate, newPath), content)
        const newDoc = readDocument(sourceFor(candidate, newPath), path.join(candidate, 'workspace/content'))
        if (newDoc.frontmatter.type !== 'decision' || newDoc.frontmatter.status !== '生效') fail('workspace_invalid_input')
        const amend = (raw, status, related) => {
          const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(raw)
          if (!match) fail('workspace_invalid_input')
          const yaml = parseDocument(match[1]); yaml.set('status', status); yaml.set('related', related)
          return '---\n' + yaml.toString() + '---\n' + raw.slice(match[0].length)
        }
        writes.set(doc.source_path, amend(doc.markdown, '废弃', [...new Set([...doc.related, command.replacement_path])]))
        writes.set(newPath, amend(content, '生效', [...new Set([...(newDoc.frontmatter.related ?? []), doc.path])]))
        const manifest = readJson(path.join(candidate, 'workspace/internal-documents.json'))
        manifest.documents.push(command.replacement_path)
        writes.set('workspace/internal-documents.json', JSON.stringify(manifest, null, 2) + '\n')
      }
      for (const [file, value] of writes) writeAtomic(sourceFor(candidate, file), value)
      const indexPath = 'workspace/content/index.md'
      const index = readSource(candidate, indexPath)
      const regenerated = regeneratedIndex(index, documents(path.join(candidate, 'workspace/content')))
      if (regenerated !== index) { writes.set(indexPath, regenerated); writeAtomic(sourceFor(candidate, indexPath), regenerated) }
      validate(candidate)
      const next = buildSnapshot(candidate, before)
      if (sha(readSource(source, doc.source_path)) !== command.source_hash || git(source, 'rev-parse', 'HEAD') !== before) fail('workspace_version_conflict')
      fs.mkdirSync(path.dirname(indexFile), { recursive: true, ...privateModes })
      const privateGit = (...args) => {
        const result = spawnSync('git', ['-C', source, ...args], { encoding: 'utf8', timeout: 30000, env: { ...process.env, GIT_INDEX_FILE: indexFile, GIT_AUTHOR_NAME: 'Workspace', GIT_AUTHOR_EMAIL: 'workspace@localhost', GIT_COMMITTER_NAME: 'Workspace', GIT_COMMITTER_EMAIL: 'workspace@localhost' } })
        if (result.status !== 0) fail('workspace_unavailable')
        return result.stdout.trimEnd()
      }
      privateGit('read-tree', before)
      for (const [file, value] of writes) {
        const blob = spawnSync('git', ['-C', source, 'hash-object', '-w', '--stdin'], { input: value, encoding: 'utf8' })
        if (blob.status !== 0) fail('workspace_unavailable')
        privateGit('update-index', '--add', '--cacheinfo', `100644,${blob.stdout.trim()},${file}`)
      }
      const tree = privateGit('write-tree')
      const commit = privateGit('commit-tree', tree, '-p', before, '-m', `docs(workspace):${command.action} ${command.operation_id}`)
      next.source_revision = commit
      const { snapshot_id: unused, ...body } = next
      next.snapshot_id = sha(JSON.stringify(body))
      writeAtomic(path.join(store, 'snapshots', next.snapshot_id + '.json'), JSON.stringify(next))
      writeAtomic(operationFile, JSON.stringify({ ...pending, candidate_snapshot_id: next.snapshot_id, candidate_revision: commit, source_paths: [...writes.keys()], source_path: doc.source_path, expected_source_hash: command.source_hash }))
      privateGit('update-ref', 'HEAD', commit, before)
      // Preserve external changes, including an editor recreating the path.
      for (const [file, value] of writes) {
        const target = sourceFor(source, file)
        const expected = file === doc.source_path ? command.source_hash : fs.existsSync(target) ? sha(spawnSync('git', ['-C', source, 'show', `${before}:${file}`]).stdout) : null
        if (expected === null) {
          fs.mkdirSync(path.dirname(target), { recursive: true, ...privateModes })
          try { fs.writeFileSync(target, value, { flag: 'wx', mode: 0o600 }) } catch { /* Keep the concurrently created file. */ }
        } else if (fs.existsSync(target) && sha(fs.readFileSync(target)) === expected) {
          const backup = path.join(path.dirname(target), `.workspace-${command.operation_id}-${sha(file)}.backup`)
          fs.renameSync(target, backup)
          try {
            if (sha(fs.readFileSync(backup)) !== expected) fail('workspace_version_conflict')
            fs.writeFileSync(target, value, { flag: 'wx', mode: 0o600 })
            fs.rmSync(backup)
          } catch {
            if (!fs.existsSync(target)) fs.linkSync(backup, target)
          }
        }
      }
      git(source, 'restore', '--staged', '--source', commit, '--', ...writes.keys())
      installSnapshot(store, next)
      const result = { status: 'published', operation_id: command.operation_id, snapshot_id: next.snapshot_id, source_revision: next.source_revision, previous_revision: before, published_path: command.replacement_path ?? doc.path }
      writeAtomic(operationFile, JSON.stringify({ ...pending, result }))
      if (command.action !== 'sync') {
        const updated = next.documents.find(item => item.path === doc.path)
        writeAtomic(draftFile, JSON.stringify({ path: doc.path, snapshot_id: next.snapshot_id, source_hash: updated.source_hash, revision: existing.revision + 1, markdown: updated.markdown, base_markdown: updated.markdown }))
      }
      return result
    } catch (error) {
      // The receipt carries a prepared snapshot, so operation reads can recover
      // a committed publication without recommitting or overwriting the source.
      const saved = readJson(operationFile)
      const result = { status: 'failed', operation_id: command.operation_id, code: error.code || 'workspace_unavailable' }
      writeAtomic(operationFile, JSON.stringify({ ...saved, result }))
      return result
    } finally {
      fs.rmSync(candidate, { recursive: true, force: true })
      fs.rmSync(indexFile, { force: true })
    }

  })
}
