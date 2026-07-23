/**
 * Phase 43 — 實驗深連結自動代填（Study Deep-Link Ghost Autofill）E2E
 *
 * 規格：specs/29-study-deep-link.md、specs/05 §3 Flow 2 v4.27
 *
 * 涵蓋場景：
 *  AC1: 深連結 → 自動開精靈 → 幽靈代填播畢 → 六欄值正確＋narration 完成態＋URL 已清
 *  AC2: 鎖定生效——name readOnly、toggle disabled（點擊不改值）、下一步可按
 *  AC3: 非法參數（turn 不在 allowlist）→ 整組退回正常模式（不自動開精靈）
 *  AC4: prefers-reduced-motion → 跳過動畫直接完成態
 *  AC5: 播畢後關閉精靈再重開 → 直接完成態（不重播）
 *  AC6: 登入回跳保留 query（未登入開深連結 → login → 參數仍生效）
 *
 * 假設：frontend localhost:3000、backend localhost:8000、教師可自助 register。
 * 純前端功能——不需 LLM。
 */
import { test, expect, type Page } from '@playwright/test'
import { loginOrRegisterTeacher } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const STAMP = Date.now()

const TASK_NAME = '重新設計大賣場購物車'
const TASK_DESC = '打破購物車單純作為容納工具的限制'

const STUDY_QS =
  `study=1&name=${encodeURIComponent(TASK_NAME)}` +
  `&desc=${encodeURIComponent(TASK_DESC)}` +
  '&turn=cued&ai=medium&crew=3&timer=40'

const DONE_TEXT = '實驗條件已就緒'

async function expectAutofillDone(page: Page, timeout = 20_000): Promise<void> {
  await expect(page.getByText(DONE_TEXT)).toBeVisible({ timeout })
}

async function expectLockedValues(page: Page): Promise<void> {
  // 名稱（readOnly Input）
  const nameInput = page.locator(`input[value="${TASK_NAME}"]`)
  await expect(nameInput).toBeVisible()
  await expect(nameInput).toHaveAttribute('readonly', '')
  // 描述（readOnly textarea）
  await expect(page.locator('textarea').first()).toHaveValue(TASK_DESC)
  // 四個 toggle 的選中態（border-primary 樣式以 disabled+文字驗證）
  const cuedBtn = page.getByRole('button', { name: /點名/ })
  await expect(cuedBtn).toBeDisabled()
  const timer40 = page.getByRole('button', { name: /40 分/ })
  await expect(timer40).toBeDisabled()
}

test.describe('Phase 43 — study 深連結自動代填', () => {
  const teacher = {
    email: `p43_t_${STAMP}@mindcrew.test`,
    password: 'Phase43Test!',
    name: `T43 ${STAMP}`,
  }

  test.beforeAll(async () => {
    await loginOrRegisterTeacher(teacher.email, teacher.password, teacher.name)
  })

  test('AC1+AC2：深連結自動開精靈、代填播畢、鎖定、URL 已清', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects?${STUDY_QS}`, { waitUntil: 'networkidle' })

    // 精靈自動開啟＋動畫播畢
    await expect(page.getByText('1. 描述你的設計挑戰')).toBeVisible({ timeout: 10_000 })
    await expectAutofillDone(page)
    await expectLockedValues(page)

    // URL 參數已被即拆即清
    expect(page.url()).not.toContain('study=1')

    // AC2：點被鎖的「輪流」不會改變選擇（disabled 擋下）
    const rrBtn = page.getByRole('button', { name: /輪流/ })
    await expect(rrBtn).toBeDisabled()
    await rrBtn.click({ force: true }).catch(() => {})
    await expect(page.getByRole('button', { name: /點名/ })).toBeDisabled()

    // 下一步可按（動畫結束後）
    await expect(
      page.getByRole('button', { name: /下一步：找出你的設計對象/ }),
    ).toBeEnabled()
  })

  test('AC7（review fix）：開精靈當下受控欄位即鎖定，無開場可編輯空窗', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects?${STUDY_QS}`, { waitUntil: 'networkidle' })

    // 精靈一出現(brief 標題)就檢查——不等動畫播畢。修復前開場 sleep(600) 的 idle 前奏
    // 會讓 toggle 短暫可點;修復後從第一幀就 disabled/readOnly。
    await expect(page.getByText('1. 描述你的設計挑戰')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('button', { name: /點名/ })).toBeDisabled()
    await expect(page.getByRole('button', { name: /輪流/ })).toBeDisabled()
    await expect(page.locator('input[readonly]').first()).toBeVisible()
  })

  test('AC5：播畢後關閉重開 → 直接完成態不重播', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects?${STUDY_QS}`, { waitUntil: 'networkidle' })
    await expectAutofillDone(page)

    // Escape 關閉 → 重開
    await page.keyboard.press('Escape')
    await expect(page.getByText('1. 描述你的設計挑戰')).toHaveCount(0)
    await page
      .locator('button')
      .filter({ hasText: /(開新|建立新)?設計專案/ })
      .first()
      .click()

    // 直接完成態：2 秒內就緒（不重播 ~6 秒動畫）
    await expectAutofillDone(page, 2_000)
    await expectLockedValues(page)
  })

  test('AC3：非法參數整組退回正常模式', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    const badQs = STUDY_QS.replace('turn=cued', 'turn=bogus')
    await page.goto(`/projects?${badQs}`, { waitUntil: 'networkidle' })

    // 不自動開精靈、無 narration
    await page.waitForTimeout(1_500)
    await expect(page.getByText('1. 描述你的設計挑戰')).toHaveCount(0)
    await expect(page.getByText(DONE_TEXT)).toHaveCount(0)
  })

  test('AC6：未登入開深連結 → login 回跳保留參數', async ({ page }) => {
    await suppressFirstRunModals(page)
    // 未登入直接開深連結 → 被導去 /login
    await page.goto(`/projects?${STUDY_QS}`, { waitUntil: 'networkidle' })
    await page.waitForURL('**/login**', { timeout: 10_000 })

    await page.fill('input[autocomplete="username"]', teacher.email)
    await page.fill('input[type="password"]', teacher.password)
    await page.click('button[type="submit"]')

    // 回跳 /projects（含參數）→ 精靈自動開啟並完成代填
    await page.waitForURL('**/projects**', { timeout: 20_000 })
    await expect(page.getByText('1. 描述你的設計挑戰')).toBeVisible({ timeout: 10_000 })
    await expectAutofillDone(page)
  })
})

test.describe('Phase 43 — reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' } })

  test('AC4：reduced-motion 跳過動畫直接完成態', async ({ page }) => {
    const teacher = {
      email: `p43_rm_${STAMP}@mindcrew.test`,
      password: 'Phase43Test!',
      name: `T43rm ${STAMP}`,
    }
    await loginOrRegisterTeacher(teacher.email, teacher.password, teacher.name)
    await suppressFirstRunModals(page)
    await loginViaUi(page, teacher.email, teacher.password)
    await page.goto(`/projects?${STUDY_QS}`, { waitUntil: 'networkidle' })

    // 精靈開啟後 2 秒內即完成態（無 ~6 秒動畫）
    await expect(page.getByText('1. 描述你的設計挑戰')).toBeVisible({ timeout: 10_000 })
    await expectAutofillDone(page, 2_000)
    await expectLockedValues(page)
  })
})
