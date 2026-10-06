import type { MDXWrapper } from 'nextra'
import { Mermaid } from 'nextra/components'
import { useMDXComponents as themeComponents } from 'nextra-theme-docs'
import type { ComponentProps } from 'react'
import type { Frontmatter } from './scripts/content.mjs'

const theme = themeComponents()
const ThemeWrapper = theme.wrapper
const metadataTypes = new Set(['capability', 'decision', 'record', 'research', 'prd', 'plan'])

function PageMetadata({ metadata }: Pick<ComponentProps<MDXWrapper>, 'metadata'>) {
  const frontmatter = metadata as typeof metadata & Frontmatter
  if (!metadataTypes.has(frontmatter.type)) return null
  const fields = [
    ['状态', frontmatter.status],
    ['版本', frontmatter.release?.join(', ')],
    ['KR', frontmatter.kr?.join(', ')],
    ['决策日期', frontmatter.decided],
    ['日期', frontmatter.date],
    ['更新', frontmatter.updated]
  ].filter(([, value]) => value)
  return (
    <p className="page-metadata" aria-label="文档元数据" data-pagefind-ignore>
      {fields.map(([label, value]) => <span key={label}>{label}：{value}</span>)}
    </p>
  )
}

const Wrapper: MDXWrapper = ({ children, ...props }) => (
  <ThemeWrapper {...props}>
    <PageMetadata metadata={props.metadata} />
    {children}
  </ThemeWrapper>
)

export function useMDXComponents(components = {}) {
  return { ...theme, Mermaid, wrapper: Wrapper, ...components }
}
