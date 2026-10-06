import { documents, groups, productGroups, routeFor } from './content.mjs'

export function pageMap() {
  const published = documents()
  const page = item => ({
    name: item.relative.split('/').at(-1).replace(/\.md$/, ''),
    title: item.frontmatter.title,
    route: routeFor(item.relative).replace(/\/$/, '') || '/',
    frontMatter: { ...item.frontmatter, sidebarTitle: item.frontmatter.title }
  })
  const metadata = {
    index: { title: '文档首页', display: 'hidden' },
    '01-术语表': { title: '术语表' }
  }
  for (const [folder, title] of groups) {
    if (published.some(item => item.relative.startsWith(`${folder}/`))) metadata[folder] = { title }
  }
  const navigation = [
    ['prd', 'PRD', '/product/prd/01-PRD/'],
    ['plan', 'PLAN', '/product/plan/01-PLAN-workspace项目知识库/'],
    ['progress', '进度', '/product/01-进度与优先级/'],
    ['architecture', '技术架构', '/product/02-技术架构/'],
    ['github', 'GitHub', 'https://github.com/StephenQiu30/hotkey-server']
  ]
  for (const [key, title, href] of navigation) {
    metadata[key] = { title, type: 'page', href }
  }
  // Supply the normalized PageMap shape directly. Importing getPageMap's
  // module would make the content loader discover private vault templates.
  return [
    { data: metadata },
    ...published.filter(item => !item.relative.includes('/')).map(page),
    ...groups.flatMap(([folder, title]) => {
      const children = folder === 'product' ? productGroups.flatMap(([prefix, label]) => {
        const pages = published.filter(item => item.relative.slice(0, item.relative.lastIndexOf('/')) === prefix).map(page)
        if (!pages.length) return []
        return prefix === 'product' ? pages : [{ name: prefix.split('/').at(-1), title: label, route: `/${prefix}`, children: pages }]
      }) : published.filter(item => item.relative.startsWith(`${folder}/`)).map(page)
      return children.length ? [{ name: folder, title, route: `/${folder}`, children }] : []
    }),
    ...navigation.map(([name, title, href]) => ({ name, title, href, route: href }))
  ]
}
