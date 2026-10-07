import nextra from 'nextra'

const withNextra = nextra({ mdxOptions: { format: 'md' } })

export default withNextra({
  output: 'export',
  basePath: '/Ripplesight',
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  // Keep the standalone package independent of the frontend lockfile.
  outputFileTracingRoot: import.meta.dirname
})
