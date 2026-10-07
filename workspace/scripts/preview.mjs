import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import { pathToFileURL } from 'node:url'
import { workspaceRoot, basePath } from './content.mjs'

const types = {
  '.html': 'text/html; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json',
  '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2'
}
const reloadScript = `const version = new URL(document.currentScript.src).searchParams.get('version');
const events = new EventSource('${basePath}/__updates');
events.onmessage = event => { if (event.data !== version) location.reload(); };`

export function createPreview({ out, liveReload = false }) {
  const clients = new Set()
  let version = 'initial'
  const server = http.createServer((request, response) => {
    let pathname
    try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname) }
    catch { response.writeHead(400).end('路径无效'); return }
    response.setHeader('Cache-Control', 'no-store')
    if (pathname === '/') { response.writeHead(302, { Location: basePath + '/' }).end(); return }
    if (pathname === basePath) { response.writeHead(308, { Location: basePath + '/' }).end(); return }
    if (!pathname.startsWith(basePath + '/')) { response.writeHead(404).end('页面不存在'); return }
    if (liveReload && pathname === basePath + '/__updates') {
      response.writeHead(200, { 'Content-Type': 'text/event-stream', Connection: 'keep-alive' })
      response.write(`data: ${version}\n\n`)
      clients.add(response)
      request.on('close', () => clients.delete(response))
      return
    }
    if (liveReload && pathname === basePath + '/__reload.js') {
      response.writeHead(200, { 'Content-Type': types['.js'] }).end(reloadScript)
      return
    }
    // Resolve the current snapshot once for each request; a build never modifies it.
    let root
    try { root = fs.realpathSync(out) }
    catch { response.writeHead(503).end('文档正在生成，请稍后重试'); return }
    let file = path.resolve(root, '.' + pathname.slice(basePath.length))
    if (file !== root && !file.startsWith(root + path.sep)) { response.writeHead(403).end('路径无效'); return }
    try {
      if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html')
      const realFile = fs.realpathSync(file)
      if (!realFile.startsWith(root + path.sep)) { response.writeHead(403).end('路径无效'); return }
      let data = fs.readFileSync(realFile)
      if (liveReload && path.extname(file) === '.html') {
        data = data.toString().replace('</body>', `<script defer src="${basePath}/__reload.js?version=${version}"></script></body>`)
      }
      response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' }).end(data)
    } catch {
      try { response.writeHead(404, { 'Content-Type': types['.html'] }).end(fs.readFileSync(path.join(root, '404.html'))) }
      catch { response.writeHead(503).end('文档正在生成，请稍后重试') }
    }
  })
  const heartbeat = liveReload ? setInterval(() => {
    for (const client of clients) client.write(': keep-alive\n\n')
  }, 15000) : undefined
  heartbeat?.unref()
  server.on('close', () => { clearInterval(heartbeat); for (const client of clients) client.end() })
  return {
    server,
    refresh(nextVersion) {
      version = nextVersion
      for (const client of clients) client.write(`data: ${version}\n\n`)
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const out = path.join(workspaceRoot, 'out')
  if (!fs.existsSync(path.join(out, 'index.html'))) throw new Error('请先执行 pnpm build')
  const port = Number(process.env.PORT || 8668)
  const host = process.env.HOST || '127.0.0.1'
  createPreview({ out }).server.listen(port, host, () => console.log(`静态预览：http://${host}:${port}${basePath}/`))
}
