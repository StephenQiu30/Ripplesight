import fs from 'node:fs'
import path from 'node:path'
import { contentRoot, documents, regeneratedIndex } from './content.mjs'

try {
  const file = path.join(contentRoot, 'index.md')
  const raw = fs.readFileSync(file, 'utf8')
  const next = regeneratedIndex(raw, documents())
  if (raw !== next) fs.writeFileSync(file, next)
  console.log(raw === next ? '索引已是最新，无改动。' : '已更新首页索引块。')
} catch (error) {
  console.error(`索引生成失败：${error.message}`)
  process.exitCode = 1
}
