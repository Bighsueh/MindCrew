/**
 * Phase 23 / 24 e2e — UI 登入 helper。
 *
 * 從登入頁出發，輸入 email/password → 等跳轉到 /projects。
 */
import type { Page } from '@playwright/test'

export async function loginViaUi(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login', { waitUntil: 'networkidle' })
  // Login input is type="text" (accepts both email and admin username).
  await page.fill('input[autocomplete="username"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/projects', { timeout: 20_000 })
}

/**
 * 預先在 localStorage 寫入 mindcrew.firstrun.* 旗標，
 * 避免 workspace / lobby 開新使用者時跳出 OnboardingModal / tour 擋住 e2e 互動。
 */
export async function suppressFirstRunModals(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const KEYS = [
      'mindcrew.firstrun.workspace-tour',
      'mindcrew.firstrun.projects-tour',
      'mindcrew.firstrun.teacher-dashboard-tour',
    ]
    KEYS.forEach((k) => {
      try {
        window.localStorage.setItem(k, '1')
      } catch {
        /* localStorage 不可用時靜默 */
      }
    })
    // 任何 onboarding-modal-* 旗標：用 Proxy 攔截 getItem 對未設過的 onboarding key 回 '1'
    const originalGet = window.localStorage.getItem.bind(window.localStorage)
    window.localStorage.getItem = function (key: string): string | null {
      if (key.startsWith('mindcrew.firstrun.onboarding-modal-')) return '1'
      return originalGet(key)
    }
  })
}
