import type { Root } from 'mdast'
import type { Plugin } from 'unified'

export interface Frontmatter {
  type: string
  title: string
  summary: string
  updated: string
  status?: string
  visibility?: 'public' | 'private'
  release?: string[]
  kr?: string[]
  decided?: string
  date?: string
  source?: string
  related?: string[]
  capability?: string
  criterion?: string | number
  result?: string
}
export interface Document {
  file: string
  relative: string
  raw: string
  body: string
  frontmatter: Frontmatter
}
export const siteUrl: string
export function documents(root?: string): Document[]
export function routeFor(relative: string): string
export const remarkVault: Plugin<[{ document: Document; published: Document[] }], Root>
