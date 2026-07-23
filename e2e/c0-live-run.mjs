/**
 * Phase 42 C0 live 驗收腳本（docker backend）— 開房階段。
 *
 * 開一間 40min 單真人房（顯示名＝小美）、入座、等暖場 crew 至少貼 2 張 AI 便條，
 * 然後輸出 PROJECT_ID / TOKEN 到 e2e/c0-live-session.json 供後續 UI 步驟
 * （Playwright：拖曳 / 手貼 / RejectToast / 引用）使用。房間留著繼續跑。
 *
 * 用法：node e2e/c0-live-run.mjs
 */

import { writeFileSync } from 'node:fs'

const BACKEND = 'http://localhost:8000'
const EMAIL = `c0_live_${Date.now()}@e2e.test`
const PASSWORD = 'Passw0rd!e2e'
const HUMAN_NAME = '小美'

async function api(method, path, body, token) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BACKEND}${path}`, {
    method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let parsed = null
  try { parsed = text ? JSON.parse(text) : null } catch { parsed = text }
  return { status: res.status, body: parsed }
}

const PERSONA = (idx) => ({
  seat_role: `crew_${idx}`,
  persona: {
    name: `live隊友${idx}`,
    role: `測試角色 ${idx}`,
    expertise: '測試專長',
    personality_axis: ['supportive', 'balanced', 'contrarian'][idx - 1] ?? 'balanced',
    personality_desc: '務實穩健、邏輯清晰、執行力強',
    backstory: '測試用人設',
    lens_affinities: { empathy: 0.5, structure: 0.5, creativity: 0.5, feasibility: 0.5 },
  },
})

function ts() { return new Date().toISOString().slice(11, 19) }
function log(...a) { console.log(`[${ts()}]`, ...a) }

await api('POST', '/api/auth/register', {
  email: EMAIL, password: PASSWORD, display_name: HUMAN_NAME, role: 'teacher',
})
let token = null
for (let i = 0; i < 10 && !token; i++) {
  const l = await api('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD })
  if (l.status === 200) token = l.body.access_token
  else await new Promise((res) => setTimeout(res, 300))
}
if (!token) throw new Error('login failed')
log('token OK, display_name =', HUMAN_NAME)

const timerConfig = {
  total_session_minutes: 40,
  intensity: 0.4,
  macro_budgets: { warmup: 5, discover: 21, define: 14 },
  preset_id: 'timer_preset_40min',
}
const create = await api('POST', '/api/projects', {
  name: `C0 Live 白板 ${Date.now()}`,
  description: '怎麼讓大家更願意把環保袋帶出門、真的用起來',
  ai_crew_count: 3,
  personas: [PERSONA(1), PERSONA(2), PERSONA(3)],
  timer_config: timerConfig,
}, token)
if (create.status !== 200 && create.status !== 201) {
  throw new Error(`create failed ${create.status} ${JSON.stringify(create.body)}`)
}
const pid = create.body.id
log('PROJECT_ID =', pid)

await api('POST', `/api/projects/${pid}/timer/init`, { config: timerConfig }, token)
await api('POST', `/api/projects/${pid}/join`, { seat_role: 'human_creator' }, token)
log('joined human_creator')

writeFileSync('e2e/c0-live-session.json', JSON.stringify({
  project_id: pid, token, email: EMAIL, password: PASSWORD, human_name: HUMAN_NAME,
}, null, 2))
log('session written to e2e/c0-live-session.json')

// Human Presence Gate：agent 迴圈要有人連著專案 WS 才會動——開著不關。
const ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
await new Promise((res) => { ws.addEventListener('open', res); setTimeout(res, 5000) })
log('WS connected（presence 保持）')

// 等暖場 crew 至少貼 2 張 AI 便條（②⑤ 的素材），上限 ~5 分鐘
let ready = false
for (let tick = 0; tick < 50 && !ready; tick++) {
  await new Promise((res) => setTimeout(res, 6000))
  const r = await api('GET', `/api/projects/${pid}/canvas-state`, undefined, token)
  const notes = Array.isArray(r.body?.notes) ? r.body.notes : []
  const aiContent = notes.filter(
    (n) => n.kind !== 'label' && /\(ai\)$/.test(n.author || ''),
  )
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  log(`tick=${tick} sub=${tr.body?.current_sub_phase} notes=${notes.length} aiContent=${aiContent.length}`)
  if (aiContent.length >= 2) {
    log('OK: AI 內容便條 ≥2，開房階段完成；保持 WS presence（kill 本程序結束）。')
    for (const n of notes) {
      log(`  note ${n.id} [${n.kind}] (${n.author}) ${String(n.content).slice(0, 30)} cites=${JSON.stringify(n.cites)}`)
    }
    ready = true
  }
}
if (!ready) throw new Error('timeout：5 分鐘內 AI 便條不足 2 張')

// 保持 presence：每 60s 報一次狀態，直到被 kill。
setInterval(async () => {
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  log(`presence alive sub=${tr.body?.current_sub_phase}`)
}, 60000)
