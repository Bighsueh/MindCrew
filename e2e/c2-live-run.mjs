/**
 * Phase 42 C2 live 驗收驅動腳本（docker 全棧）。
 *
 * 跑一間房 0.0a→2.7→completed，對照 phase2-summary A 表逐關打勾。
 * 兩種模式：
 *   ai    ＝全 AI 房：真人只連 WS（Human Presence Gate），全程不貼便條／不發言；
 *           驗兜底路徑（time-box＋forced_closure＋誠實結業）全走通、無死鎖。
 *   human ＝單真人房：逐關真人 gate 訊號層＋定義階段每關探針（FAIL 探 reason_zh、
 *           PASS 探放行），2.6 走 forced_closure、2.7 配對＋設計題目外框素材。
 *
 * 預算壓縮（暖場固定 5 分由後端強制；其餘以 sub_phase_overrides 壓到 1–2 分），
 * 讓 0.0a→completed 約 20 分跑完，定義階段給足探針時間。
 *
 * 用法：node e2e/c2-live-run.mjs <ai|human> <label>
 * 例：  node e2e/c2-live-run.mjs human B
 */
import { writeFileSync, appendFileSync } from 'node:fs'

const MODE = process.argv[2] === 'ai' ? 'ai' : 'human'
const LABEL = process.argv[3] || MODE
const BACKEND = 'http://localhost:8000'
const SIDECAR = 'http://localhost:4000'
const EMAIL = `c2_${LABEL}_${Date.now()}@e2e.test`
const PASSWORD = 'Passw0rd!e2e'
const HUMAN_NAME = MODE === 'ai' ? '旁觀者' : '小明'
const SESSION_FILE = `e2e/c2-${LABEL}-session.json`
const LOGFILE = `e2e/c2-${LABEL}-log.jsonl`

// 定義階段壓縮預算（分鐘）；0.0a 由後端強制 5 分。
const SUB_OVERRIDES = {
  '1.1a': 1, '1.1b': 1, '1.1c': 1, '1.1d': 1, '1.2': 1,
  '2.1': 1, '2.2': 2, '2.3': 1, '2.4': 1, '2.5': 2, '2.6': 2, '2.7': 2,
}

function ts() { return new Date().toISOString().slice(11, 19) }
function log(...a) { console.log(`[${ts()}][${LABEL}]`, ...a) }
function jlog(obj) { try { appendFileSync(LOGFILE, JSON.stringify({ t: new Date().toISOString(), ...obj }) + '\n') } catch {} }

async function api(method, path, body, token, base = BACKEND) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${base}${path}`, {
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
    name: `隊友${idx}`, role: `測試角色 ${idx}`, expertise: '測試專長',
    personality_axis: ['supportive', 'balanced', 'contrarian'][idx - 1] ?? 'balanced',
    personality_desc: '務實穩健、邏輯清晰', backstory: '測試用人設',
    lens_affinities: { empathy: 0.5, structure: 0.5, creativity: 0.5, feasibility: 0.5 },
  },
})

// ---- bootstrap ----
await api('POST', '/api/auth/register', { email: EMAIL, password: PASSWORD, display_name: HUMAN_NAME, role: 'teacher' })
let token = null
for (let i = 0; i < 10 && !token; i++) {
  const l = await api('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD })
  if (l.status === 200) token = l.body.access_token
  else await new Promise((r) => setTimeout(r, 300))
}
if (!token) throw new Error('login failed')
log('token OK; mode =', MODE)

const timerConfig = {
  total_session_minutes: 40, intensity: 0.4,
  macro_budgets: { warmup: 5, discover: 6, define: 12 },
  sub_phase_overrides: SUB_OVERRIDES,
  preset_id: 'timer_preset_40min',
}
const create = await api('POST', '/api/projects', {
  name: `C2 Live ${MODE} ${Date.now()}`,
  description: '怎麼讓大家更願意把環保袋帶出門、真的用起來',
  ai_crew_count: 3, personas: [PERSONA(1), PERSONA(2), PERSONA(3)],
  timer_config: timerConfig,
}, token)
if (![200, 201].includes(create.status)) throw new Error(`create failed ${create.status} ${JSON.stringify(create.body)}`)
const pid = create.body.id
log('PROJECT_ID =', pid)
jlog({ ev: 'created', pid, mode: MODE })

await api('POST', `/api/projects/${pid}/timer/init`, { config: timerConfig }, token)
await api('POST', `/api/projects/${pid}/join`, { seat_role: 'human_creator' }, token)
log('joined human_creator')
writeFileSync(SESSION_FILE, JSON.stringify({ project_id: pid, token, email: EMAIL, mode: MODE, human_name: HUMAN_NAME }, null, 2))

// ---- WS presence ----
let ws
function openWS() {
  ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
  ws.addEventListener('close', () => setTimeout(openWS, 1000))
  ws.addEventListener('message', (e) => {
    try {
      const m = JSON.parse(e.data)
      if (!m || !m.type) return
      if (['presence', 'pong', 'cursor', 'agent_typing'].includes(m.type)) return
      jlog({ ev: 'ws', type: m.type, data: m })
      if (['waiting_for_human', 'stage_changed', 'artifact_gate_rejected', 'note_rejected',
           'first_diamond_completed', 'turn_state'].includes(m.type)) {
        log(`[WS] ${m.type}: ${JSON.stringify(m).slice(0, 180)}`)
      }
      if (m.type === 'chat_message') {
        const c = m.content ?? m.data?.content ?? m.payload?.content ?? ''
        const sender = m.sender_id ?? m.data?.sender_id ?? ''
        if (String(sender).includes('supervisor')) log(`[CHAT sup] ${String(c).slice(0, 160)}`)
      }
    } catch {}
  })
}
openWS()
await new Promise((r) => setTimeout(r, 2500))
log('WS connected (presence held)')

// chat helper（透過 WS 發群聊）
function sendChat(content) {
  try { ws.send(JSON.stringify({ type: 'chat_message', payload: { content } })) } catch {}
  jlog({ ev: 'human_chat', content })
  log(`[human chat] ${content}`)
}

// note helper（人類貼便條 → 印出閘門回應）
async function postNote({ text, x, y, sub, kind = 'content', cites, group_id, force = false }) {
  const r = await api('POST', `/api/projects/${pid}/canvas/notes`, {
    text, color: 'yellow', x, y, sub_phase_id: sub, kind,
    force_publish: force, cites, group_id,
  }, token)
  const ok = r.body?.success === true
  const reason = r.body?.rejection?.reason_zh ?? r.body?.reason_zh ?? r.body?.detail ?? null
  const nid = r.body?.note_id ?? r.body?.id ?? r.body?.note?.id ?? null
  jlog({ ev: 'probe', sub, text, ok, reason, nid, status: r.status, resp: r.body })
  log(`[probe ${sub}] "${String(text).slice(0, 24)}" -> ok=${ok}${reason ? ` reason="${reason}"` : ''}${nid ? ` id=${nid}` : ''}`)
  return { ok, reason, nid, body: r.body }
}

// ---- sidecar full-state inventory ----
async function fullState() {
  const f = await api('GET', `/api/projects/${pid}/canvas-state/full`, undefined, token, SIDECAR)
  return Array.isArray(f.body) ? f.body : []
}
function findForcedNotes(shapes) {
  return shapes.filter((s) => s.time_box_forced === true || /時間到了，先選這張往下走/.test(s.text || s.content || ''))
}
function findHmwNotes(shapes) {
  return shapes.filter((s) => /我們可以怎麼.+[?？]/.test(s.text || s.content || ''))
}

// ---- 定義階段探針排程（human 模式；每關一次）----
const done = new Set()
const state = { painIds: [], psId: null, chosenPsId: null }

async function runProbes(sub, shapes) {
  if (MODE !== 'human') return
  if (done.has(sub)) return

  if (sub === '0.0a' && !done.has('0.0a')) {
    done.add('0.0a')
    sendChat('磚頭我覺得可以拿來壓泡菜、當門擋、還能墊高螢幕')
  }
  if (sub === '1.1b') {
    done.add('1.1b')
    await postNote({ text: '陳建宏', x: 1000, y: 400, sub: '1.1b' }) // stakeholder 只寫名字 PASS
    sendChat('我想到一個對象：常騎機車買晚餐的上班族')
  }
  if (sub === '1.2') {
    done.add('1.2')
    // 痛點牆 template=problem_candidate（2–15字），痛點短句 ≤15 字
    const p1 = await postNote({ text: '出門前忘了帶袋子', x: 600, y: 1200, sub: '1.2' })
    const p2 = await postNote({ text: '袋子佔空間懶得帶', x: 1000, y: 1200, sub: '1.2' })
    if (p1.nid) state.painIds.push(p1.nid)
    if (p2.nid) state.painIds.push(p2.nid)
    jlog({ ev: 'painIds', ids: state.painIds })
  }
  if (sub === '2.1') {
    done.add('2.1')
    await postNote({ text: '忘', x: 600, y: 1300, sub: '2.1' }) // FAIL：太短，探主題群標籤 reason
  }
  if (sub === '2.2') {
    done.add('2.2')
    await postNote({ text: '上班族需要購物袋', x: 600, y: 400, sub: '2.2' }) // FAIL：無「因為」
    // PASS：需求句 + cites≥2 真實痛點
    if (state.painIds.length >= 2) {
      const ps = await postNote({
        text: '常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，因為 他們不是不想帶，是想到的時候人已經在店裡了',
        x: 900, y: 500, sub: '2.2', cites: state.painIds.slice(0, 2),
      })
      if (ps.nid) state.psId = ps.nid
      jlog({ ev: 'psId', id: state.psId, cites: state.painIds.slice(0, 2) })
    } else {
      log('[2.2] 痛點 id 不足，略過 PASS PS')
    }
  }
  if (sub === '2.5') {
    done.add('2.5')
    await postNote({ text: '準則：時間可行性', x: 2250, y: 400, sub: '2.5' }) // FAIL：缺衡量方式
    await postNote({ text: '準則：影響範圍｜衡量方式：卡住的人多不多', x: 2250, y: 600, sub: '2.5' }) // PASS
  }
  if (sub === '2.7') {
    done.add('2.7')
    // 找選定區內被選定的問題定義（forced_closure 的 time_box_forced 理由便條 cites[0]）
    const forced = findForcedNotes(shapes)
    if (forced.length && Array.isArray(forced[0].cites) && forced[0].cites.length) {
      state.chosenPsId = forced[0].cites[0]
    } else if (state.psId) {
      state.chosenPsId = state.psId
    }
    jlog({ ev: 'chosenPs', id: state.chosenPsId, forcedFound: forced.length })
    log(`[2.7] chosenPsId=${state.chosenPsId}（forced 理由便條=${forced.length}）`)
    await postNote({ text: '怎麼讓袋子出現在手邊？', x: 600, y: 300, sub: '2.7' }) // FAIL：句型不符
    await postNote({ text: '我們可以怎麼用 HMW 改寫成需求？', x: 700, y: 350, sub: '2.7' }) // FAIL：禁字
    // PASS 設計題目（配對 chosenPs；也是前端外框素材）
    const cites = state.chosenPsId ? [state.chosenPsId] : undefined
    await postNote({ text: '我們可以怎麼讓上班族出門時自動記得帶袋子？', x: 900, y: 350, sub: '2.7', cites }) // 確認
  }
}

// ---- 觀察迴圈 ----
let lastSub = null
let completed = false
const startMs = Date.now()
const MAX_MIN = 30

for (let tick = 0; ; tick++) {
  if ((Date.now() - startMs) / 60000 > MAX_MIN) { log('MAX_MIN reached, stop'); break }
  await new Promise((r) => setTimeout(r, 7000))
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  const proj = await api('GET', `/api/projects/${pid}`, undefined, token)
  const sub = tr.body?.current_sub_phase
  const stage = proj.body?.current_stage
  const shapes = await fullState()
  const notes = shapes.filter((s) => (s.shape_type === 'note' || s.type === 'note' || s.text != null))
  const forced = findForcedNotes(shapes)
  const hmws = findHmwNotes(shapes)
  const budget = tr.body?.sub_phase_budget_seconds ?? tr.body?.budget_seconds
  const used = tr.body?.sub_phase_used_seconds ?? tr.body?.used_seconds

  if (sub !== lastSub) {
    log(`>>> SUB ${lastSub} -> ${sub}  stage=${stage} budget=${budget}s`)
    jlog({ ev: 'transition', from: lastSub, to: sub, stage })
    lastSub = sub
  }
  log(`tick=${tick} sub=${sub} stage=${stage} shapes=${shapes.length} notes=${notes.length} forced=${forced.length} hmw=${hmws.length} used=${used}/${budget}s`)
  jlog({ ev: 'tick', tick, sub, stage, shapes: shapes.length, notes: notes.length, forced: forced.length, hmw: hmws.length })

  await runProbes(sub, shapes)

  if (stage === 'completed' || sub === 'completed') {
    if (!completed) {
      completed = true
      log('>>> REACHED COMPLETED')
      jlog({ ev: 'completed', forced: forced.map((f) => ({ id: f.id, text: f.text, cites: f.cites, tbf: f.time_box_forced })), hmw: hmws.map((h) => ({ id: h.id, text: h.text, cites: h.cites })) })
      // 收工後再觀察幾個 tick 抓結業匯報 chat，然後停。
      await new Promise((r) => setTimeout(r, 12000))
      break
    }
  }
}

log('DONE driving. forced-closure notes:', JSON.stringify(findForcedNotes(await fullState()).map((f) => f.text)))
// 保持 presence 直到被 kill
setInterval(async () => {
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  log(`presence alive sub=${tr.body?.current_sub_phase}`)
}, 60000)
