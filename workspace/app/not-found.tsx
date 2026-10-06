import Link from 'next/link'

export default function NotFound() {
  return (
    <main style={{ maxWidth: '48rem', margin: '4rem auto', padding: '1rem' }}>
      <h1>404：页面不存在</h1>
      <p>请检查链接，或回到文档首页查找。</p>
      <Link href="/">返回文档首页</Link>
    </main>
  )
}
