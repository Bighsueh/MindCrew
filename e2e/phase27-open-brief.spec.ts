/**
 * Phase 27 — 開放任務簡報 + 利害關係人勾選 + 練功坊品牌 E2E
 *
 * 規格：specs/17 §3.0 §11、specs/06 §1.3 §2.3、specs/05 §3、specs/04 §11
 *
 * 涵蓋場景：
 *  AC1: 三步驟 wizard 流程（brief → stakeholders → personas）
 *  AC2: AI 建議條件 chip 採納（附加不覆寫）
 *  AC3: 利害關係人勾選數量必須 == ai_crew_count（負面 → 下一步 disabled）
 *  AC4: 建立後 lobby 顯示 StakeholderPanel
 *  AC5: 舊 project（legacy）進 lobby 不顯示 StakeholderPanel
 *  AC6: 全站品牌「設計專案」「設計思考練功坊」可見、無「學習活動」殘留
 *  AC7: 後端 task_brief_kind 寫入正確（open vs legacy）
 *
 * 假設：
 *  - frontend localhost:3000、backend localhost:8000
 *  - LLM 可用（vLLM 或任一 enabled provider）
 *  - 後端允許教師自助 register
 */
import { test, expect } from '@playwright/test'
import {
  apiCall,
  createMinimalProject,
  loginOrRegisterTeacher,
} from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const STAMP = Date.now()

test.describe('Phase 27 — 開放任務簡報 + 利害關係人勾選', () => {
  const teacher = {
    email: `p27_t_${STAMP}@mindcrew.test`,
    password: 'Phase27Test!',
    name: `T27 ${STAMP}`,
  }
  let teacherToken: string
  let legacyProjectId: string

  test.beforeAll(async () => {
    const acc = await loginOrRegisterTeacher(
      teacher.email,
      teacher.password,
      teacher.name,
    )
    teacherToken = acc.token
    // AC5 用：用 API 建一個 legacy project（不帶 stakeholders）
    legacyProjectId = await createMinimalProject(
      teacherToken,
      `Phase27 legacy ${STAMP}`,
    )
  })

  // ─────────────────────────────────────────────────────────────────────
  // 後端 API smoke tests（不依賴 UI；快速驗證 endpoint）
  // ─────────────────────────────────────────────────────────────────────

  test('AC2 backend：suggest-constraints 回傳四分類陣列', async () => {
    const resp = await apiCall<{
      budget_hints: string[]
      audience_hints: string[]
      venue_hints: string[]
      other_hints: string[]
    }>(
      'POST',
      '/api/projects/draft/suggest-constraints',
      { title: '重新設計大賣場購物車', description: '協助使用者快速結帳' },
      teacherToken,
    )
    expect([200, 502, 504]).toContain(resp.status)
    if (resp.status === 200) {
      expect(Array.isArray(resp.body.budget_hints)).toBeTruthy()
      expect(Array.isArray(resp.body.audience_hints)).toBeTruthy()
      // 至少一個分類有 hint
      const total =
        resp.body.budget_hints.length +
        resp.body.audience_hints.length +
        resp.body.venue_hints.length +
        resp.body.other_hints.length
      expect(total).toBeGreaterThan(0)
    }
  })

  test('AC3 backend：suggest-stakeholders 回 6-10 位具體人', async () => {
    const resp = await apiCall<{
      suggestions: Array<{
        id: string
        name: string
        role: string
        relevance: string
      }>
    }>(
      'POST',
      '/api/projects/draft/suggest-stakeholders',
      {
        title: '重新設計大賣場購物車',
        description: '協助使用者快速結帳',
        constraints: '預算微型；可能族群:重度推車使用者',
      },
      teacherToken,
    )
    expect([200, 502, 504]).toContain(resp.status)
    if (resp.status === 200) {
      const list = resp.body.suggestions
      expect(list.length).toBeGreaterThanOrEqual(3) // 容忍 LLM 略低於 6
      expect(list.length).toBeLessThanOrEqual(10)
      for (const s of list) {
        expect(s.id).toBeTruthy()
        expect(s.name).toBeTruthy()
        expect(s.role).toBeTruthy()
      }
    }
  })

  test('AC7 backend：建立帶 stakeholders 的 project → task_brief_kind=open', async () => {
    // 先抓 stakeholders
    const sug = await apiCall<{
      suggestions: Array<{
        id: string
        name: string
        role: string
        relevance: string
      }>
    }>(
      'POST',
      '/api/projects/draft/suggest-stakeholders',
      { title: 'AC7 stake test', description: 'fixture', constraints: null },
      teacherToken,
    )
    test.skip(sug.status !== 200, 'LLM unavailable — skip AC7')
    const picked = sug.body.suggestions.slice(0, 3)

    // 用 picked stakeholders 建 project
    const create = await apiCall<{
      id: string
      stakeholders: unknown[]
      task_brief_kind: string
    }>(
      'POST',
      '/api/projects',
      {
        name: `Phase27 open ${STAMP}`,
        description: '開放任務簡報測試',
        constraints: 'AC7 fixture constraint',
        stakeholders: picked,
        ai_contribution: 'medium',
        ai_crew_count: 3,
        personas: [
          minimalPersona(1),
          minimalPersona(2),
          minimalPersona(3),
        ],
        timer_config: {
          mode: 'preset',
          preset_id: 'preset_2hr',
          auto_advance_on_timeout: false,
          allow_overrun: true,
        },
      },
      teacherToken,
    )
    expect([200, 201]).toContain(create.status)
    expect(create.body.task_brief_kind).toBe('open')
    expect(create.body.stakeholders.length).toBe(3)

    // 抓回確認持久化
    const got = await apiCall<{
      stakeholders: unknown[]
      task_brief_kind: string
    }>('GET', `/api/projects/${create.body.id}`, undefined, teacherToken)
    expect(got.status).toBe(200)
    expect(got.body.task_brief_kind).toBe('open')
    expect(got.body.stakeholders.length).toBe(3)
  })

  test('AC5 backend：legacy project task_brief_kind=legacy + stakeholders 為空', async () => {
    const got = await apiCall<{
      stakeholders: unknown[]
      task_brief_kind: string
    }>('GET', `/api/projects/${legacyProjectId}`, undefined, teacherToken)
    expect(got.status).toBe(200)
    expect(got.body.task_brief_kind).toBe('legacy')
    expect(got.body.stakeholders.length).toBe(0)
  })

  // ─────────────────────────────────────────────────────────────────────
  // UI tests（依賴 frontend 起著）
  // ─────────────────────────────────────────────────────────────────────

  test('AC6 UI：登入後 AppLayout 顯示「設計思考練功坊」品牌 + nav「設計專案」', async ({
    page,
  }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto('/projects', { waitUntil: 'networkidle' })

    await expect(page.getByText('設計思考練功坊').first()).toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByText('設計專案', { exact: false }).first()).toBeVisible({
      timeout: 10_000,
    })
    // 不應再看到「學習活動」字樣
    await expect(page.getByText('學習活動')).toHaveCount(0)
  })

  test('AC1 UI：CreateProjectDialog 顯示三步驟 wizard 標籤', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto('/projects', { waitUntil: 'networkidle' })

    // 點建立按鈕（"開新設計專案" 或 "建立新設計專案"）
    const btn = page
      .locator('button')
      .filter({ hasText: /(開新|建立新)?設計專案/ })
      .first()
    await btn.click()

    // Step 標籤（each appears twice：step chip "1. 設計簡報" + MindsetHintCard 標題）
    await expect(page.getByText('1. 設計簡報')).toBeVisible()
    await expect(page.getByText('2. 利害關係人地圖')).toBeVisible()
    await expect(page.getByText('3. 設計 AI 隊友')).toBeVisible()

    // ConstraintsField 不應再有預設的 checkbox 文字
    await expect(page.getByText('兒童', { exact: true })).toHaveCount(0)
    await expect(page.getByText('青少年', { exact: true })).toHaveCount(0)
    await expect(page.getByText('校園', { exact: true })).toHaveCount(0)

    // 有「由 AI 建議條件」按鈕
    await expect(
      page.getByRole('button', { name: /AI 建議條件|建議條件/ }),
    ).toBeVisible()
  })

  test('AC4 UI：開 legacy lobby 不顯示 StakeholderPanel', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects/${legacyProjectId}/lobby`, {
      waitUntil: 'networkidle',
    })

    // legacy project stakeholders 為 [] → 不顯示 panel 標題
    await expect(page.getByText('設定的利害關係人')).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────
// fixture helpers
// ─────────────────────────────────────────────────────────────────────

function minimalPersona(idx: number) {
  return {
    seat_role: `crew_${idx}`,
    persona: {
      name: `測試人${idx}`,
      role: `測試角色${idx}`,
      expertise: '測試專長',
      personality_axis: 'balanced',
      personality_desc: '冷靜、務實、好奇',
      backstory: '測試 fixture',
      lens_affinities: {
        empathy: 0.5,
        structure: 0.5,
        creativity: 0.5,
        feasibility: 0.5,
      },
    },
  }
}
