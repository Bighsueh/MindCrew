/**
 * Phase 38 (spec/28) — 暖場（Warmup）= 第一級 Macro Stage + Alternative Uses 破冰遊戲。
 * Phase 39 (spec/16 v1.1) — Timer presets 40/60/90 + intensity 縮放（耦合驗收）。
 *
 * 驗收（API-driven，需 live app 全棧）：
 *   1. 建專案即進暖場：current_stage=warmup、timer current_sub_phase=0.0a。
 *   2. 40 分 preset：timer config intensity=0.4、warmup macro budget=2 分。
 *   3. 全 AI 房：暖場（0.0a）在最低停留後由 Evaluator warmup 分支推進到 discover 1.1a
 *      （不跑 discover 計分、不卡死）。
 *
 * 對照 0605 災情（暖場壓成 1.1a、機器灌爆白板）。暖場已升格為獨立 macro stage。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, apiCall } from './helpers/api'

const EMAIL = `p38_warmup_${Date.now()}@e2e.test`
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

interface TimerState {
  available: boolean
  current_sub_phase?: string
  used_pct?: number
  config?: { intensity?: number; macro_budgets?: Record<string, number>; preset_id?: string }
}

interface ProjectState {
  current_stage?: string
}

/**
 * 部署驗收（deterministic，API-checkable）：證 Phase 38 暖場入口 + Phase 39 intensity 上線。
 *
 * 注意：current_sub_phase 不在 ProjectResponse（只在 timer endpoint）；warmup→discover 跨界
 * 由 Evaluator（supervisor agent 迴圈）驅動，純 API 全 AI 房（無人入座）agent 為 dormant、
 * 不會自動推進——advance 行為由 human-join 的 phase36-warmup-live 測試覆蓋。本測試只硬驗
 * 「入口 + intensity 接線」這些不依賴 agent 的決定性事實，並對 advance 做 best-effort 觀察。
 */
test('Phase 38/39 — 暖場 macro stage 入口 + 40 分 preset intensity 上線（deterministic）', async () => {
  test.setTimeout(120_000)

  const teacher = await loginOrRegisterTeacher(EMAIL, PASSWORD, 'P38 Warmup Teacher')

  // 40 分 preset。前端只送部分欄位 + preset_id；後端 initialize_project 解析為權威 preset
  // （intensity 0.4 + 縮放後 sub_phase_overrides）。
  // Phase 42 B1 (spec/16 §2.1 v2.0)：暖場固定硬上限 5 分——這裡刻意送舊值 warmup=2，
  // 驗證後端強制覆寫為 5（不吃呼叫端值）。
  const timerConfig = {
    total_session_minutes: 40,
    intensity: 0.4,
    macro_budgets: { warmup: 2, discover: 23, define: 15 },
    preset_id: 'timer_preset_40min',
  }

  const create = await apiCall<{ id: string }>(
    'POST',
    '/api/projects',
    {
      name: `P38 Warmup ${Date.now()}`,
      description: 'spec28 warmup macro stage + spec16 v1.1 intensity',
      ai_crew_count: 3,
      personas: [PERSONA(1), PERSONA(2), PERSONA(3)],
      timer_config: timerConfig,
    },
    teacher.token,
  )
  expect([200, 201]).toContain(create.status)
  const projectId = create.body.id
  console.log(`[p38] PROJECT_ID=${projectId}`)

  // (1) 建專案即進暖場 macro stage：current_stage=warmup（Phase 38 入口）。
  const proj = await apiCall<ProjectState>(
    'GET', `/api/projects/${projectId}`, undefined, teacher.token,
  )
  console.log(`[p38] stage=${proj.body?.current_stage}`)
  expect(proj.body?.current_stage).toBe('warmup')

  // Mimic the frontend InitTimerDialog so the timer state is materialised.
  const init = await apiCall(
    'POST', `/api/projects/${projectId}/timer/init`,
    { config: timerConfig }, teacher.token,
  )
  console.log(`[p38] timer/init status=${init.status}`)
  expect([200, 201]).toContain(init.status)

  // (2) timer 落在暖場唯一格 0.0a，且後端權威 40min preset 帶 intensity 0.4；
  //     暖場預算被強制覆寫為固定硬上限 5 分（Phase 42 B1，spec/16 §2.1 v2.0——
  //     送進去的舊值 2 不生效）。warmup_goal=8（max(8, round(20×0.4))）。
  const t0 = await apiCall<TimerState>(
    'GET', `/api/projects/${projectId}/timer`, undefined, teacher.token,
  )
  console.log(
    `[p38] timer sub=${t0.body?.current_sub_phase} intensity=${t0.body?.config?.intensity} ` +
    `warmup_budget=${t0.body?.config?.macro_budgets?.warmup} preset=${t0.body?.config?.preset_id}`,
  )
  expect(t0.body?.current_sub_phase).toBe('0.0a')
  expect(t0.body?.config?.intensity).toBeCloseTo(0.4, 5)
  expect(t0.body?.config?.macro_budgets?.warmup).toBe(5)
  expect(t0.body?.config?.preset_id).toBe('timer_preset_40min')

  // (3) Best-effort 觀察（不硬驗）：純 API 全 AI 房 agent dormant，預期停在暖場；
  //     真正的 warmup→discover advance 由 human-join 的 phase36-warmup-live 覆蓋。
  let lastStage = 'warmup'
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 5_000))
    const p = await apiCall<ProjectState>(
      'GET', `/api/projects/${projectId}`, undefined, teacher.token,
    )
    lastStage = p.body?.current_stage ?? lastStage
  }
  console.log(`[p38] (best-effort) stage after dwell=${lastStage} (advance 由 human-join 測試覆蓋)`)
})
