import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { stringify } from 'yaml'
import { checkDocuments } from '../scripts/check.mjs'
import {
  contentRoot, repoRoot, documents, regeneratedIndex, rewriteLink,
  markdown, remarkVault, readDocument
} from '../scripts/content.mjs'
import { pageMap } from '../scripts/navigation.mjs'
import { normalizePages } from 'nextra/normalize-pages'
import { exportDocuments } from '../scripts/export.mjs'

const base = { title: '测试文档', summary: '用于验证约束', updated: '2026-10-06' }
const capability = { ...base, type: 'capability', status: '部分可用', release: ['V1', 'V2'], kr: ['KR3'] }
function fixture(t) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'ripplesight-docs-check-'))
  const root = path.join(temporary, 'content')
  fs.mkdirSync(root)
  const manifest = path.join(temporary, 'public-documents.json')
  const registered = new Set()
  t.after(() => fs.rmSync(temporary, { recursive: true, force: true }))
  const write = (relative, fm, body = '# 测试文档\n') => {
    const file = path.join(root, relative)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, `---\n${stringify(fm)}---\n\n${body}`)
    registered.add(relative)
    fs.writeFileSync(manifest, JSON.stringify({ version: 1, documents: [...registered] }))
    return file
  }
  for (const folder of ['product', 'capabilities', 'decisions', 'records', 'research', 'templates', 'views']) {
    fs.mkdirSync(path.join(root, folder))
  }
  write('capabilities/01-测试能力.md', capability)
  write('decisions/01-测试决策.md', { ...base, type: 'decision', status: '生效', decided: '2026-10-06', related: ['capabilities/01-测试能力.md'] })
  write('records/2026-10-06-测试验收.md', { ...base, type: 'record', capability: 'capabilities/01-测试能力.md', criterion: 1, result: '通过', date: '2026-10-06' })
  write('research/2026-10-06-测试调研.md', { ...base, type: 'research', date: '2026-10-06' })
  write('product/prd/01-PRD.md', { ...base, type: 'prd', status: '生效' })
  const index = write('index.md', { ...base, type: 'index' }, '# 测试文档\n\n<!-- index:start -->\n\n<!-- index:end -->\n\n保留尾文。\n')
  fs.writeFileSync(index, regeneratedIndex(fs.readFileSync(index, 'utf8'), documents(root)))
  return { root, write, index }
}

test('当前知识库索引完全一致；生成器保留索引块外的字节', () => {
  const index = fs.readFileSync(path.join(contentRoot, 'index.md'), 'utf8')
  assert.equal(regeneratedIndex(index, documents()), index)
  const wrapped = '前言\n' + index + '\n结语'
  assert.equal(regeneratedIndex(wrapped, documents()), wrapped)
})

test('有效模板字段、日期文件名与空目录通过；模板不参与发布', t => {
  const { root } = fixture(t)
  fs.writeFileSync(path.join(root, 'templates/01-空模板.md'), '无元数据的模板，不发布。')
  assert.deepEqual(checkDocuments(root).errors, [])
})

test('拒绝缺失 frontmatter、必填字段与未知类型', t => {
  const { root, write } = fixture(t)
  write('research/02-未知类型.md', { ...base, type: 'unknown' })
  write('capabilities/02-缺字段.md', { ...capability, kr: null })
  fs.writeFileSync(path.join(root, 'decisions/02-无元数据.md'), '# 没有 frontmatter')
  const errors = checkDocuments(root).errors.join('\n')
  assert.match(errors, /缺少必填字段：kr/)
  assert.match(errors, /未知文档类型/)
  assert.match(errors, /缺少 frontmatter/)
})

test('拒绝所有状态枚举、release、记录结果、错误关联和正文超限', t => {
  const { root, write } = fixture(t)
  write('capabilities/02-错误状态.md', { ...capability, status: '完成', release: ['V3'] }, '字'.repeat(6001))
  write('decisions/02-错误决策.md', { ...base, type: 'decision', status: '待定', decided: '2026-02-30', related: ['capabilities/99-不存在.md'] }, '字'.repeat(2001))
  write('records/02-错误验收.md', { ...base, type: 'record', capability: 'product/prd/01-PRD.md', criterion: 1, result: '完成', date: '2026-10-06' }, '字'.repeat(2001))
  write('product/prd/02-超长PRD.md', { ...base, type: 'prd', status: '生效' }, '字'.repeat(12001))
  const errors = checkDocuments(root).errors.join('\n')
  for (const expected of ['状态无效', 'release 只能', '验收结果必须', '关联文档不存在', 'capability 必须', '超过 6000', '超过 2000', '超过 12000', '有效的 YYYY-MM-DD']) assert.ok(errors.includes(expected), expected)
})

test('拒绝双链、失效本地链接与锚点；代码中的写法示例允许', t => {
  const { root, write } = fixture(t)
  write('product/prd/01-PRD.md', { ...base, type: 'prd', status: '生效' }, '# 测试文档\n\n`[[示例]]`\n\n[有效](../../capabilities/01-测试能力.md#测试文档)\n')
  assert.deepEqual(checkDocuments(root).errors, [])
  write('product/prd/01-PRD.md', { ...base, type: 'prd', status: '生效' }, '# 测试文档\n\n[[双链]] [坏文件](../missing.md) [坏锚点](#missing)\n')
  const errors = checkDocuments(root).errors.join('\n')
  assert.match(errors, /不允许 Obsidian 双链/)
  assert.match(errors, /本地链接不存在/)
  assert.match(errors, /本地锚点不存在/)
})

test('拒绝中文目录、错误命名、重复编号和过期索引', t => {
  const { root, write, index } = fixture(t)
  write('中文目录/01-测试.md', { ...base, type: 'research', date: '2026-10-06' })
  write('product/prd/01-重复编号.md', { ...base, type: 'prd', status: '生效' })
  write('product/prd/无编号.md', { ...base, type: 'prd', status: '生效' })
  fs.appendFileSync(index, '\n正文外新增内容应保留。\n')
  const errors = checkDocuments(root).errors.join('\n')
  for (const expected of ['文件夹必须', '文件名必须', '编号 01 重复', '索引块已过期']) assert.ok(errors.includes(expected), expected)
})

test('根文档链接分流到站内或 GitHub，并保留中文路径和锚点', () => {
  const origin = path.join(repoRoot, 'BACKLOG.md')
  assert.equal(rewriteLink('workspace/content/capabilities/04-评论舆情.md#验收记录', origin), '/capabilities/04-%E8%AF%84%E8%AE%BA%E8%88%86%E6%83%85/#验收记录')
  assert.equal(rewriteLink('workspace/content/index.md#能力', origin), '/#能力')
  for (const file of ['AGENTS.md', 'backend/README.md', 'PROJECT.md#6-数据库']) {
    assert.equal(rewriteLink(file, origin), `https://github.com/StephenQiu30/Ripplesight/blob/main/${file}`)
  }
  const document = readDocument(path.join(contentRoot, 'product/reference/01-进度与优先级.md'))
  const tree = markdown.parse(document.body)
  remarkVault({ document, published: documents() })(tree)
  assert.ok(tree.children.some(node => node.type === 'heading' && node.children[0].value === 'Ripplesight BACKLOG'))
})

test('导航保留 frontmatter 中文标题、五个链接，有验收记录时显示验收组', () => {
  const normalized = normalizePages({ list: pageMap(), route: '/' })
  assert.deepEqual(normalized.topLevelNavbarItems.map(item => item.title), ['PRD', 'PLAN', '进度', '技术架构', 'GitHub'])
  const docs = normalized.docsDirectories.filter(item => item.type === 'doc')
  assert.deepEqual(docs.map(item => item.title), ['术语表', '产品', '能力', '决策', '验收记录', '调研'])
  assert.equal(docs.find(item => item.title === '能力').children[3].title, '评论舆情')
  const product = docs.find(item => item.title === '产品')
  assert.deepEqual(product.children.filter(item => item.children).map(item => item.title), ['产品需求（PRD）', '执行计划（PLAN）', '页面需求', '产品参考'])
  const pageRequirements = product.children.find(item => item.title === '页面需求').children
  assert.ok(pageRequirements.some(item => item.route === '/product/pages/01-今日热点'))
  assert.ok(pageRequirements.some(item => item.route === '/product/pages/52-Agent 读取说明'))
  assert.equal(normalized.topLevelNavbarItems.find(item => item.title === 'PLAN').href, '/product/plan/01-PLAN-workspace项目知识库/')
})

test('PRD、PLAN 与产品参考各自使用 01，目录内重复和 00 编号仍拒绝', t => {
  const { root, write, index } = fixture(t)
  write('product/plan/01-测试计划.md', { ...base, type: 'plan', status: '生效' })
  write('product/reference/01-产品参考.md', { ...base, type: 'pointer' })
  fs.writeFileSync(index, regeneratedIndex(fs.readFileSync(index, 'utf8'), documents(root)))
  assert.deepEqual(checkDocuments(root).errors, [])
  write('product/plan/01-重复计划.md', { ...base, type: 'plan', status: '生效' })
  write('product/prd/00-零编号.md', { ...base, type: 'prd', status: '生效' })
  write('product/plan/中文目录/02-计划.md', { ...base, type: 'plan', status: '生效' })
  const errors = checkDocuments(root).errors.join('\n')
  assert.match(errors, /编号 01 重复/)
  assert.match(errors, /文档编号从 01 开始/)
  assert.match(errors, /文件夹必须使用小写英文字母/)
})

test('计划字段与长度受校验，需求和计划不能回到同一平层', t => {
  const { root, write } = fixture(t)
  write('product/plan/01-缺状态.md', { ...base, type: 'plan' })
  write('product/plan/02-长计划.md', { ...base, type: 'plan', status: '生效' }, '字'.repeat(12001))
  write('product/plan/03-错误状态.md', { ...base, type: 'plan', status: '完成' })
  write('product/02-放错需求.md', { ...base, type: 'prd', status: '生效' })
  write('product/prd/02-放错计划.md', { ...base, type: 'plan', status: '生效' })
  const errors = checkDocuments(root).errors.join('\n')
  for (const expected of ['缺少必填字段：status', '超过 12000', '状态无效', 'PRD 必须位于 product/prd/', 'PLAN 必须位于 product/plan/']) assert.ok(errors.includes(expected), expected)
})

test('未登记资料不进入目录或 AI 产物，重新导出清除残留原文', t => {
  const { root } = fixture(t)
  const unpublished = 'product/prd/02-私密草稿.md'
  const marker = 'UNPUBLISHED_CONTENT_MUST_NOT_EXPORT'
  fs.writeFileSync(path.join(root, unpublished), `---\n${stringify({ ...base, type: 'prd', status: '草稿', visibility: 'private' })}---\n\n${marker}\n`)
  const published = documents(root)
  assert.ok(!published.some(item => item.relative === unpublished))
  const out = path.join(root, '../out')
  fs.mkdirSync(path.join(out, 'raw', 'product', 'prd'), { recursive: true })
  fs.writeFileSync(path.join(out, 'raw', unpublished), marker)
  exportDocuments(out, published)
  assert.ok(!fs.existsSync(path.join(out, 'raw', unpublished)))
  for (const file of ['llms.txt', 'llms-full.txt']) {
    const raw = fs.readFileSync(path.join(out, file), 'utf8')
    assert.ok(!raw.includes(marker) && !raw.includes(unpublished))
  }
  const index = regeneratedIndex(fs.readFileSync(path.join(root, 'index.md'), 'utf8'), published)
  assert.ok(!index.includes(unpublished))
})

test('公开清单拒绝私密文档、草稿、重复登记、缺失文件和真实路径越界', t => {
  const { root, write } = fixture(t)
  const manifest = path.resolve(root, '../public-documents.json')
  const original = JSON.parse(fs.readFileSync(manifest, 'utf8'))
  write('product/prd/02-私密资料.md', { ...base, type: 'prd', status: '生效', visibility: 'private' })
  assert.throws(() => documents(root), /受保护文档不能进入公开清单/)
  write('product/prd/02-私密资料.md', { ...base, type: 'prd', status: '草稿' })
  assert.throws(() => documents(root), /草稿不能进入公开清单/)
  for (const [extra, expected] of [['../AGENTS.md', /公开文档路径无效/], ['templates/01-模板.md', /公开文档路径无效/], ['index.md', /重复登记/], ['product/prd/99-不存在.md', /ENOENT/]]) {
    fs.writeFileSync(manifest, JSON.stringify({ version: 1, documents: [...original.documents, extra] }))
    assert.throws(() => documents(root), expected)
  }
  const outside = path.resolve(root, '../outside.md')
  fs.writeFileSync(outside, 'outside vault')
  fs.symlinkSync(outside, path.join(root, 'product/prd/03-越界链接.md'))
  fs.writeFileSync(manifest, JSON.stringify({ version: 1, documents: [...original.documents, 'product/prd/03-越界链接.md'] }))
  assert.throws(() => documents(root), /真实路径越界/)
  fs.rmSync(manifest)
  assert.throws(() => documents(root), /ENOENT/)
})

test('公开文档中的未登记资料链接不会自动退回 GitHub 原文出口', () => {
  assert.throws(() => rewriteLink('product/prd/99-未登记.md', path.join(contentRoot, 'index.md')), /链接指向未公开登记的资料/)
  assert.equal(rewriteLink('templates/05-执行计划.md', path.join(contentRoot, 'index.md')), 'https://github.com/StephenQiu30/Ripplesight/blob/main/workspace/content/templates/05-%E6%89%A7%E8%A1%8C%E8%AE%A1%E5%88%92.md')
  assert.ok(!documents().some(item => item.relative.startsWith('templates/')))
})
