/**
 * Phase 36 / Spec 27 v2.0 — LIVE 活動驗收（Playwright + Chrome，真實 AI）。
 *
 * 完整參與者流程：teacher 建專案 → student 佔人類席位(crew_1) → student 在 Chrome
 * 登入進 workspace → 像真人送開場訊息 → 觀察 AI 以「接話式」貼出沉澱概念便條。
 *
 * 行為面以「輪詢 canvas-state + 截圖」觀察；驗證任何 live 便條皆為 v2.0 結構（無連線欄位）。
 */
import { test, expect } from '@playwright/test'
import {
  loginOrRegisterTeacher,
  registerStudent,
  createMinimalProject,
  apiCall,
} from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const TEA_EMAIL = `p36_tea_${Date.now()}@e2e.test`
const STU_EMAIL = `p36_stu_${Date.now()}@e2e.test`
const PASSWORD = 'Test1234!'

interface CanvasNote {
  id: string
  content: string
  kind?: string
  group_id?: string | null
  author?: string
}

test('Phase 36 v2.0 LIVE — student 參與者觸發真實 AI 接話式貼便條', async ({ page }) => {
  test.setTimeout(320_000)

  const teacher = await loginOrRegisterTeacher(TEA_EMAIL, PASSWORD, 'P36 Tea')
  const projectId = await createMinimalProject(teacher.token, `P36 LIVE ${Date.now()}`)
  const student = await registerStudent(teacher.token, STU_EMAIL, PASSWORD, 'P36 學生')

  // student 佔人類席位（接管 crew_1 → 該席變人類，其餘 crew_2/3 + supervisor 仍 AI）
  const join = await apiCall(
    'POST', `/api/projects/${projectId}/join`, { seat_role: 'crew_1' }, student.token,
  )
  console.log(`[live] join status=${join.status} body=${JSON.stringify(join.body).slice(0, 120)}`)
  expect([200, 201]).toContain(join.status)

  await suppressFirstRunModals(page)
  await loginViaUi(page, STU_EMAIL, PASSWORD)
  await page.goto(`/projects/${projectId}/workspace`, { waitUntil: 'networkidle' })
  await expect(page.locator('.tl-container').first()).toBeAttached({ timeout: 20_000 })
  await page.screenshot({ path: 'e2e/phase36-live-00-initial.png', fullPage: true })

  // 送開場訊息（student 有席位 → chat 應已啟用）
  const chatInput = page.locator('textarea[placeholder*="輸入訊息"]').first()
  await expect(chatInput).toBeEnabled({ timeout: 20_000 })
  await chatInput.fill('大家好，我最近在大型超市購物遇到一些困擾，想跟大家聊聊。')
  await chatInput.press('Enter')
  console.log('[live] kickoff message sent')

  // 觀察：每 15s dump canvas-state + 截圖；最多 ~4.5 分鐘或直到出現 ≥3 張便條
  let lastNotes: CanvasNote[] = []
  const deadline = Date.now() + 270_000
  let tick = 0
  while (Date.now() < deadline) {
    await page.waitForTimeout(15_000)
    tick++
    const resp = await apiCall<{ notes: CanvasNote[] }>(
      'GET', `/api/projects/${projectId}/canvas-state`, undefined, student.token,
    )
    lastNotes = resp.body?.notes ?? []
    const groups = [...new Set(lastNotes.map((n) => n.group_id).filter(Boolean))]
    console.log(`[live] t=${tick * 15}s notes=${lastNotes.length} groups=${JSON.stringify(groups)}`)
    if (tick % 2 === 0) {
      await page.screenshot({ path: `e2e/phase36-live-${String(tick).padStart(2, '0')}.png`, fullPage: true })
    }
    if (lastNotes.length >= 3) break
  }
  await page.screenshot({ path: 'e2e/phase36-live-final.png', fullPage: true })

  console.log('[live] === 便條快照 ===')
  for (const n of lastNotes.slice(0, 20)) {
    console.log(`  [${n.kind}|${n.group_id ?? '-'}] ${n.content}  (by ${n.author})`)
  }

  // v2.0 結構：任何 live 便條只有 kind/group_id，無連線欄位
  for (const n of lastNotes) {
    expect(n).not.toHaveProperty('relation')
    expect(n).not.toHaveProperty('derived_from_id')
    expect(n).not.toHaveProperty('lineage_id')
  }
  await expect(
    page.locator('[data-concept-evolution-overlay], .concept-evolution-line, svg.concept-evolution'),
  ).toHaveCount(0)

  console.log(`[live] RESULT notes_observed=${lastNotes.length}`)
  // 至少觀察到 AI 有產出便條（live 行為證據）
  expect(lastNotes.length).toBeGreaterThan(0)
})
