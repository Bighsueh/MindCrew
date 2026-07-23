/**
 * Spec 27 / v4.15 — sub_phase advancement via the Facilitator-Paced Progression
 * watcher (NO crew advance vote).
 *
 * Regression for the keystone stall: previously the activity sat at sub_phase
 * 1.1a forever because the crew advance vote never reached quorum (threshold 3
 * vs ≤3 AI seats) and the watcher read a NULL top-level current_sub_phase. The
 * vote is now removed; `progression_watcher` deterministically walks the
 * intra-micro sub_phases on (ready ∧ dwell≥floor) OR time-box, and create/
 * start_phase now sync the top-level `project.current_sub_phase` column.
 *
 * All-AI room, 1.1a budget = 1 min (threaded_reveal floor = 50%), so the watcher
 * advances 1.1a→1.1b at ~30s. We also assert no advance-vote endpoint exists.
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, apiCall } from './helpers/api'

const EMAIL = `p36_fac_${Date.now()}@e2e.test`
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
}

test('Spec 27 v4.15 — all-AI room advances past 1.1a via progression watcher (no vote)', async () => {
  test.setTimeout(220_000)

  const teacher = await loginOrRegisterTeacher(EMAIL, PASSWORD, 'P36 Fac Teacher')

  const create = await apiCall<{ id: string }>(
    'POST',
    '/api/projects',
    {
      name: `P36 Facilitator ${Date.now()}`,
      description: 'spec27 v4.15 facilitator-paced advancement regression',
      ai_crew_count: 3,
      personas: [PERSONA(1), PERSONA(2), PERSONA(3)],
      timer_config: {
        total_session_minutes: 120,
        macro_budgets: { discover: 45, define: 30 },
        sub_phase_overrides: { '1.1a': 1 },
        auto_advance_on_timeout: false,
        preset_id: 'timer_preset_2hr',
      },
    },
    teacher.token,
  )
  expect([200, 201]).toContain(create.status)
  const projectId = create.body.id
  console.log(`[fac] PROJECT_ID=${projectId}`)

  // Mimic the frontend InitTimerDialog so the timer actually elapses.
  const init = await apiCall(
    'POST',
    `/api/projects/${projectId}/timer/init`,
    {
      config: {
        total_session_minutes: 120,
        macro_budgets: { discover: 45, define: 30 },
        sub_phase_overrides: { '1.1a': 1 },
        auto_advance_on_timeout: false,
        preset_id: 'timer_preset_2hr',
      },
    },
    teacher.token,
  )
  console.log(`[fac] timer/init status=${init.status}`)
  expect([200, 201]).toContain(init.status)

  // The advance-vote endpoint must no longer exist (removed in v4.15).
  const voteResp = await apiCall(
    'GET', `/api/projects/${projectId}/advance-vote`, undefined, teacher.token,
  )
  console.log(`[fac] advance-vote endpoint status=${voteResp.status}`)
  expect(voteResp.status).toBe(404)

  // Poll the timer endpoint; expect to leave 1.1a once the progression watcher
  // advances (time-floor 50% of a 1-min budget ≈ 30s).
  let lastPhase = '1.1a'
  let lastPct = 0
  const deadline = Date.now() + 150_000
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 5_000))
    const resp = await apiCall<TimerState>(
      'GET', `/api/projects/${projectId}/timer`, undefined, teacher.token,
    )
    const st = resp.body
    lastPhase = st?.current_sub_phase ?? lastPhase
    lastPct = st?.used_pct ?? lastPct
    // eslint-disable-next-line no-console
    console.log(`[fac] sub_phase=${lastPhase} used_pct=${lastPct?.toFixed?.(0)}`)
    if (lastPhase && lastPhase !== '1.1a') break
  }

  console.log(`[fac] RESULT final_sub_phase=${lastPhase}`)
  expect(lastPhase).not.toBe('1.1a')
})
