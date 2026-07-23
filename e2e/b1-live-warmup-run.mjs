/**
 * Phase 42 B1 live 驗收腳本（docker 全棧）— 跑一輪暖場並蒐證。
 *
 * 觀察點（phase-42.md B1）：
 *   1. timer：40min preset → 0.0a budget=300s（固定硬 5 分；送舊值 warmup=2 應被覆寫）、warmup_goal=8。
 *   2. 組長進場：貼標題便條（label）＋示範便條（content、僅 1 張）＋宣告含目標。
 *   3. 點名真人雙工具（user_task / @顯示名 訊息）。
 *   4. 達標慶祝或 3 分未達宣布延長；收尾橋接非樣板 → 進 1.1a。
 *   5. 不再 2 分鐘 time-box 提前退場。
 *
 * 用法：node e2e/b1-live-warmup-run.mjs
 */

const BACKEND = 'http://localhost:8000'
const EMAIL = `b1_live_${Date.now()}@e2e.test`
const PASSWORD = 'Passw0rd!e2e'

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

// --- auth ---
let r = await api('POST', '/api/auth/register', {
  email: EMAIL, password: PASSWORD, display_name: 'B1 Live 老師', role: 'teacher',
})
let token = null
for (let i = 0; i < 10 && !token; i++) {
  const l = await api('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD })
  if (l.status === 200) token = l.body.access_token
  else await new Promise((res) => setTimeout(res, 300))
}
if (!token) throw new Error('login failed')
log('teacher token OK')

// --- create project: 40min preset，刻意送舊值 warmup=2 ---
const timerConfig = {
  total_session_minutes: 40,
  intensity: 0.4,
  macro_budgets: { warmup: 2, discover: 23, define: 15 },
  preset_id: 'timer_preset_40min',
}
const create = await api('POST', '/api/projects', {
  name: `B1 Live 暖場 ${Date.now()}`,
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

// --- timer init ---
const init = await api('POST', `/api/projects/${pid}/timer/init`, { config: timerConfig }, token)
log('timer/init', init.status)

const t0 = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
log('CHECK1 timer:',
  'sub=', t0.body?.current_sub_phase,
  'budget=', t0.body?.sub_phase_budget_seconds,
  'warmup_goal=', t0.body?.warmup_goal,
  'cfg.warmup=', t0.body?.config?.macro_budgets?.warmup,
  'cfg.0.0a=', t0.body?.config?.sub_phase_overrides?.['0.0a'])

// --- 真人入座（human_creator）→ 喚醒 AI ---
const seats = await api('GET', `/api/projects/${pid}/seats`, undefined, token)
const humanSeat = (seats.body || []).find((s) => s.seat_role === 'human_creator')
log('seats:', (seats.body || []).map((s) => s.seat_role).join(','), '→ join', humanSeat?.seat_role)
const join = await api('POST', `/api/projects/${pid}/join`, { seat_role: 'human_creator' }, token)
log('join human_creator:', join.status)

// --- 真人聊天走 WS（round_lock 實質檢核路徑在 chat_ws）---
const ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
const wsEvents = []
ws.addEventListener('message', (ev) => {
  try {
    const d = JSON.parse(ev.data)
    if (['user_task', 'waiting_for_human', 'input_bounced', 'timer_state'].includes(d.type)) {
      if (d.type !== 'timer_state') { wsEvents.push(d); log(`📡 WS ${d.type}:`, JSON.stringify(d.payload).slice(0, 140)) }
    }
  } catch { /* ignore */ }
})
await new Promise((res) => { ws.addEventListener('open', res); setTimeout(res, 5000) })
log('WS connected')
function sendChat(content) {
  ws.send(JSON.stringify({ type: 'chat_message', payload: { content, chat_id: 'group' } }))
}

// --- 觀察循環 ---
const startedAt = Date.now()
let lastMsgCount = 0
let humanActed = false
let summary = {
  titleLabelNote: null, demoNote: null, goalAnnounced: false,
  userCued: false, scenarioMsg: null, bridgeMsg: null,
  advancedAt: null, advancedSub: null, supContentNotes: 0,
}

async function notes() {
  const r = await api('GET', `/api/projects/${pid}/canvas-state`, undefined, token)
  const arr = r.body?.notes
  return Array.isArray(arr) ? arr : []
}
async function messages() {
  const r = await api('GET', `/api/projects/${pid}/messages?limit=100`, undefined, token)
  return r.body?.messages ?? r.body ?? []
}

for (let tick = 0; tick < 80; tick++) {
  await new Promise((res) => setTimeout(res, 6000))
  const elapsedS = Math.round((Date.now() - startedAt) / 1000)

  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  const sub = tr.body?.current_sub_phase
  const proj = await api('GET', `/api/projects/${pid}`, undefined, token)
  const stage = proj.body?.current_stage

  const ns = await notes()
  const labelNotes = ns.filter((n) => (n.kind ?? 'content') === 'label')
  const contentNotes = ns.filter((n) => (n.kind ?? 'content') === 'content')
  if (!summary.titleLabelNote) {
    const t = labelNotes.find((n) => (n.content || n.text || '').includes('破冰'))
    if (t) { summary.titleLabelNote = t.content || t.text; log('✅ 標題便條:', summary.titleLabelNote) }
  }

  const ms = await messages()
  if (ms.length > lastMsgCount) {
    for (const m of ms.slice(lastMsgCount)) {
      const c = (m.content || '').replace(/\n/g, ' ')
      log(`💬 ${m.sender_name || m.sender_id}: ${c.slice(0, 110)}`)
      if (!summary.goalAnnounced && /湊|目標|張/.test(c) && (m.sender_type === 'ai')) summary.goalAnnounced = true
      if (!summary.userCued && c.includes('@') && /便條/.test(c)) summary.userCued = true
      if (!summary.scenarioMsg && /(延長|到了|湊滿|湊到)/.test(c) && m.sender_type === 'ai') summary.scenarioMsg = c.slice(0, 160)
      if (/(經驗|真實|接下來|題目)/.test(c) && m.sender_type === 'ai' && summary.advancedAt) {
        if (!summary.bridgeMsg) summary.bridgeMsg = c.slice(0, 200)
      }
    }
    lastMsgCount = ms.length
  }

  log(`tick ${tick}: stage=${stage} sub=${sub} notes=${contentNotes.length}c/${labelNotes.length}l elapsed=${elapsedS}s`)

  // 真人最小參與：在組長點名後（~第 5 tick）做雙工具——貼一張便條＋說一句話
  if (!humanActed && tick >= 4) {
    const noteRes = await api('POST', `/api/projects/${pid}/canvas/notes`, {
      text: '可以拿來當簡易手機支架',
      color: 'yellow', x: 600, y: 600, sub_phase_id: '0.0a',
    }, token)
    sendChat('我覺得它卡在桌縫剛剛好，拿來架手機看影片很穩')
    log('🙋 human dual-tool: note=', noteRes.status, 'chat=WS sent')
    humanActed = true
  }

  if (stage && stage !== 'warmup' && !summary.advancedAt) {
    summary.advancedAt = elapsedS
    summary.advancedSub = sub
    log(`🎯 暖場退場 @ ${elapsedS}s → stage=${stage} sub=${sub}`)
  }
  if (summary.advancedAt && elapsedS > summary.advancedAt + 30) break
  if (elapsedS > 480) { log('⏰ 8 分鐘觀察上限'); break }
}

// 結算：組長 content 便條數（限示範檢查）
const finalNotes = await notes()
const supNotes = finalNotes.filter((n) => (n.kind ?? 'content') === 'content' && /supervisor|組長/.test(n.author_id || '') )
summary.supContentNotes = supNotes.length

console.log('\n===== B1 LIVE SUMMARY =====')
console.log(JSON.stringify(summary, null, 2))
console.log('PROJECT_ID=', pid)
