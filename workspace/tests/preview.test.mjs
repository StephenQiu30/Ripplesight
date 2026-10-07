import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { once } from 'node:events'
import test from 'node:test'
import { captureSources, fingerprint, rebuild } from '../scripts/watch.mjs'
import { createPreview } from '../scripts/preview.mjs'

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ripplesight-live-docs-'))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const sourceRoot = path.join(root, 'source'), buildRoot = path.join(root, 'build')
  const previewRoot = path.join(root, 'preview')
  fs.mkdirSync(path.join(sourceRoot, 'workspace/content'), { recursive: true })
  fs.mkdirSync(buildRoot)
  const source = path.join(sourceRoot, 'workspace/content/index.md')
  fs.writeFileSync(source, 'original')
  const build = async () => {
    const out = path.join(buildRoot, 'workspace/out')
    fs.mkdirSync(path.join(out, '_pagefind'), { recursive: true })
    fs.writeFileSync(path.join(out, 'index.html'), '<html><body>' + fs.readFileSync(path.join(buildRoot, 'workspace/content/index.md')) + '</body></html>')
    fs.writeFileSync(path.join(out, '404.html'), 'not found')
    fs.writeFileSync(path.join(out, '_pagefind/pagefind.js'), 'search')
    fs.writeFileSync(path.join(out, 'llms-full.txt'), fs.readFileSync(path.join(buildRoot, 'workspace/content/index.md')))
  }
  return { sourceRoot, buildRoot, previewRoot, source, build }
}

async function preview(t, out, liveReload = true) {
  const result = createPreview({ out, liveReload })
  result.server.listen(0, '127.0.0.1')
  await once(result.server, 'listening')
  t.after(() => { result.server.closeAllConnections(); result.server.close() })
  return { ...result, address: `http://127.0.0.1:${result.server.address().port}` }
}

test('热更新来源筛选排除凭据、Git、本机状态与生成物，新增及删除文档改变版本', t => {
  const f = fixture(t)
  for (const relative of ['.env', 'workspace/.env.local', 'workspace/node_modules/secret', 'workspace/.preview/current', 'workspace/out/index.html', 'workspace/.tools/config.json', 'workspace/.git/config']) {
    fs.mkdirSync(path.dirname(path.join(f.sourceRoot, relative)), { recursive: true })
    fs.writeFileSync(path.join(f.sourceRoot, relative), 'must not copy')
  }
  assert.deepEqual(captureSources(f.sourceRoot).map(file => file.relative), ['workspace/content/index.md'])
  const original = fingerprint(captureSources(f.sourceRoot))
  const extra = path.join(f.sourceRoot, 'workspace/content/extra.md')
  fs.writeFileSync(extra, 'new')
  assert.notEqual(fingerprint(captureSources(f.sourceRoot)), original)
  fs.rmSync(extra)
  assert.equal(fingerprint(captureSources(f.sourceRoot)), original)
})

test('文档来源拒绝符号链接逃逸', t => {
  const f = fixture(t)
  const outside = path.join(f.sourceRoot, '../private.md')
  fs.writeFileSync(outside, 'private')
  fs.symlinkSync(outside, path.join(f.sourceRoot, 'workspace/content/leak.md'))
  assert.throws(() => captureSources(f.sourceRoot), /不允许符号链接/)
})

test('构建失败保留上一版；构建中新修改不混入已捕获版本，下一轮才发布', async t => {
  const f = fixture(t)
  await rebuild(f)
  const current = path.join(f.previewRoot, 'current')
  const first = fs.readlinkSync(current)
  fs.writeFileSync(f.source, 'changed')
  await assert.rejects(rebuild({ ...f, build: async () => { throw new Error('invalid document') } }), /invalid document/)
  assert.equal(fs.readlinkSync(current), first)
  await rebuild({ ...f, build: async () => { await f.build(); fs.writeFileSync(f.source, 'newer') } })
  assert.notEqual(fs.readlinkSync(current), first)
  assert.equal(fs.readFileSync(path.join(current, 'llms-full.txt'), 'utf8'), 'changed')
  assert.match(fs.readFileSync(path.join(current, 'index.html'), 'utf8'), /changed/)
  await rebuild(f)
  assert.notEqual(fs.readlinkSync(current), first)
  assert.equal(fs.readFileSync(path.join(current, 'llms-full.txt'), 'utf8'), 'newer')
  assert.match(fs.readFileSync(path.join(current, 'index.html'), 'utf8'), /newer/)
})

test('缺少搜索索引的构建不能替换当前完整版本', async t => {
  const f = fixture(t)
  await rebuild(f)
  const first = fs.readlinkSync(path.join(f.previewRoot, 'current'))
  await assert.rejects(rebuild({ ...f, build: async () => { await f.build(); fs.rmSync(path.join(f.buildRoot, 'workspace/out/_pagefind/pagefind.js')) } }), /完整页面与搜索索引/)
  assert.equal(fs.readlinkSync(path.join(f.previewRoot, 'current')), first)
})

test('预览只提供产物，保留 Markdown MIME、重定向和 404，阻止路径与符号链接越界', async t => {
  const f = fixture(t)
  await rebuild(f)
  const out = path.join(f.previewRoot, 'current')
  fs.mkdirSync(path.join(out, 'raw'))
  fs.writeFileSync(path.join(out, 'raw/doc.md'), 'raw')
  fs.symlinkSync(f.source, path.join(out, 'leak.md'))
  const p = await preview(t, out, false)
  const redirect = await fetch(p.address + '/Ripplesight', { redirect: 'manual' })
  assert.equal(redirect.status, 308)
  assert.equal(redirect.headers.get('location'), '/Ripplesight/')
  const raw = await fetch(p.address + '/Ripplesight/raw/doc.md')
  assert.equal(raw.headers.get('content-type'), 'text/markdown; charset=utf-8')
  assert.equal(raw.headers.get('cache-control'), 'no-store')
  for (const relative of ['/Ripplesight/missing', '/Ripplesight/.env', '/outside']) assert.equal((await fetch(p.address + relative)).status, 404)
  assert.equal((await fetch(p.address + '/Ripplesight/leak.md')).status, 403)
  assert.equal((await fetch(p.address + '/Ripplesight/%2e%2e%2fprivate.md')).status, 403)
  assert.ok(!(await (await fetch(p.address + '/Ripplesight/')).text()).includes('__reload.js'))
})

test('开发预览通知已连接的浏览器切换版本，静态产物不注入脚本', async t => {
  const f = fixture(t)
  const version = await rebuild(f)
  const out = path.join(f.previewRoot, 'current')
  const p = await preview(t, out)
  p.refresh(version)
  const html = await (await fetch(p.address + '/Ripplesight/')).text()
  assert.ok(html.includes('__reload.js?version=' + version))
  assert.ok(!fs.readFileSync(path.join(out, 'index.html'), 'utf8').includes('__reload.js'))
  const controller = new AbortController()
  t.after(() => controller.abort())
  const events = await fetch(p.address + '/Ripplesight/__updates', { signal: controller.signal })
  const reader = events.body.getReader()
  assert.match(new TextDecoder().decode((await reader.read()).value), new RegExp('data: ' + version))
  p.refresh('next-version')
  assert.match(new TextDecoder().decode((await reader.read()).value), /data: next-version/)
  await reader.cancel()
})
