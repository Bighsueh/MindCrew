/**
 * Phase 42 C1 live 驗收驅動腳本（docker 全棧）。
 *
 * 開一間 40min 單真人房（顯示名＝小美，intensity 0.4，3 AI crew），入座、保持 WS
 * presence（Human Presence Gate），長輪詢記錄 sub_phase / 牆面便條盤點 / 轉場，並在
 * 1.1b 達「組長已驅動 crew 貼名字、真人尚未出手」時：先觀察一個窗口確認 gate HELD
 * （crew 貼滿但仍停 1.1b），再由真人親手貼一張「只寫名字」便條，觀察是否解鎖推進到 1.1c。
 *
 * 跑到 sub_phase 進入 2.1（define）或逾時即停止主動作，但保持 presence 不關。
 * 事件流另寫 e2e/c1-live-log.jsonl 供事後分析。
 *
 * 用法：node e2e/c1-live-run.mjs
 */

import { writeFileSync, appendFileSync } from 'node:fs'

const BACKEND = 'http://localhost:8000'
const SIDECAR = 'http://localhost:4000'
const EMAIL = `c1_live_${Date.now()}@e2e.test`
const PASSWORD = 'Passw0rd!e2e'
const HUMAN_NAME = '小美'
const LOGFILE = 'e2e/c1-live-log.jsonl'

// stakeholder_public: x[100,2100] y[100,900]；pain_wall: x[100,2300] y[1000,2000]
function zoneOf(x, y) {
  if (y >= 1000) return 'pain_wall'
  if (y >= 100 && y < 1000) return 'stakeholder/discover'
  return 'other'
}

// macro stage 不是 timer 欄位，依 sub_phase 在地映射（workflow map）
const DISCOVER = new Set(['1.1a', '1.1b', '1.1c', '1.1d', '1.2'])
const DEFINE = new Set(['2.1', '2.2', '2.3', '2.4', '2.5', '2.6', '2.7'])
function macroOf(sub) {
  if (sub === '0.0a') return 'warmup'
  if (DISCOVER.has(sub)) return 'discover'
  if (DEFINE.has(sub)) return 'define'
  return '?'
}

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
function jlog(obj) { try { appendFileSync(LOGFILE, JSON.stringify({ t: new Date().toISOString(), ...obj }) + '\n') } catch {} }

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
  name: `C1 Live ${Date.now()}`,
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
jlog({ ev: 'created', pid })

await api('POST', `/api/projects/${pid}/timer/init`, { config: timerConfig }, token)
await api('POST', `/api/projects/${pid}/join`, { seat_role: 'human_creator' }, token)
log('joined human_creator')

writeFileSync('e2e/c1-live-session.json', JSON.stringify({
  project_id: pid, token, email: EMAIL, password: PASSWORD, human_name: HUMAN_NAME,
}, null, 2))
log('session written to e2e/c1-live-session.json')

// Human Presence Gate：保持 WS 連線不關。
let ws
let sawWaitingForHuman1_1b = false
function openWS() {
  ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
  ws.addEventListener('close', () => { setTimeout(openWS, 1000) })
  ws.addEventListener('message', (e) => {
    try {
      const m = JSON.parse(e.data)
      if (m && m.type && !['presence', 'pong', 'cursor'].includes(m.type)) {
        jlog({ ev: 'ws', type: m.type, data: m })
        if (m.type === 'waiting_for_human') {
          const sp = m.sub_phase ?? m.data?.sub_phase ?? m.payload?.sub_phase
          log(`   [WS] waiting_for_human sub_phase=${sp} required=${JSON.stringify(m.required ?? m.data?.required ?? m.payload?.required)}`)
          if (sp === '1.1b') sawWaitingForHuman1_1b = true
        } else if (['turn_state', 'artifact_gate_rejected', 'reject_toast', 'note_rejected', 'stage_changed'].includes(m.type)) {
          log(`   [WS] ${m.type}: ${JSON.stringify(m).slice(0, 200)}`)
        }
      }
    } catch {}
  })
}
openWS()
await new Promise((res) => setTimeout(res, 2500))
log('WS connected（presence 保持）')

// ---- 觀察迴圈 ----
let lastSub = null
let humanPosted = false
let gateHeldTicks = 0
let reached21 = false
const startMs = Date.now()
const MAX_MIN = 42

function inventory(notes, shapes) {
  const posById = new Map()
  for (const s of shapes) posById.set(s.id, s)
  const z = { 'stakeholder/discover': { ai: 0, human: 0, label: 0 }, pain_wall: { ai: 0, human: 0, label: 0 }, other: { ai: 0, human: 0, label: 0 } }
  const labels = []
  for (const n of notes) {
    const s = posById.get(n.id)
    const zone = s ? zoneOf(s.x, s.y) : 'other'
    const isHuman = /\(human\)$/.test(n.author || '')
    if (n.kind === 'label') { z[zone].label++; labels.push({ content: n.content, group_id: n.group_id, zone }) }
    else if (isHuman) z[zone].human++
    else z[zone].ai++
  }
  return { z, labels }
}

for (let tick = 0; ; tick++) {
  if ((Date.now() - startMs) / 60000 > MAX_MIN) { log('MAX_MIN reached, stop driving (presence kept)'); break }
  await new Promise((res) => setTimeout(res, 8000))
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  const cs = await api('GET', `/api/projects/${pid}/canvas-state`, undefined, token)
  const full = await api('GET', `/api/projects/${pid}/canvas-state/full`, undefined, token, SIDECAR)
  const sub = tr.body?.current_sub_phase
  const macro = macroOf(sub)
  const notes = Array.isArray(cs.body?.notes) ? cs.body.notes : []
  const shapes = Array.isArray(full.body) ? full.body : []
  const { z, labels } = inventory(notes, shapes)
  const budgetSec = tr.body?.sub_phase_budget_seconds ?? tr.body?.budget_seconds
  const usedSec = tr.body?.sub_phase_used_seconds ?? tr.body?.used_seconds
  const subBudget = budgetSec != null ? `${Math.round(budgetSec / 60)}m(${usedSec ?? '?'}s used)` : '?'

  if (sub !== lastSub) {
    log(`>>> SUB TRANSITION ${lastSub} -> ${sub}  macro=${macro} budget=${subBudget}min`)
    jlog({ ev: 'transition', from: lastSub, to: sub, macro, subBudget })
    lastSub = sub
    gateHeldTicks = 0
  }

  const line = `tick=${tick} sub=${sub} macro=${macro} notes=${notes.length} ` +
    `stake[ai=${z['stakeholder/discover'].ai} human=${z['stakeholder/discover'].human} label=${z['stakeholder/discover'].label}] ` +
    `pain[ai=${z.pain_wall.ai} human=${z.pain_wall.human} label=${z.pain_wall.label}] budget=${subBudget}`
  log(line)
  jlog({ ev: 'tick', tick, sub, macro, z, labels, total: notes.length, subBudget })
  if (labels.length) jlog({ ev: 'labels', sub, labels })

  // ② 1.1b 真人 gate 自動演示
  if (sub === '1.1b' && !humanPosted) {
    const crewStake = z['stakeholder/discover'].ai
    const anyHuman = z['stakeholder/discover'].human > 0
    if (anyHuman) { humanPosted = true }
    else if (crewStake >= 2 || sawWaitingForHuman1_1b) {
      gateHeldTicks++
      log(`   [1.1b] crew 牆面便條=${crewStake}，真人尚未出手，waiting_for_human=${sawWaitingForHuman1_1b}；gate 觀察窗 tick=${gateHeldTicks}（仍停 1.1b 即 gate HELD）`)
      // 觀察 2 ticks（~16s）確認未推進，再由真人親手貼一張名字便條
      if (gateHeldTicks >= 2 || sawWaitingForHuman1_1b) {
        log('   [1.1b] >>> 真人親手貼「只寫名字」便條：陳建宏')
        const r = await api('POST', `/api/projects/${pid}/canvas/notes`, {
          text: '陳建宏', color: 'yellow', x: 840, y: 400, sub_phase_id: '1.1b', kind: 'content',
        }, token)
        log('   [1.1b] human note resp:', JSON.stringify(r.body).slice(0, 240))
        jlog({ ev: 'human_note_1_1b', resp: r.body, status: r.status })
        humanPosted = true
      }
    }
  }

  if (sub === '2.1' || macro === 'define' || sub?.startsWith('2.')) {
    if (!reached21) {
      reached21 = true
      log(`>>> REACHED DEFINE BOUNDARY: sub=${sub} macro=${macro} budget=${subBudget}min`)
      jlog({ ev: 'reached_define', sub, macro, subBudget })
    }
  }
}

// 保持 presence
setInterval(async () => {
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  log(`presence alive sub=${tr.body?.current_sub_phase}`)
}, 60000)
