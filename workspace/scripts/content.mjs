import fs from 'node:fs'
import path from 'node:path'
import { parse as parseYaml } from 'yaml'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import { visit } from 'unist-util-visit'

// All package scripts run in workspace/. import.meta.dirname is not preserved
// when Next bundles this module into its server chunks.
export const workspaceRoot = process.cwd()
export const repoRoot = path.resolve(workspaceRoot, '..')
export const contentRoot = path.join(workspaceRoot, 'content')
export const basePath = '/Ripplesight'
export const siteUrl = `https://stephenqiu30.github.io${basePath}`
export const githubUrl = 'https://github.com/StephenQiu30/Ripplesight/blob/main'
export const groups = [
  ['product', '产品'], ['capabilities', '能力'], ['decisions', '决策'],
  ['records', '验收记录'], ['research', '调研']
]
export const excluded = new Set(['templates', 'views', '.obsidian'])
export const productGroups = [
  ['product/prd', '产品需求（PRD）'],
  ['product/plan', '执行计划（PLAN）'],
  ['product/pages', '页面需求'],
  ['product/reference', '产品参考']
]
export const markdown = unified().use(remarkParse).use(remarkGfm)

export function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true })
    .sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
    .flatMap(entry => {
      if (entry.name.startsWith('.') || excluded.has(entry.name)) return []
      const absolute = path.join(directory, entry.name)
      return entry.isDirectory() ? walk(absolute) : absolute.endsWith('.md') ? [absolute] : []
    })
}

export function readDocument(file, root = contentRoot) {
  const raw = fs.readFileSync(file, 'utf8')
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(raw)
  if (!match) throw new Error('缺少 frontmatter（文件必须以 --- 开头）')
  const relative = path.relative(root, file).split(path.sep).join('/')
  // Parse template placeholders as text while leaving the authored file intact.
  const metadata = relative.startsWith('templates/')
    ? match[1].replaceAll('{{date:YYYY-MM-DD}}', '"{{date:YYYY-MM-DD}}"')
    : match[1]
  const frontmatter = parseYaml(metadata)
  if (!frontmatter || typeof frontmatter !== 'object' || Array.isArray(frontmatter)) {
    throw new Error('frontmatter 必须是字段映射')
  }
  return { file, relative, raw, body: raw.slice(match[0].length), frontmatter }
}

export function publicDocumentPaths(root = contentRoot) {
  const manifest = JSON.parse(fs.readFileSync(path.resolve(root, '../public-documents.json'), 'utf8'))
  if (manifest.version !== 1 || !Array.isArray(manifest.documents)) {
    throw new Error('公开文档清单必须声明 version: 1 和 documents 数组')
  }
  const seen = new Set()
  for (const relative of manifest.documents) {
    if (typeof relative !== 'string' || !relative.endsWith('.md') ||
      path.posix.normalize(relative) !== relative || relative.startsWith('/') || relative.includes('\\') ||
      relative.split('/').some(part => part.startsWith('.') || excluded.has(part))) {
      throw new Error(`公开文档路径无效：${relative}`)
    }
    if (seen.has(relative)) throw new Error(`公开文档重复登记：${relative}`)
    seen.add(relative)
  }
  return [...seen].sort()
}

export function documents(root = contentRoot) {
  const realRoot = fs.realpathSync(root)
  return publicDocumentPaths(root).map(relative => {
    const file = path.join(root, relative)
    const realFile = fs.realpathSync(file)
    if (!realFile.startsWith(realRoot + path.sep)) throw new Error(`公开文档真实路径越界：${relative}`)
    const document = readDocument(file, root)
    if (document.frontmatter.visibility && document.frontmatter.visibility !== 'public') {
      throw new Error(`受保护文档不能进入公开清单：${relative}`)
    }
    if (document.frontmatter.status === '草稿') throw new Error(`草稿不能进入公开清单：${relative}`)
    return document
  })
}

// Reviewed authoring templates may be linked to their existing public Git source,
// but are never rendered, indexed or included in raw/AI exports.
export function publicReferencePaths(root = contentRoot) {
  const manifest = JSON.parse(fs.readFileSync(path.resolve(root, '../public-documents.json'), 'utf8'))
  const references = manifest.references ?? []
  if (!Array.isArray(references)) throw new Error('公开原文引用必须为数组')
  const realRoot = fs.realpathSync(root)
  for (const relative of references) {
    if (typeof relative !== 'string' || !/^templates\/\d{2}-[^/\\]+\.md$/.test(relative)) {
      throw new Error(`公开原文引用路径无效：${relative}`)
    }
    const file = path.join(root, relative)
    if (!fs.realpathSync(file).startsWith(realRoot + path.sep)) throw new Error(`公开原文引用越界：${relative}`)
    const { frontmatter } = readDocument(file, root)
    if ((frontmatter.visibility && frontmatter.visibility !== 'public') || frontmatter.status === '草稿') {
      throw new Error(`受保护资料不能作为公开原文引用：${relative}`)
    }
  }
  return references
}

export function routeFor(relative) {
  return relative === 'index.md' ? '/' : `/${relative.replace(/\.md$/, '')}/`
}

export function encodedPath(value) {
  return value.split('/').map(segment => encodeURIComponent(segment)).join('/')
}

export function sourceFile(document, sourceRepoRoot = repoRoot) {
  const source = document.frontmatter.source
  if (!source) return undefined
  if (typeof source !== 'string') throw new Error('source 必须是相对路径')
  const file = path.resolve(path.dirname(document.file), source)
  if (!['BACKLOG.md', 'PROJECT.md', 'AGENTS.md'].some(name => file === path.join(sourceRepoRoot, name)) ||
    fs.realpathSync(file) !== file) {
    throw new Error('source 只允许嵌入仓库根目录的 BACKLOG.md、PROJECT.md 或 AGENTS.md 原文')
  }
  return file
}

export function splitLink(url) {
  const match = /^([^?#]*)([\s\S]*)$/.exec(url)
  return [decodeURIComponent(match[1]), match[2]]
}

export function rewriteLink(url, origin, published = documents()) {
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(url)) return url
  const [target, suffix] = splitLink(url)
  if (!target) return url
  const absolute = path.resolve(path.dirname(origin), target)
  const document = published.find(item => item.file === absolute)
  // Next Link adds basePath; internal hrefs must not include it twice.
  if (document) return encodedPath(routeFor(document.relative)) + suffix
  if (absolute.startsWith(contentRoot + path.sep) &&
    !publicReferencePaths().includes(path.relative(contentRoot, absolute).split(path.sep).join('/'))) {
    throw new Error(`链接指向未公开登记的资料：${url}`)
  }
  const relative = path.relative(repoRoot, absolute).split(path.sep).join('/')
  if (relative.startsWith('../') || relative === '..') throw new Error(`链接超出仓库：${url}`)
  return `${githubUrl}/${encodedPath(relative)}${suffix}`
}

export function rewriteTree(tree, origin, published) {
  visit(tree, node => {
    if (['link', 'image', 'definition'].includes(node.type)) {
      node.url = rewriteLink(node.url, origin, published)
    }
  })
}

// Runs before Nextra's heading/TOC plugins, so embedded headings are indexed too.
export function remarkVault({ document, published }) {
  return tree => {
    rewriteTree(tree, document.file, published)
    const source = sourceFile(document)
    if (source) {
      const embedded = markdown.parse(fs.readFileSync(source, 'utf8'))
      rewriteTree(embedded, source, published)
      tree.children.push(...embedded.children)
    }
  }
}

export const indexPattern = /(<!-- index:start[^\n]*-->)[\s\S]*?(<!-- index:end -->)/

export function indexBlock(published) {
  const cell = value => String(value ?? '—').replaceAll('|', '\\|').replace(/\r?\n/g, ' ')
  const table = (items, capability = false) => {
    if (!items.length) return '（暂无）'
    const header = capability
      ? '| 文档 | 摘要 | 状态 | 版本 |\n|---|---|---|---|'
      : '| 文档 | 摘要 | 状态 |\n|---|---|---|'
    const rows = items.map(({ relative, frontmatter: fm }) => {
      const cells = [`[${cell(fm.title)}](${relative})`, cell(fm.summary), cell(fm.status ?? fm.date)]
      if (capability) cells.push(cell(fm.release?.join(', ')))
      return `| ${cells.join(' | ')} |`
    })
    return [header, ...rows].join('\n')
  }
  return groups.map(([folder, title]) => {
    const heading = `### ${title}\n\n`
    if (folder === 'product') {
      return heading + productGroups.map(([prefix, label]) => {
        const items = published.filter(item => path.posix.dirname(item.relative) === prefix)
        return `#### ${label}\n\n${table(items)}`
      }).join('\n\n')
    }
    return heading + table(published.filter(item => item.relative.startsWith(`${folder}/`)), folder === 'capabilities')
  }).join('\n\n')
}

export function regeneratedIndex(raw, published) {
  if (!indexPattern.test(raw)) throw new Error('首页缺少唯一的 index:start / index:end 生成标记')
  if ((raw.match(/<!-- index:start/g) ?? []).length !== 1 || (raw.match(/<!-- index:end -->/g) ?? []).length !== 1) {
    throw new Error('首页的索引生成标记必须各出现一次')
  }
  return raw.replace(indexPattern, (_, start, end) => `${start}\n\n${indexBlock(published)}\n\n${end}`)
}
