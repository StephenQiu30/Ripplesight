import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import {
  workspaceRoot, documents, groups, productGroups, routeFor, encodedPath, siteUrl, sourceFile
} from './content.mjs'

export function exportDocuments(out, published = documents()) {
  fs.mkdirSync(out, { recursive: true })
  fs.rmSync(path.join(out, 'raw'), { recursive: true, force: true })
  const introduction = '# Ripplesight 文档\n\nRipplesight 是公开资讯阅读与个人舆情监控工具，供个人非商业使用。本文档包括产品需求、执行计划、能力、决策、验收记录与调研。\n\n'
  const entry = item => `- [${item.frontmatter.title}](${siteUrl}${encodedPath(routeFor(item.relative))})：${item.frontmatter.summary}\n  - 原始 Markdown：${siteUrl}/raw/${encodedPath(item.relative)}`
  const sections = [['', '入口与术语'], ...groups.flatMap(group => group[0] === 'product' ? productGroups : [group])].flatMap(([folder, title]) => {
    const pages = published.filter(item => folder === 'product' ? path.posix.dirname(item.relative) === folder : folder ? item.relative.startsWith(`${folder}/`) : !item.relative.includes('/'))
    return pages.length ? [`## ${title}\n\n${pages.map(entry).join('\n')}\n`] : []
  })
  fs.writeFileSync(path.join(out, 'llms.txt'), introduction + sections.join('\n'))
  const full = [introduction]
  for (const document of published) {
    const target = path.join(out, 'raw', document.relative)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    // Preserve authored Markdown byte-for-byte. Pointers also expose their full source.
    const source = sourceFile(document)
    const raw = document.raw + (source ? '\n' + fs.readFileSync(source, 'utf8') : '')
    fs.writeFileSync(target, raw)
    full.push(`<!-- ${siteUrl}${encodedPath(routeFor(document.relative))} -->\n\n${raw}\n\n`)
  }
  fs.writeFileSync(path.join(out, 'llms-full.txt'), full.join(''))
  fs.writeFileSync(path.join(out, '.nojekyll'), '')
  console.log(`AI 文档已生成：llms.txt、llms-full.txt、raw/（${published.length} 页）。`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  exportDocuments(path.join(workspaceRoot, 'out'))
}
