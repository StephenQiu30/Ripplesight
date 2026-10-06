import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import { workspaceRoot, basePath } from './content.mjs'

const out = path.join(workspaceRoot, 'out')
const port = Number(process.env.PORT || 8668)
const types = {
  '.html': 'text/html; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json',
  '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2'
}
if (!fs.existsSync(path.join(out, 'index.html'))) throw new Error('请先执行 pnpm build')
http.createServer((request, response) => {
  let pathname
  try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname) }
  catch { response.writeHead(400).end('路径无效'); return }
  if (pathname === basePath) { response.writeHead(308, { Location: basePath + '/' }).end(); return }
  if (!pathname.startsWith(basePath + '/')) { response.writeHead(404).end('页面不存在'); return }
  let file = path.resolve(out, '.' + pathname.slice(basePath.length))
  if (file !== out && !file.startsWith(out + path.sep)) { response.writeHead(403).end('路径无效'); return }
  try {
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html')
    const data = fs.readFileSync(file)
    response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' }).end(data)
  } catch {
    response.writeHead(404, { 'Content-Type': types['.html'] }).end(fs.readFileSync(path.join(out, '404.html')))
  }
}).listen(port, '127.0.0.1', () => console.log(`静态预览：http://127.0.0.1:${port}${basePath}/`))
