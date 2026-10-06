import { execute } from './local-store.mjs'
let input = ''
for await (const chunk of process.stdin) { input += chunk; if (input.length > 250000) process.exit(1) }
try {
  const { source, store, ...command } = JSON.parse(input)
  process.stdout.write(JSON.stringify({ result: execute(source, store, command) }))
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.code || 'workspace_unavailable' }))
}
