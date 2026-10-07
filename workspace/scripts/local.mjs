import fs from 'node:fs'
import path from 'node:path'
import net from 'node:net'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { initialize, writeAtomic, execute } from './local-store.mjs'
import { documents, regeneratedIndex } from './content.mjs'

const tool = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repository = path.dirname(tool)
const requestedDirectory = process.argv.includes('--directory') ? process.argv[process.argv.indexOf('--directory') + 1] : undefined
if (requestedDirectory && !path.isAbsolute(requestedDirectory)) throw new Error('--directory 必须为绝对路径。')
const base = requestedDirectory ?? path.join(repository, '.tools/workspace')
const configuration = path.join(base, 'config.json')
const [action, ...args] = process.argv.slice(2).filter(value => value !== '--')
const git = (directory, ...values) => {
  const result = spawnSync('git', ['-C', directory, ...values], { encoding: 'utf8', timeout: 30000 })
  if (result.status !== 0) throw new Error('本地 Git 工作副本操作失败。')
}
async function portAvailable(port) {
  return new Promise(resolve => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)))
  })
}
try {
  if (action === 'init') {
    const user = args[args.indexOf('--user') + 1]
    if (!args.includes('--user') || !/^[a-f\d]{8}-[a-f\d]{4}-[1-8][a-f\d]{3}-[89ab][a-f\d]{3}-[a-f\d]{12}$/i.test(user ?? '')) throw new Error('请使用 local:init --user <现有登录账号 UUID>。')
    if (fs.existsSync(base)) throw new Error('本机知识库目录已存在；保留已有来源与草稿，不重复初始化。')
    const source = path.join(base, 'source'), store = path.join(base, 'store')
    fs.mkdirSync(base, { recursive: true, mode: 0o700 })
    const cloned = spawnSync('git', ['clone', '--no-hardlinks', '--', repository, source], { encoding: 'utf8', timeout: 30000 })
    if (cloned.status !== 0) throw new Error('无法初始化独立 Git 工作副本。')
    git(source, 'remote', 'remove', 'origin')
    // Seed documentation only, including current uncommitted authored documents.
    // Application code, environment files and runtime state are not overlaid.
    fs.cpSync(path.join(tool, 'content'), path.join(source, 'workspace/content'), { recursive: true, filter: file => !path.basename(file).startsWith('.') })
    for (const file of ['AGENTS.md', 'PROJECT.md', 'BACKLOG.md', 'workspace/public-documents.json', 'workspace/internal-documents.json', 'workspace/LOCAL.md']) {
      fs.copyFileSync(path.join(repository, file), path.join(source, file))
    }
    const index = path.join(source, 'workspace/content/index.md')
    fs.writeFileSync(index, regeneratedIndex(fs.readFileSync(index, 'utf8'), documents(path.join(source, 'workspace/content'))))
    git(source, 'add', '--', 'workspace/content', 'workspace/public-documents.json', 'workspace/internal-documents.json', 'workspace/LOCAL.md', 'AGENTS.md', 'PROJECT.md', 'BACKLOG.md')
    git(source, '-c', 'user.name=Workspace', '-c', 'user.email=workspace@localhost', 'commit', '--allow-empty', '-m', 'docs(workspace):初始化本机文档来源')
    const result = initialize(source, store)
    writeAtomic(configuration, JSON.stringify({
      HOTKEY_WORKSPACE_DOCUMENT_TOOL_ROOT: tool,
      HOTKEY_WORKSPACE_DOCUMENT_SOURCE_ROOT: source,
      HOTKEY_WORKSPACE_DOCUMENT_SNAPSHOT_ROOT: store,
      HOTKEY_WORKSPACE_DOCUMENT_READ_USER_IDS: JSON.stringify([user]),
      HOTKEY_WORKSPACE_DOCUMENT_WRITE_USER_IDS: JSON.stringify([user]),
      HOTKEY_WORKSPACE_DOCUMENT_PUBLISH_USER_IDS: JSON.stringify([user]),
    }, null, 2))
    console.log(`本机知识库已初始化：${result.documents} 篇文档。\nObsidian 来源：${path.join(source, 'workspace/content')}\n使用 pnpm local:start 启动。`)
  } else if (action === 'read') {
    const config = JSON.parse(fs.readFileSync(configuration, 'utf8'))
    const mode = args[0]
    if (!['list', 'search', 'read', 'raw'].includes(mode)) throw new Error('只读工具支持 list/search/read/raw。')
    const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined
    const result = execute(config.HOTKEY_WORKSPACE_DOCUMENT_SOURCE_ROOT, config.HOTKEY_WORKSPACE_DOCUMENT_SNAPSHOT_ROOT, {
      action: mode, path: option('--path'), query: option('--query'), snapshot_id: option('--snapshot'), anchor: option('--anchor'), owner_id: 'local-filesystem-reader', history: args.includes('--history'),
    })
    console.log(JSON.stringify(result, null, 2))
  } else if (action === 'start') {
    if (!fs.existsSync(configuration)) throw new Error('先执行 pnpm local:init -- --user <UUID>。')
    if (!(await portAvailable(8666)) || !(await portAvailable(8667))) throw new Error('8666 或 8667 已被占用。请先正常停止现有 Web/API，再用 local:start 启动；不会自动终止其他进程。')
    const env = { ...process.env, ...JSON.parse(fs.readFileSync(configuration, 'utf8')) }
    const api = spawn('uv', ['run', '--locked', 'uvicorn', 'main:create_app', '--factory', '--app-dir', 'app', '--host', '127.0.0.1', '--port', '8667', '--no-proxy-headers', '--no-access-log'], { cwd: path.join(repository, 'backend'), env, stdio: 'inherit', detached: true })
    const web = spawn('pnpm', ['dev'], { cwd: path.join(repository, 'frontend'), env, stdio: 'inherit', detached: true })
    const stop = () => { for (const child of [api, web]) { if (child.pid) { try { process.kill(-child.pid, 'SIGTERM') } catch { /* Already stopped. */ } } } }
    process.once('SIGINT', stop); process.once('SIGTERM', stop)
    for (const child of [api, web]) {
      child.once('error', () => { console.error('本机启动失败，请核对 uv、pnpm 和已安装依赖。'); stop(); process.exitCode = 1 })
      child.once('exit', code => { stop(); if (code) process.exitCode = code })
    }
    console.log('项目知识库：http://127.0.0.1:8666/workspace/docs（沿用 Ripplesight 登录）')
  } else throw new Error('支持 init --user <UUID> 和 start。')
} catch (error) {
  console.error(error.message)
  process.exitCode = 1
}
