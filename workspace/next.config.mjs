import nextra from 'nextra'

const withNextra = nextra({ mdxOptions: { format: 'md' } })

export default withNextra({
  output: 'export',
  basePath: '/hotkey-server',
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  // Keep the standalone package independent of the frontend lockfile.
  outputFileTracingRoot: import.meta.dirname
})
