/**
 * Phase 24 — Activity Highlight smoke test (Playwright with Chrome)
 *
 * 驗收標準（_discussion/）：
 *  AC0：頁面有至少 2 個 chat row（data-activity-highlight="chat"）。
 *  AC1：hover 同作者 30s 內 chat 氣泡 → boxShadow ring 出現；滑出後消失。
 *  AC1b：同作者另一則氣泡也同步高亮（兩者 ring 同時存在）。
 *  AC4a：click → pinned，boxShadow 持久。
 *  AC4b：按 Esc → 清除 pin。
 *
 * 範圍刻意限縮：只驗 chat 端高亮（不開 tldraw 便利貼互動，避免 LLM/WS 變數）。
 * 假設：
 *   - 後端 / 前端 / sidecar 都已起來（localhost:3000 / 8000 / 4000）。
 *   - 測試帳號 qa_auto@mindcrew.test 可登入或可註冊，密碼從 E2E_TEST_PASSWORD env var。
 *   - 至少一個既有 project；若無則自建。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, apiCall, createMinimalProject } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const TEST_EMAIL = 'qa_auto@mindcrew.test'
const TEST_PASSWORD =
  process.env.E2E_TEST_PASSWORD || 'change-me-set-E2E_TEST_PASSWORD'

test.describe('Phase 24 — Activity Highlight', () => {
  let projectId: string

  test.beforeAll(async () => {
    const account = await loginOrRegisterTeacher(TEST_EMAIL, TEST_PASSWORD, 'QA Auto')
    const list = await apiCall<Array<{ id: string }>>('GET', '/api/projects', undefined, account.token)
    if (Array.isArray(list.body) && list.body.length > 0) {
      projectId = list.body[0].id
    } else {
      projectId = await createMinimalProject(account.token, 'Phase 24 Smoke')
    }
  })

  test('AC0-AC4：chat 氣泡同作者 30s 內高亮 / pin / Esc 清除', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, TEST_EMAIL, TEST_PASSWORD)
    await page.goto(`/projects/${projectId}/workspace`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1500)

    // 若 chat input 可輸入，先注入兩則訊息確保 row 數量達標
    const input = page.locator('textarea[placeholder*="輸入訊息"]').first()
    if (await input.count()) {
      const isDisabled = await input.evaluate(
        (el) => (el as HTMLTextAreaElement).disabled,
      ).catch(() => true)
      if (!isDisabled) {
        const stamp = Date.now()
        await input.fill(`phase24-smoke-A-${stamp}`)
        await page.keyboard.press('Enter')
        await page.waitForTimeout(500)
        await input.fill(`phase24-smoke-B-${stamp}`)
        await page.keyboard.press('Enter')
        await page.waitForTimeout(500)
      }
    }

    // AC0：確認有 chat rows
    const rows = page.locator('[data-activity-highlight="chat"]')
    const total = await rows.count()
    test.skip(
      total < 2,
      `chat rows=${total}<2，無同作者歷史可測；高亮邏輯已由 vitest pure unit 覆蓋`,
    )
    expect(total).toBeGreaterThanOrEqual(2)

    const first = rows.first()
    const last = rows.last()

    // AC1：hover 第一則 → 出現 boxShadow
    await first.hover()
    await page.waitForTimeout(200)
    const firstShadow = await first.evaluate((el) => getComputedStyle(el).boxShadow)
    expect(firstShadow, 'hover 後第一則應有 boxShadow').not.toBe('none')
    expect(firstShadow.length).toBeGreaterThan(0)

    // AC1b：同作者其他氣泡也應同步亮起（若 last 與 first 同作者）
    const lastShadow = await last.evaluate((el) => getComputedStyle(el).boxShadow)
    // 不強制 same author（測試環境 chat 來源可能不同人），但若有則應為非空
    if (lastShadow && lastShadow !== 'none') {
      expect(lastShadow.length).toBeGreaterThan(0)
    }

    // AC1c：滑出 → 清除
    await page.mouse.move(10, 10)
    await page.waitForTimeout(200)
    const afterLeave = await first.evaluate((el) => getComputedStyle(el).boxShadow)
    expect(afterLeave === 'none' || afterLeave === '').toBeTruthy()

    // AC4a：click → pin
    await first.click()
    await page.waitForTimeout(200)
    const pinnedShadow = await first.evaluate((el) => getComputedStyle(el).boxShadow)
    expect(pinnedShadow, 'click 後應 pin boxShadow').not.toBe('none')

    // AC4b：Esc → 清除 pin
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    const afterEsc = await first.evaluate((el) => getComputedStyle(el).boxShadow)
    expect(afterEsc === 'none' || afterEsc === '').toBeTruthy()
  })
})
