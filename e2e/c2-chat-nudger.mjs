/**
 * C2 單真人房聊天推手：偵測 sub_phase 進入「需要真人發言才順暢推進」的關，
 * 各關發一句合情境的真人聊天（每關一次），避免組長空等真人卡關。
 * 便條探針仍由 c2-live-run.mjs 負責；本腳本只補聊天參與（訊號層真人 gate）。
 *
 * 用法：node e2e/c2-chat-nudger.mjs <label>   （label 對應 c2-<label>-session.json）
 */
import { readFileSync } from 'node:fs'

const LABEL = process.argv[2] || 'human'
const s = JSON.parse(readFileSync(`e2e/c2-${LABEL}-session.json`, 'utf8'))
const pid = s.project_id
const token = s.token

function ts() { return new Date().toISOString().slice(11, 19) }
function log(...a) { console.log(`[${ts()}][nudge]`, ...a) }

// 每關一句真人發言（訊號層參與）。便條探針由主驅動負責，這裡只發聊天。
const LINES = {
  '0.0a': '磚頭我覺得可以拿來壓泡菜、當門擋、還能墊高螢幕',
  '1.1a': '我自己也常常買完東西才發現沒帶袋子，只好再買一個',
  '1.1c': '我覺得「通勤上班族」跟「帶小孩的家長」可以歸成同一類，都是趕時間沒空準備',
  '1.1d': '我覺得通勤上班族這群最該先看，因為人最多、最常發生',
  '2.1': '可以分成「出門前就忘了帶」跟「帶了但嫌麻煩」兩個主題',
  '2.3': '我覺得根源是大家把環保跟方便當成二選一，環保就得多花力氣',
  '2.4': '現有的折疊袋跟集點折扣，借還那關還是很麻煩，沒解決到根本',
  '2.5': '我提一條準則：幫到的人多不多，越多人卡住的越優先',
  '2.6': '我選通勤上班族那句，因為最多人卡在這、解決它影響最大',
  '2.7': '我確認這句設計題目：我們可以怎麼讓上班族出門時自動記得帶袋子',
}

let ws
function openWS() {
  ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
  ws.addEventListener('close', () => setTimeout(openWS, 1000))
}
openWS()
await new Promise((r) => setTimeout(r, 2000))
log('WS open for', pid)

async function timerSub() {
  const res = await fetch(`http://localhost:8000/api/projects/${pid}/timer`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const b = await res.json().catch(() => null)
  return b?.current_sub_phase
}

const sent = new Set()
const startMs = Date.now()
while ((Date.now() - startMs) / 60000 < 35) {
  const sub = await timerSub()
  if (sub && LINES[sub] && !sent.has(sub)) {
    sent.add(sub)
    // 進關後稍等讓組長先開場，再發言
    await new Promise((r) => setTimeout(r, 9000))
    try {
      ws.send(JSON.stringify({ type: 'chat_message', payload: { content: LINES[sub] } }))
      log(`sub=${sub} -> chat: ${LINES[sub]}`)
    } catch (e) { log('send failed', String(e).slice(0, 80)) }
  }
  if (sub === 'completed') { log('completed; nudger stop'); break }
  await new Promise((r) => setTimeout(r, 10000))
}
log('nudger done')
