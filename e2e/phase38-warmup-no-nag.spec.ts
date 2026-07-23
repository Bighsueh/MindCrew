/**
 * Phase 38 修復驗收 — 暖場組長「點名後留白、不連環催」。
 *
 * Bug（2026-06 實機）：組長對著還沒開口的學員，每 ~57s 連環催 5 次。根因：
 * awaiting-reply lock TTL=45s < supervisor 決策週期 ~57-60s → 鎖每次都在下個週期前過期、
 * 形同虛設。修：lock TTL 45→120s + 人類發話主動清鎖。
 *
 * 驗收（Playwright + Chrome，提供真實 presence 讓 agents 運轉）：
 *   人類入座但**全程沉默**，觀察組長訊息時序。修復後組長點名後 lock 120s → 必出現
 *   ≥95s 的長靜默；修復前 ~57s 連環催（最大間隔 <95s）。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, apiCall } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const EMAIL = `warmup_nonag_${Date.now()}@e2e.test`
const PASSWORD = 'Test1234!'

const PERSONA = (idx: number) => ({
  seat_role: `crew_${idx}`,
  persona: {
    name: `測試隊友 ${idx}`,
    role: `測試角色 ${idx}`,
    expertise: '測試專長',
    personality_axis: ['supportive', 'balanced', 'contrarian'][idx - 1] ?? 'balanced',
    personality_desc: '務實穩健、邏輯清晰、執行力強',
    backstory: '測試用人設',
    lens_affinities: { empathy: 0.5, structure: 0.5, creativity: 0.5, feasibility: 0.5 },
  },
})

interface Msg { sender_type: string; sender_name: string; content: string; created_at: string }

const isSupervisor = (m: Msg) =>
  m.sender_type === 'ai' &&
  (m.sender_name?.includes('引導者') || m.sender_name === 'Supervisor')

test('Phase 38 — 暖場組長點名後留白、不連環催（lock TTL 修復）', async ({ page }) => {
  test.setTimeout(260_000)

  const teacher = await loginOrRegisterTeacher(EMAIL, PASSWORD, 'NoNag Teacher')
  const token = teacher.token

  const create = await apiCall<{ id: string }>(
    'POST', '/api/projects',
    {
      name: `暖場不連環催 ${Date.now()}`,
      description: 'awaiting-reply lock TTL 修復驗收',
      ai_crew_count: 3,
      personas: [PERSONA(1), PERSONA(2), PERSONA(3)],
      timer_config: { total_session_minutes: 40, intensity: 0.4, macro_budgets: { warmup: 2, discover: 23, define: 15 }, preset_id: 'timer_preset_40min' },
    },
    token,
  )
  expect([200, 201]).toContain(create.status)
  const pid = create.body.id
  console.log(`[nonag] PROJECT_ID=${pid}`)

  // 人類入座 crew_1 → 喚醒 agents；turn-policy best-effort（403 容忍）。
  console.log('join crew_1:', (await apiCall('POST', `/api/projects/${pid}/join`, { seat_role: 'crew_1' }, token)).status)
  console.log('turn-policy:', (await apiCall('PATCH', `/api/projects/${pid}/turn-policy`, { policy: 'open_floor' }, token)).status)

  // 開 workspace（Chrome）→ 建立 presence，組長開始主持暖場。
  await suppressFirstRunModals(page)
  await loginViaUi(page, EMAIL, PASSWORD)
  await page.goto(`/projects/${pid}/workspace`, { waitUntil: 'networkidle' })
  await expect(page.locator('.tl-container').first()).toBeAttached({ timeout: 20_000 })

  // 觀察 ~190s——人類全程沉默，蒐集組長訊息時間戳（用 created_at 精確算間隔）。
  const supTimes: number[] = []
  const seen = new Set<string>()
  const traj: string[] = []
  const t0 = Date.now()
  for (let i = 0; i < 24; i++) {
    await page.waitForTimeout(8_000)
    const r = await apiCall<{ messages: Msg[] }>(
      'GET', `/api/projects/${pid}/messages?chat_id=group&limit=100`, undefined, token,
    )
    for (const m of r.body?.messages ?? []) {
      if (!isSupervisor(m)) continue
      const key = `${m.created_at}|${(m.content || '').slice(0, 14)}`
      if (seen.has(key)) continue
      seen.add(key)
      supTimes.push(new Date(m.created_at).getTime())
      traj.push(`+${Math.round((Date.now() - t0) / 1000)}s 「${(m.content || '').slice(0, 26)}」`)
    }
  }

  console.log('組長訊息軌跡：\n  ' + traj.join('\n  '))
  supTimes.sort((a, b) => a - b)
  let maxGap = 0
  for (let i = 1; i < supTimes.length; i++) {
    maxGap = Math.max(maxGap, (supTimes[i] - supTimes[i - 1]) / 1000)
  }
  if (supTimes.length) maxGap = Math.max(maxGap, (Date.now() - supTimes[supTimes.length - 1]) / 1000)
  console.log(`組長訊息數=${supTimes.length} 最大靜默間隔=${maxGap.toFixed(0)}s`)
  await page.screenshot({ path: 'phase38-warmup-no-nag.png', fullPage: true })

  // 修復前 ~57s 連環催（最大間隔 <95s）；修復後點名後 lock 120s → 必有 ≥95s 靜默。
  expect(
    maxGap,
    `組長點名後應留白（出現 ≥95s 長靜默），不再 ~57s 連環催。實際軌跡見 log。`,
  ).toBeGreaterThanOrEqual(95)
})
