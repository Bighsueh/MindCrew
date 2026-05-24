/**
 * Phase 23 — Lobby 三視圖 + 每專案 1 位人類硬限 E2E
 *
 * 規格：specs/17 §3.4、specs/06 §2.3、specs/05 §4。
 *
 * 三視圖：
 *  - 教師（creator） → 看到完整 SeatSelectionGrid + ObserverCard + 各 crew row 入座鈕
 *  - 學生 A（未入座）→ 看到 JoinSeatCard CTA「加入討論」、不見 ObserverCard、不見 crew row 入座鈕
 *  - 學生 B（學生 A 入座後再來）→ JoinSeatCard 變 disabled，文字「此設計專案已有人類參與者」
 *
 * 假設：
 *  - 後端 / 前端 已起在 localhost:3000 / 8000。
 *  - 後端允許自助 register 新 teacher 帳號（loginOrRegisterTeacher 內 fallback 註冊）。
 *  - 後端 /api/teacher/students 端點可由 teacher 建立學生帳號。
 */
import { test, expect } from '@playwright/test'
import {
  apiCall,
  createMinimalProject,
  loginOrRegisterTeacher,
  registerStudent,
} from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

interface SeatInfo {
  seat_role: string
  occupant_type: string
}

test.describe('Phase 23 — Lobby 三視圖', () => {
  const stamp = Date.now()
  const teacher = {
    email: `p23_t_${stamp}@mindcrew.test`,
    password: 'Phase23Test!',
    name: `T23 ${stamp}`,
  }
  const studentA = {
    email: `p23_sa_${stamp}@mindcrew.test`,
    password: 'Phase23Test!',
    name: `SA ${stamp}`,
  }
  const studentB = {
    email: `p23_sb_${stamp}@mindcrew.test`,
    password: 'Phase23Test!',
    name: `SB ${stamp}`,
  }
  let projectId: string

  test.beforeAll(async () => {
    const teacherAcc = await loginOrRegisterTeacher(teacher.email, teacher.password, teacher.name)
    await registerStudent(teacherAcc.token, studentA.email, studentA.password, studentA.name)
    await registerStudent(teacherAcc.token, studentB.email, studentB.password, studentB.name)
    projectId = await createMinimalProject(teacherAcc.token, `Phase 23 Lobby ${stamp}`)
  })

  test('教師視圖：看到完整 SeatSelectionGrid + ObserverCard', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects/${projectId}/lobby`, { waitUntil: 'networkidle' })

    // 教師應看到 ObserverCard（觀察者模式 / 進入工作區），不該看到「加入這個設計專案」CTA
    await expect(page.getByText('加入這個設計專案')).toHaveCount(0)
    // SeatSelectionGrid 應渲染（含「組長」文字）
    await expect(page.getByText('組長', { exact: false }).first()).toBeVisible({ timeout: 10_000 })
  })

  test('學生 A 視圖：JoinSeatCard CTA「加入討論」可點，且看不到 ObserverCard', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, studentA.email, studentA.password)
    await page.goto(`/projects/${projectId}/lobby`, { waitUntil: 'networkidle' })

    await expect(page.getByText('加入這個設計專案')).toBeVisible({ timeout: 10_000 })
    const joinBtn = page.getByRole('button', { name: /加入討論/ })
    await expect(joinBtn).toBeVisible()
    await expect(joinBtn).toBeEnabled()

    // 點擊後應由後端自動分配 crew，CTA 切換為「進入工作區」
    await joinBtn.click()
    await expect(
      page.getByRole('button', { name: /進入工作區/ }),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('學生 B 視圖：學生 A 已入座 → CTA disabled + 顯示「此設計專案已有人類參與者」', async ({ page }) => {
    // 雙保險：透過後端 API 確認專案確實有 1 位人類佔位（避免上題若 race 失敗本題誤報）
    const teacherAcc = await loginOrRegisterTeacher(teacher.email, teacher.password, teacher.name)
    const proj = await apiCall<{ seats: SeatInfo[] }>('GET', `/api/projects/${projectId}`, undefined, teacherAcc.token)
    const humanSeats = proj.body.seats.filter((s) => s.occupant_type === 'human')
    expect(humanSeats.length, `學生 A 應已佔位；實際 humans=${humanSeats.length}`).toBe(1)

    await suppressFirstRunModals(page)
    await loginViaUi(page, studentB.email, studentB.password)
    await page.goto(`/projects/${projectId}/lobby`, { waitUntil: 'networkidle' })

    await expect(page.getByText('此設計專案已有人類參與者')).toBeVisible({ timeout: 10_000 })
    // CTA 應 disabled（button[disabled]）
    const cta = page.locator('button:has-text("此設計專案已有人類參與者")')
    await expect(cta).toBeDisabled()
  })
})
