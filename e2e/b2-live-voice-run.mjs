/**
 * Phase 42 B2 live 驗收腳本（docker backend）— 話術契約抽查。
 *
 * 觀察點（phase-42.md B2 + B1 留給 B2 的觀察）：
 *   1. 點名真人用顯示名：AI 訊息出現「@小美」、全程不得出現「human_creator」（#15）。
 *   2. 離題答完收束（B12）：真人問「現在是哪一關？」→ 組長正常回答＋一句收束回任務（#21）。
 *   3. 語氣契約：AI 訊息無 emoji、無投票話術、無 POV/HMW 等英文縮寫、無官腔樣板（#7/#17/#25）。
 *   4. 1.1a 進場：暖場退場後組長貼「發現階段」macro 標題便條（§3.2，B1 留的缺口）。
 *
 * 用法：node e2e/b2-live-voice-run.mjs
 */

const BACKEND = 'http://localhost:8000'
const EMAIL = `b2_live_${Date.now()}@e2e.test`
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

// --- auth（顯示名＝小美，學生身分入座）---
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
  name: `B2 Live 話術 ${Date.now()}`,
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

const ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
ws.addEventListener('message', (ev) => {
  try {
    const d = JSON.parse(ev.data)
    if (['user_task', 'input_bounced'].includes(d.type)) {
      log(`WS ${d.type}:`, JSON.stringify(d.payload).slice(0, 140))
    }
  } catch { /* ignore */ }
})
await new Promise((res) => { ws.addEventListener('open', res); setTimeout(res, 5000) })
log('WS connected')
function sendChat(content) {
  ws.send(JSON.stringify({ type: 'chat_message', payload: { content, chat_id: 'group' } }))
}

async function messages() {
  const r = await api('GET', `/api/projects/${pid}/messages?limit=200`, undefined, token)
  return r.body?.messages ?? r.body ?? []
}
async function notes() {
  const r = await api('GET', `/api/projects/${pid}/canvas-state`, undefined, token)
  const arr = r.body?.notes
  return Array.isArray(arr) ? arr : []
}

// emoji（含常見符號）偵測
const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}⬀-⯿✀-➿✅❌✓✗⭐⚠]/u
const JARGON_RE = /\b(POV|HMW|Define|Discover|Warmup)\b|solution-language|naysayer/
const OFFICIAL_RE = /(請各位踴躍|階段已完成|請勿|違者)/

const startedAt = Date.now()
let lastMsgCount = 0
let humanActed = false
let askedOffTopic = false
let offTopicAskAt = null
const aiMessages = []
const violations = { seatId: [], emoji: [], jargon: [], vote: [], official: [] }
const summary = {
  humanCuedByName: false, offTopicAnswered: null, discoverLabelNote: null,
  advancedAt: null, advancedSub: null, aiMsgCount: 0,
}

for (let tick = 0; tick < 90; tick++) {
  await new Promise((res) => setTimeout(res, 6000))
  const elapsedS = Math.round((Date.now() - startedAt) / 1000)

  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  const sub = tr.body?.current_sub_phase
  const proj = await api('GET', `/api/projects/${pid}`, undefined, token)
  const stage = proj.body?.current_stage

  const ms = await messages()
  if (ms.length > lastMsgCount) {
    for (const m of ms.slice(lastMsgCount)) {
      const c = (m.content || '').replace(/\n/g, ' ')
      log(`MSG ${m.sender_name || m.sender_id}: ${c.slice(0, 120)}`)
      if (m.sender_type === 'ai') {
        aiMessages.push({ sender: m.sender_name || m.sender_id, content: c, at: elapsedS })
        if (c.includes('human_creator')) violations.seatId.push(c.slice(0, 120))
        if (EMOJI_RE.test(c)) violations.emoji.push(c.slice(0, 120))
        if (JARGON_RE.test(c)) violations.jargon.push(c.slice(0, 120))
        if (c.includes('投票')) violations.vote.push(c.slice(0, 120))
        if (OFFICIAL_RE.test(c)) violations.official.push(c.slice(0, 120))
        if (c.includes(`@${HUMAN_NAME}`)) summary.humanCuedByName = true
        if (askedOffTopic && summary.offTopicAnswered === null
            && /(暖場|破冰|這一關|現在在|回來|接著)/.test(c)
            && (m.sender_name || '').match(/引導|組長|supervisor/i)) {
          summary.offTopicAnswered = c.slice(0, 200)
        }
      }
    }
    lastMsgCount = ms.length
  }

  // 真人最小參與：雙工具
  if (!humanActed && tick >= 4) {
    await api('POST', `/api/projects/${pid}/canvas/notes`, {
      text: '可以拿來當簡易手機支架', color: 'yellow', x: 600, y: 600, sub_phase_id: '0.0a',
    }, token)
    sendChat('我覺得它卡在桌縫剛剛好，拿來架手機看影片很穩')
    log('human dual-tool done')
    humanActed = true
  }

  // 離題提問（B12 行為 (a)：答完收束）
  if (humanActed && !askedOffTopic && tick >= 8) {
    sendChat('等等，我有點搞不清楚——現在是哪一關？這個遊戲到底要幹嘛？')
    askedOffTopic = true
    offTopicAskAt = elapsedS
    log('human asked off-topic/meta question')
  }

  // 暖場退場後找「發現階段」macro 標題便條（1.1a 進場語）
  if (summary.advancedAt && !summary.discoverLabelNote) {
    const ns = await notes()
    const t = ns.find((n) => (n.kind ?? 'content') === 'label' && (n.content || n.text || '').includes('發現階段'))
    if (t) { summary.discoverLabelNote = t.content || t.text; log('OK 發現階段標題便條:', summary.discoverLabelNote) }
  }

  log(`tick ${tick}: stage=${stage} sub=${sub} elapsed=${elapsedS}s aiMsgs=${aiMessages.length}`)

  if (stage && stage !== 'warmup' && !summary.advancedAt) {
    summary.advancedAt = elapsedS
    summary.advancedSub = sub
    log(`暖場退場 @ ${elapsedS}s → stage=${stage} sub=${sub}`)
  }
  // 退場後再觀察 ~2 分鐘（看 1.1a 進場語/標題便條/點名顯示名）
  if (summary.advancedAt && elapsedS > summary.advancedAt + 120) break
  if (elapsedS > 540) { log('9 分鐘觀察上限'); break }
}

summary.aiMsgCount = aiMessages.length

console.log('\n===== B2 LIVE SUMMARY =====')
console.log(JSON.stringify(summary, null, 2))
console.log('--- violations ---')
console.log(JSON.stringify(violations, null, 2))
console.log('off-topic asked at', offTopicAskAt, 's')
console.log('PROJECT_ID=', pid)
const hardFail = violations.seatId.length > 0
console.log(hardFail ? 'RESULT: FAIL（seat id 外漏）' : 'RESULT: 觀察完成（違規清單見上）')
process.exit(hardFail ? 1 : 0)
