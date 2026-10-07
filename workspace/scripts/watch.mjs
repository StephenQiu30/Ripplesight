import fs from 'node:fs'
import path from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { pathToFileURL } from 'node:url'
import { createPreview } from './preview.mjs'

const ignored = new Set(['node_modules', '.git', '.tools', '.next', '.preview', 'out', '.venv', '__pycache__', '.obsidian'])
const ignoredFile = name => /^\.env(?:\.|$)/.test(name) || /\.(?:pyc|pem|key|log)$/.test(name) || ['next-env.d.ts', 'tsconfig.tsbuildinfo', '.DS_Store'].includes(name)

// Match the documentation build context rather than copying the whole checkout.
export function captureSources(root, { metadataOnly = false } = {}) {
  const files = []
  function read(relative) {
    const file = path.join(root, relative)
    if (!fs.existsSync(file)) return
    const stat = fs.lstatSync(file)
    if (stat.isSymbolicLink()) throw new Error(`文档构建来源不允许符号链接：${relative}`)
    if (stat.isDirectory()) {
      for (const name of fs.readdirSync(file).sort()) {
        if (!ignored.has(name) && !ignoredFile(name)) read(path.join(relative, name))
      }
    } else if (stat.isFile() && !ignoredFile(path.basename(file))) {
      const data = metadataOnly ? Buffer.from(`${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`) : fs.readFileSync(file)
      files.push({ relative, data })
    }
  }
  for (const name of fs.readdirSync(root).sort()) {
    if (name.endsWith('.md') || /^docker-compose.*\.ya?ml$/.test(name)) read(name)
  }
  for (const directory of ['backend', 'frontend']) {
    if (!fs.existsSync(path.join(root, directory))) continue
    for (const name of fs.readdirSync(path.join(root, directory)).sort()) {
      if (name.endsWith('.md')) read(path.join(directory, name))
    }
  }
  for (const relative of ['backend/app', 'backend/database/schema.sql', 'backend/tests', 'frontend/src', 'workspace']) read(relative)
  return files.sort((a, b) => a.relative.localeCompare(b.relative))
}

export function fingerprint(files) {
  const hash = createHash('sha256')
  for (const { relative, data } of files) hash.update(relative).update('\0').update(data).update('\0')
  return hash.digest('hex')
}

export async function rebuild({ sourceRoot, buildRoot, previewRoot, build }) {
  const sources = captureSources(sourceRoot)
  const revision = fingerprint(sources)
  if (fingerprint(captureSources(sourceRoot)) !== revision) throw new Error('捕获来源期间有新修改，等待下一次完整构建')
  const paths = new Set(sources.map(file => file.relative))
  for (const previous of captureSources(buildRoot)) {
    if (!paths.has(previous.relative)) fs.rmSync(path.join(buildRoot, previous.relative))
  }
  for (const { relative, data } of sources) {
    const target = path.join(buildRoot, relative)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    if (!fs.existsSync(target) || !fs.readFileSync(target).equals(data)) fs.writeFileSync(target, data)
  }
  await build()
  // The copied sources stay unchanged during this build. New edits queue the next build.
  const generated = path.join(buildRoot, 'workspace/out')
  if (!fs.existsSync(path.join(generated, 'index.html')) || !fs.existsSync(path.join(generated, '_pagefind/pagefind.js'))) {
    throw new Error('构建未生成完整页面与搜索索引')
  }
  fs.mkdirSync(previewRoot, { recursive: true })
  const version = `${Date.now()}-${randomUUID()}`
  const snapshot = path.join(previewRoot, version)
  fs.cpSync(generated, snapshot, { recursive: true })
  const temporary = path.join(previewRoot, 'next')
  fs.rmSync(temporary, { force: true })
  fs.symlinkSync(version, temporary)
  fs.renameSync(temporary, path.join(previewRoot, 'current'))
  const generations = fs.readdirSync(previewRoot).filter(name => /^\d+-[a-f\d-]+$/.test(name)).sort()
  for (const old of generations.slice(0, -2)) fs.rmSync(path.join(previewRoot, old), { recursive: true })
  return version
}

async function watch() {
  const sourceRoot = path.resolve(process.env.DOCS_SOURCE_ROOT)
  const buildRoot = path.resolve(process.cwd(), '..')
  if (sourceRoot === buildRoot) throw new Error('文档来源与容器构建目录必须分开')
  const previewRoot = path.join(process.cwd(), '.preview')
  const preview = createPreview({ out: path.join(previewRoot, 'current'), liveReload: true })
  preview.server.listen(Number(process.env.PORT || 8080), process.env.HOST || '0.0.0.0')
  let child, timer, building = false, attempted = '', observed = '', changedAt = 0
  const build = () => new Promise((resolve, reject) => {
    const cwd = path.join(buildRoot, 'workspace')
    const script = JSON.parse(fs.readFileSync(path.join(cwd, 'package.json'), 'utf8')).scripts.build
    // Use the existing build script and locked image dependencies without runtime installation.
    child = spawn('sh', ['-c', script], {
      cwd, stdio: 'inherit', detached: true,
      env: { ...process.env, PATH: path.join(cwd, 'node_modules/.bin') + path.delimiter + process.env.PATH }
    })
    child.on('error', reject)
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`文档构建退出码：${code}`)))
  })
  const update = async signature => {
    building = true
    attempted = signature
    console.log('检测到文档或构建来源修改，开始校验与更新。')
    try {
      const version = await rebuild({ sourceRoot, buildRoot, previewRoot, build })
      preview.refresh(version)
      console.log(`文档热更新完成：${version}；页面、搜索和 AI 原文已整体切换。`)
    } catch (error) { console.error(`文档更新未发布，保留上一版：${error.message}`) }
    finally { building = false; child = undefined }
  }
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
    clearInterval(timer)
    if (child?.pid) { try { process.kill(-child.pid, 'SIGTERM') } catch { /* already exited */ } }
    preview.server.closeAllConnections()
    preview.server.close()
    process.exit(0)
  })
  await update(fingerprint(captureSources(sourceRoot, { metadataOnly: true })))
  timer = setInterval(() => {
    try {
      const signature = fingerprint(captureSources(sourceRoot, { metadataOnly: true }))
      if (signature !== observed) { observed = signature; changedAt = Date.now(); return }
      if (!building && signature !== attempted && Date.now() - changedAt >= 750) void update(signature)
    } catch (error) { console.error(`文档来源读取失败：${error.message}`) }
  }, 1000)
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await watch()
