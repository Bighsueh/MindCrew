/**
 * C2 定義階段閘門探針掃描（對既有房 sub_phase_id 直驅；閘以 note.sub_phase_id 判模板，
 * 與房當前 sub 無關）。FAIL 探 reason_zh（不 force、不落地）、PASS 探放行（落地）。
 * 並貼一張帶 cites 的問題定義，作為 forced_closure 的搬入素材。
 *
 * 用法：node e2e/c2-probe-sweep.mjs <label> <painId1> <painId2>
 */
import { readFileSync } from 'node:fs'

const LABEL = process.argv[2] || 'human'
const PAIN1 = process.argv[3]
const PAIN2 = process.argv[4]
const s = JSON.parse(readFileSync(`e2e/c2-${LABEL}-session.json`, 'utf8'))
const pid = s.project_id
const token = s.token

async function post({ text, x, y, sub, kind = 'content', cites, force = false }) {
  const res = await fetch(`http://localhost:8000/api/projects/${pid}/canvas/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ text, color: 'yellow', x, y, sub_phase_id: sub, kind, cites, force_publish: force }),
  })
  const b = await res.json().catch(() => null)
  const ok = b?.success === true
  const reason = b?.rejection?.reason_zh ?? b?.reason_zh ?? b?.detail ?? null
  const nid = b?.note_id ?? b?.id ?? b?.note?.id ?? null
  console.log(JSON.stringify({ sub, text: text.slice(0, 30), ok, reason, nid }))
  return { ok, reason, nid }
}

console.log('=== 2.1 problem_candidate ===')
await post({ text: '忘', x: 600, y: 1300, sub: '2.1' })                       // FAIL 太短
await post({ text: '出門前就忘了帶', x: 700, y: 1350, sub: '2.1' })            // PASS 7字

console.log('=== 2.2 problem_statement ===')
await post({ text: '上班族需要購物袋', x: 600, y: 400, sub: '2.2' })           // FAIL 無因為
const ps = await post({                                                       // PASS 需求句 + cites≥2
  text: '常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，因為 他們不是不想帶，是想到的時候人已經在店裡了',
  x: 900, y: 450, sub: '2.2', cites: [PAIN1, PAIN2].filter(Boolean),
})
console.log('CONTROLLED_PS_ID=' + (ps.nid || ''))

console.log('=== 2.5 criteria ===')
await post({ text: '準則：時間可行性', x: 2250, y: 400, sub: '2.5' })          // FAIL 缺衡量方式
await post({ text: '準則：影響範圍｜衡量方式：卡住的人多不多', x: 2250, y: 600, sub: '2.5' }) // PASS

console.log('=== 2.7 hmw / 設計題目 ===')
await post({ text: '怎麼讓袋子出現在手邊？', x: 600, y: 300, sub: '2.7' })      // FAIL 句型
await post({ text: '我們可以怎麼用 HMW 改寫成需求？', x: 700, y: 350, sub: '2.7' }) // FAIL 禁字
// PASS hmw 留待 force_close 後配 chosenPS（見後續 docker exec）
console.log('DONE')
