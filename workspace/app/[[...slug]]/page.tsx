import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { compileMdx } from 'nextra/compile'
import { evaluate } from 'nextra/evaluate'
import { useMDXComponents } from '../../mdx-components'
import { documents, remarkVault, routeFor, siteUrl } from '../../scripts/content.mjs'

type Props = { params: Promise<{ slug?: string[] }> }

export const dynamicParams = false

export function generateStaticParams() {
  return documents().map(item => ({
    slug: item.relative === 'index.md' ? [] : item.relative.replace(/\.md$/, '').split('/')
  }))
}

async function documentFor(props: Props) {
  const { slug = [] } = await props.params
  // Static export passes non-ASCII route segments percent-encoded.
  const relative = slug.length ? `${slug.map(decodeURIComponent).join('/')}.md` : 'index.md'
  const published = documents()
  const document = published.find(item => item.relative === relative)
  if (!document) notFound()
  return { document, published }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { document } = await documentFor(props)
  return {
    title: document.frontmatter.title,
    description: document.frontmatter.summary,
    alternates: { canonical: siteUrl + routeFor(document.relative) }
  }
}

export default async function Page(props: Props) {
  const { document, published } = await documentFor(props)
  const components = useMDXComponents()
  const compiled = await compileMdx(document.raw, {
    filePath: document.file,
    mdxOptions: {
      format: 'md',
      remarkPlugins: [[remarkVault, { document, published }]]
    }
  })
  const { default: Content, toc, metadata, sourceCode } = evaluate(compiled, components)
  const Wrapper = components.wrapper
  return (
    <Wrapper toc={toc} metadata={{ ...metadata, ...document.frontmatter, filePath: document.relative }} sourceCode={sourceCode}
      bottomContent={<a href={`/Ripplesight/raw/${document.relative}`}>原始 Markdown</a>}>
      <Content />
    </Wrapper>
  )
}
