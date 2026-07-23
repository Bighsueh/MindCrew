/**
 * C1 live：以真人（小美）身分送一則群組聊天，滿足 chat 型逐關真人 gate。
 * 用法：node e2e/c1-chat.mjs "<content>"
 */
import { readFileSync } from 'node:fs'

const s = JSON.parse(readFileSync('e2e/c1-live-session.json', 'utf8'))
const content = process.argv[2]
if (!content) { console.error('need content'); process.exit(1) }

const ws = new WebSocket(`ws://localhost:8000/ws/project/${s.project_id}?token=${s.token}`)
await new Promise((res, rej) => {
  ws.addEventListener('open', res)
  ws.addEventListener('error', rej)
  setTimeout(res, 4000)
})
ws.send(JSON.stringify({ type: 'chat_message', payload: { content } }))
console.log('sent chat:', content)
await new Promise((res) => setTimeout(res, 2500))
ws.close()
console.log('closed')
