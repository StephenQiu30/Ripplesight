import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { documents, encodedPath, routeFor, workspaceRoot, groups } from './content.mjs'

const address = process.env.DOCS_PREVIEW_URL || 'http://127.0.0.1:8668/Ripplesight'
const out = path.join(workspaceRoot, 'out')
const published = documents()
async function get(relative) {
  const response = await fetch(address + encodedPath(relative))
  assert.equal(response.status, 200, relative)
  return response.text()
}
const links = html => [...html.matchAll(/<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)]
  .map(match => ({ href: match[1], text: match[2].replace(/<[^>]*>/g, '').trim() }))

for (const document of published) {
  const html = await get(routeFor(document.relative))
  assert.ok(html.includes('data-pagefind-body'), `${document.relative} 没有渲染正文`)
  assert.ok(!html.includes('NEXT_HTTP_ERROR_FALLBACK'), `${document.relative} 渲染为错误页`)
  const raw = await get(`/raw/${document.relative}`)
  assert.ok(raw.startsWith(document.raw), `${document.relative} 原文有变化`)
}
const home = await get('/')
for (const title of ['产品', '产品需求（PRD）', '执行计划（PLAN）', '能力', '决策', '调研', '术语表', '跳至正文']) assert.ok(home.includes(title), `首页缺少 ${title}`)
for (const title of ['PRD', 'PLAN', '进度', '技术架构', 'GitHub']) assert.ok(links(home).some(link => link.text === title), `导航缺少 ${title}`)
for (const [folder] of groups) {
  if (!published.some(item => item.relative.startsWith(folder + '/'))) assert.ok(!links(home).some(link => link.href === '/Ripplesight/' + folder + '/'), `空目录 ${folder} 进入导航`)
}
const capability = await get('/capabilities/04-评论舆情/')
for (const value of ['部分可用', 'V1, V2', 'KR2, KR3, KR4', '2026-10-06']) assert.ok(capability.includes(value), `缺少元数据 ${value}`)
assert.ok(links(capability).some(link => link.text === '评论舆情'), '侧栏没有 frontmatter 标题')
const progress = await get('/product/reference/01-进度与优先级/')
assert.ok(progress.includes('Ripplesight BACKLOG') && progress.includes('由 Claude 写任务卡并派给 Codex 开发'), 'BACKLOG 首尾正文未嵌入')
const progressLinks = links(progress)
assert.ok(progressLinks.some(link => decodeURIComponent(link.href) === '/Ripplesight/capabilities/04-评论舆情/'), 'BACKLOG 能力链接未改写')
assert.ok(progressLinks.some(link => link.href === 'https://github.com/StephenQiu30/Ripplesight/blob/main/AGENTS.md'), 'BACKLOG 工程规范链接未改写')
const architecture = await get('/product/reference/02-技术架构/')
for (const heading of ['1. 技术栈', '6. 数据库', '10. 配置与部署', '文档预览']) assert.ok(architecture.includes(heading), `PROJECT 缺少 ${heading}`)
const engineering = await get('/product/reference/03-工程规范/')
for (const heading of ['Ripplesight 工程规范', '6. 什么算', '7. 提交与推送']) assert.ok(engineering.includes(heading), `AGENTS 原文缺少 ${heading}`)
const engineeringRaw = await get('/raw/product/reference/03-工程规范.md')
assert.ok(engineeringRaw.endsWith(fs.readFileSync(path.join(workspaceRoot, '../AGENTS.md'), 'utf8')), '工程规范原文导出不完整')
const plan = await get('/product/plan/01-PLAN-workspace项目知识库/')
const planMetadata = [...plan.matchAll(/<p\b[^>]*aria-label="文档元数据"[^>]*>([\s\S]*?)<\/p>/g)]
  .map(match => match[1].replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, ' ')).join(' ')
assert.ok(/状态\s*：\s*生效/.test(planMetadata) && /更新\s*：\s*2026-10-06/.test(planMetadata), 'PLAN 元数据未显示')
const llms = await get('/llms.txt')
const full = await get('/llms-full.txt')
for (const document of published) {
  assert.ok(llms.includes(document.frontmatter.title) && llms.includes(document.frontmatter.summary), `llms 缺少 ${document.relative}`)
  assert.ok(full.includes(document.raw), `llms-full 缺少 ${document.relative}`)
}
assert.ok(!llms.includes('/templates/') && !llms.includes('/views/') && !llms.includes('/.obsidian/'), '私有目录进入 AI 索引')
for (const folder of ['templates', 'views', '.obsidian']) assert.ok(!fs.existsSync(path.join(out, folder)), `${folder} 被发布`)
console.log(`HTTP 与导出检查通过：${published.length} 个页面与原文；导航、元数据、全文嵌入、改写链接、AI 导出有效。`)

// Exercise the actual exported search bundle in Node, fetching assets over HTTP.
const pagefind = await import(pathToFileURL(path.join(out, '_pagefind/pagefind.js')).href)
await pagefind.options({ basePath: address + '/_pagefind/', baseUrl: '/' })
for (const query of ['舆情', '评论', '情感']) {
  const result = await pagefind.search(query)
  assert.ok(result.results.length > 0, `中文搜索无结果：${query}`)
  const top = await result.results[0].data()
  await get(top.url.split('#')[0])
  console.log(`${query}：${result.results.length} 条；首条 ${top.meta.title} → /Ripplesight${top.url}`)
}
