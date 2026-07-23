/**
 * Phase 42 定義階段 confound 拆解 — 90 分「單房 + 全 AI + 不壓縮」clean run。
 *
 * 目的：移除 C2 驗收時的兩個 confound（壓縮預算 + 2 房併打單一 gemma），量出在
 * 正常時長、單房、不搶 LLM 下，定義階段 crew 到底有沒有回合、有沒有嘗試 problem_statement。
 *
 * 設計：單一全 AI 房（真人只連 WS 保 presence、全程不貼便條/不發言），送 90 分 preset
 * （只給 preset_id + total + intensity、**不送 sub_phase_overrides**→後端 load 權威 PRESET_90MIN，
 * warmup 5 / discover 51 / define 34 分，逐格比例上限、不壓縮）。觀察窗拉長到 100 分。
 *
 * 每 tick 記：sub_phase、各作者便條數（crew vs supervisor）、痛點牆/pov 牆/選定區張數、
 * forced/hmw、轉場。定義階段的 crew 回合與 problem_statement 嘗試另由後端 log 事後判讀。
 *
 * 用法：node e2e/c2-clean-run.mjs
 */
import { writeFileSync, appendFileSync } from 'node:fs'

const BACKEND = 'http://localhost:8000'
const SIDECAR = 'http://localhost:4000'
const EMAIL = `c2_clean_${Date.now()}@e2e.test`
const PASSWORD = 'Passw0rd!e2e'
const HUMAN_NAME = '旁觀者'
const SESSION_FILE = 'e2e/c2-clean-session.json'
const LOGFILE = 'e2e/c2-clean-log.jsonl'
const MAX_MIN = 100

function ts() { return new Date().toISOString().slice(11, 19) }
function log(...a) { console.log(`[${ts()}][clean]`, ...a) }
function jlog(o) { try { appendFileSync(LOGFILE, JSON.stringify({ t: new Date().toISOString(), ...o }) + '\n') } catch {} }

async function api(method, path, body, token, base = BACKEND) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${base}${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  const text = await res.text()
  let parsed = null
  try { parsed = text ? JSON.parse(text) : null } catch { parsed = text }
  return { status: res.status, body: parsed }
}

const PERSONA = (i) => ({
  seat_role: `crew_${i}`,
  persona: { name: `隊友${i}`, role: `測試角色 ${i}`, expertise: '測試專長',
    personality_axis: ['supportive', 'balanced', 'contrarian'][i - 1] ?? 'balanced',
    personality_desc: '務實穩健、邏輯清晰', backstory: '測試用人設',
    lens_affinities: { empathy: 0.5, structure: 0.5, creativity: 0.5, feasibility: 0.5 } },
})

await api('POST', '/api/auth/register', { email: EMAIL, password: PASSWORD, display_name: HUMAN_NAME, role: 'teacher' })
let token = null
for (let i = 0; i < 10 && !token; i++) {
  const l = await api('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD })
  if (l.status === 200) token = l.body.access_token; else await new Promise((r) => setTimeout(r, 300))
}
if (!token) throw new Error('login failed')

// 90 分 preset：不送 sub_phase_overrides → 後端用權威 PRESET_90MIN（warmup5/discover51/define34、intensity0.8）
const timerConfig = { total_session_minutes: 90, intensity: 0.8, preset_id: 'timer_preset_90min' }
const create = await api('POST', '/api/projects', {
  name: `C2 Clean 90min ${Date.now()}`,
  description: '怎麼讓大家更願意把環保袋帶出門、真的用起來',
  ai_crew_count: 3, personas: [PERSONA(1), PERSONA(2), PERSONA(3)], timer_config: timerConfig,
}, token)
if (![200, 201].includes(create.status)) throw new Error(`create failed ${create.status} ${JSON.stringify(create.body)}`)
const pid = create.body.id
log('PROJECT_ID =', pid)
await api('POST', `/api/projects/${pid}/timer/init`, { config: timerConfig }, token)
await api('POST', `/api/projects/${pid}/join`, { seat_role: 'human_creator' }, token)
writeFileSync(SESSION_FILE, JSON.stringify({ project_id: pid, token, email: EMAIL, mode: 'clean90' }, null, 2))
jlog({ ev: 'created', pid })

// 印實際生效的逐格預算（驗證沒被壓縮）
const tr0 = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
log('preset 生效，current_sub_phase=', tr0.body?.current_sub_phase, 'budget=', tr0.body?.sub_phase_budget_seconds ?? tr0.body?.budget_seconds, 's')

let ws
function openWS() {
  ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${token}`)
  ws.addEventListener('close', () => setTimeout(openWS, 1000))
  ws.addEventListener('message', (e) => {
    try {
      const m = JSON.parse(e.data); if (!m?.type) return
      if (['presence', 'pong', 'cursor', 'agent_typing'].includes(m.type)) return
      jlog({ ev: 'ws', type: m.type })
      if (['stage_changed', 'first_diamond_completed'].includes(m.type)) log(`[WS] ${m.type}`)
    } catch {}
  })
}
openWS()
await new Promise((r) => setTimeout(r, 2500))
log('WS connected（presence 保持，全程不貼/不發言）')

function authorType(n) {
  const a = n.author || ''
  if (/引導者|supervisor/.test(a)) return 'sup'
  if (/\(ai\)$/.test(a)) return 'crew'
  if (/\(human\)$/.test(a)) return 'human'
  return 'other'
}

let lastSub = null
let reachedDefine = false
let completed = false
const startMs = Date.now()

for (let tick = 0; ; tick++) {
  if ((Date.now() - startMs) / 60000 > MAX_MIN) { log('MAX_MIN reached, stop'); break }
  await new Promise((r) => setTimeout(r, 15000))
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  const proj = await api('GET', `/api/projects/${pid}`, undefined, token)
  const cs = await api('GET', `/api/projects/${pid}/canvas-state`, undefined, token)
  const sub = tr.body?.current_sub_phase
  const stage = proj.body?.current_stage
  const budget = tr.body?.sub_phase_budget_seconds ?? tr.body?.budget_seconds
  const used = tr.body?.sub_phase_used_seconds ?? tr.body?.used_seconds
  const notes = Array.isArray(cs.body?.notes) ? cs.body.notes : []
  const by = { crew: 0, sup: 0, human: 0, other: 0 }
  let labels = 0
  for (const n of notes) { if (n.kind === 'label') labels++; by[authorType(n)]++ }

  if (sub !== lastSub) {
    log(`>>> SUB ${lastSub} -> ${sub}  stage=${stage} budget=${budget}s`)
    jlog({ ev: 'transition', from: lastSub, to: sub, stage, budget })
    lastSub = sub
  }
  log(`t=${tick} sub=${sub} stage=${stage} used=${used}/${budget}s notes=${notes.length}[crew=${by.crew} sup=${by.sup} label=${labels}]`)
  jlog({ ev: 'tick', tick, sub, stage, used, budget, notes: notes.length, by, labels })

  if (!reachedDefine && (sub?.startsWith('2.') || stage === 'define')) {
    reachedDefine = true
    log(`>>> REACHED DEFINE: sub=${sub} budget=${budget}s（定義階段觀測窗開始）`)
    jlog({ ev: 'reached_define', sub, budget })
  }
  if ((stage === 'completed' || sub === 'completed') && !completed) {
    completed = true
    log('>>> COMPLETED')
    jlog({ ev: 'completed', notes: notes.length, by })
    await new Promise((r) => setTimeout(r, 10000))
    break
  }
}
log('DONE driving.')
setInterval(async () => {
  const tr = await api('GET', `/api/projects/${pid}/timer`, undefined, token)
  log(`presence alive sub=${tr.body?.current_sub_phase}`)
}, 60000)
