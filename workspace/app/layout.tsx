import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Footer, Layout, Navbar } from 'nextra-theme-docs'
import { Head, Search } from 'nextra/components'
import { pageMap } from '../scripts/navigation.mjs'
import 'nextra-theme-docs/style.css'
import './style.css'

export const metadata: Metadata = {
  title: { default: 'HotKey 文档', template: '%s · HotKey 文档' },
  description: 'HotKey 产品、能力、决策、验收记录与调研文档。'
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          pageMap={pageMap()}
          navbar={<Navbar logo="HotKey 文档" />}
          footer={<Footer>HotKey 文档 · 个人非商业使用</Footer>}
          search={<Search placeholder="搜索文档…" emptyResult="没有找到相关文档。" loading="搜索中…" errorText="无法加载搜索索引，请刷新重试。" />}
          docsRepositoryBase="https://github.com/StephenQiu30/hotkey-server/tree/main/workspace/content"
          editLink="在 GitHub 编辑此页"
          feedback={{ content: '反馈此页', labels: 'documentation' }}
          copyPageButton={false}
          themeSwitch={{ dark: '深色', light: '浅色', system: '跟随系统' }}
          toc={{ title: '本页目录', backToTop: '返回顶部' }}
          sidebar={{ defaultMenuCollapseLevel: 1, toggleButton: false }}
        >
          {children}
        </Layout>
      </body>
    </html>
  )
}
