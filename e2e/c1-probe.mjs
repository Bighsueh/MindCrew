/**
 * C1 live 互動探針：以真人（小美）身分貼一張便條，印出後端閘門回應。
 * 用法：node e2e/c1-probe.mjs "<text>" <sub_phase_id> <x> <y> [kind] [color] [force]
 * 例：node e2e/c1-probe.mjs "陳建宏｜超長違規理由……" 1.1c 900 450        （測 template 擋）
 *     node e2e/c1-probe.mjs "做一個 App 提醒大家帶環保袋" 1.2 900 1400      （測 no_feature_jump 軟擋）
 *     node e2e/c1-probe.mjs "他到門口才想起沒帶只好買塑膠袋" 1.2 900 1400   （真人痛點）
 */
import { readFileSync } from 'node:fs'

const s = JSON.parse(readFileSync('e2e/c1-live-session.json', 'utf8'))
const [, , text, sub, x, y, kind = 'content', color = 'yellow', force = 'false'] = process.argv
if (!text || !sub) { console.error('need: text sub_phase_id x y'); process.exit(1) }

const res = await fetch(`http://localhost:8000/api/projects/${s.project_id}/canvas/notes`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${s.token}` },
  body: JSON.stringify({
    text, color, x: Number(x) || 900, y: Number(y) || 450,
    sub_phase_id: sub, kind, force_publish: force === 'true',
  }),
})
const body = await res.json().catch(() => null)
console.log('status', res.status)
console.log(JSON.stringify(body, null, 2))
