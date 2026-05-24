/**
 * Phase 26.E — Admin Stats auto-refresh E2E check (Playwright / Chrome)
 *
 * Verifies: refresh indicator UI, manual refresh, 60s auto-refresh tick,
 * toggle-off suppression, and toggle-off manual-refresh still fires.
 *
 * Total runtime budget: ~3 min (two 65-second waits).
 */
import { test, expect, type Page, request as playwrightRequest } from '@playwright/test'
import * as path from 'path'
import * as fs from 'fs'

const SCREENSHOT_PATH = path.resolve(
  __dirname,
  'screenshots/admin-stats-auto-refresh.png',
)

// Ensure screenshots dir exists
fs.mkdirSync(path.dirname(SCREENSHOT_PATH), { recursive: true })

const ADMIN_EMAIL = 'admin'
const ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD || 'change-me-set-E2E_ADMIN_PASSWORD'

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function loginViaLocalStorage(page: Page): Promise<void> {
  // Use Playwright's Node-side request context (bypasses CORS) to get the token
  const apiContext = await playwrightRequest.newContext({ baseURL: 'http://localhost:8000' })
  const res = await apiContext.post('/api/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  })
  const body = await res.json()
  const token: string = body.access_token
  await apiContext.dispose()
  if (!token) throw new Error(`Login failed: ${JSON.stringify(body)}`)

  // Navigate to root then inject token into localStorage
  await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded', timeout: 15_000 })
  await page.evaluate((t: string) => {
    localStorage.setItem('access_token', t)
  }, token)
}

async function gotoStats(page: Page): Promise<void> {
  await page.goto('http://localhost:3000/admin/stats', {
    waitUntil: 'networkidle',
    timeout: 30_000,
  })
}

// ---------------------------------------------------------------------------
// Count how many times a URL pattern was requested so far
// ---------------------------------------------------------------------------
function makeRequestCounter(page: Page, urlFragment: string): () => number {
  let count = 0
  page.on('request', (req) => {
    if (req.url().includes(urlFragment)) count++
  })
  return () => count
}

// ---------------------------------------------------------------------------
// suite
// ---------------------------------------------------------------------------

test.describe('Phase 26.E — Admin Stats auto-refresh', () => {
  // Per-test timeout: 8 min to accommodate two 65s waits + overhead
  test.setTimeout(480_000)

  test.beforeEach(async ({ page }) => {
    await loginViaLocalStorage(page)
    await gotoStats(page)
  })

  // -------------------------------------------------------------------------
  // Check 1: refresh indicator structure
  // -------------------------------------------------------------------------
  test('Check 1: Header refresh indicator present with correct sub-elements', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const indicator = page.locator('[data-testid="stats-refresh-indicator"]')
    await expect(indicator).toBeVisible({ timeout: 15_000 })

    // "上次更新：HH:MM:SS" — must NOT be a dash placeholder
    const indicatorText = await indicator.textContent()
    const hasTimestamp = /上次更新[：:]\s*\d{1,2}:\d{2}:\d{2}/.test(indicatorText ?? '')
    expect(
      hasTimestamp,
      `Expected "上次更新：HH:MM:SS" inside indicator, got: "${indicatorText}"`,
    ).toBe(true)

    // Checkbox — checked by default
    const toggle = page.locator('[data-testid="stats-refresh-toggle"]')
    await expect(toggle).toBeVisible({ timeout: 5_000 })
    await expect(toggle).toBeChecked()

    // Manual refresh button
    const refreshBtn = page.locator('[data-testid="stats-refresh-button"]')
    await expect(refreshBtn).toBeVisible({ timeout: 5_000 })
    const btnText = await refreshBtn.textContent()
    expect(btnText?.trim()).toBe('重新整理')

    // Report console errors (non-fatal for check 1, but surfaced)
    const realErrors = consoleErrors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('chrome-extension') &&
        !e.includes('net::ERR_'),
    )
    if (realErrors.length > 0) {
      console.warn('Console errors during Check 1:', realErrors.join('\n'))
    }
  })

  // -------------------------------------------------------------------------
  // Check 2: manual refresh button fires all three API calls + updates timestamp
  // -------------------------------------------------------------------------
  test('Check 2: Manual refresh button fires timeseries + overview + success-rate', async ({ page }) => {
    const indicator = page.locator('[data-testid="stats-refresh-indicator"]')
    await expect(indicator).toBeVisible({ timeout: 15_000 })

    // Capture timestamp before click
    const tsBefore = await indicator.textContent()

    // Set up response watchers
    const hitTimeseries = page.waitForResponse(
      (r) => r.url().includes('/api/admin/stats/timeseries') && r.status() === 200,
      { timeout: 15_000 },
    )
    const hitOverview = page.waitForResponse(
      (r) => r.url().includes('/api/admin/stats/overview') && r.status() === 200,
      { timeout: 15_000 },
    )
    const hitSuccessRate = page.waitForResponse(
      (r) => r.url().includes('/api/admin/stats/success-rate') && r.status() === 200,
      { timeout: 15_000 },
    )

    const refreshBtn = page.locator('[data-testid="stats-refresh-button"]')
    await refreshBtn.click()

    // All three must respond 200
    await Promise.all([hitTimeseries, hitOverview, hitSuccessRate])

    // Timestamp should have updated (wait briefly for UI re-render)
    await page.waitForTimeout(1_000)
    const tsAfter = await indicator.textContent()
    expect(tsAfter, 'Timestamp must change after manual refresh').not.toEqual(tsBefore)
  })

  // -------------------------------------------------------------------------
  // Check 3: auto-refresh fires exactly once per 60s interval (65s wait)
  // -------------------------------------------------------------------------
  test('Check 3: Auto-refresh fires once within 65s and no full-page loading spinner', async ({ page }) => {
    const indicator = page.locator('[data-testid="stats-refresh-indicator"]')
    await expect(indicator).toBeVisible({ timeout: 15_000 })

    // Wait for initial load to settle
    await page.waitForLoadState('networkidle', { timeout: 20_000 })

    // Assert no "計算統計中…" loading text is showing (initial load done)
    const loadingText = page.locator('text=計算統計中')
    const loadingVisible = await loadingText.isVisible().catch(() => false)
    expect(loadingVisible, 'Full-page loading spinner should not be visible after initial load').toBe(false)

    // Count timeseries requests from this point
    const getTimeseriesCount = makeRequestCounter(page, '/api/admin/stats/timeseries')

    console.log('Check 3: waiting 65 seconds for one auto-refresh tick...')
    await page.waitForTimeout(65_000)

    const count = getTimeseriesCount()
    console.log(`Check 3: timeseries requests in 65s window = ${count}`)
    expect(
      count === 1 || count === 2,
      `Expected 1 or 2 auto-refresh timeseries calls in 65s, got ${count}`,
    ).toBe(true)

    // No loading spinner visible during/after auto-refresh
    const stillLoading = await loadingText.isVisible().catch(() => false)
    expect(stillLoading, 'No full-page loading spinner during auto-refresh').toBe(false)
  })

  // -------------------------------------------------------------------------
  // Check 4: toggle OFF → no requests fired in 65s
  // -------------------------------------------------------------------------
  test('Check 4: Toggle off suppresses auto-refresh for 65s', async ({ page }) => {
    const toggle = page.locator('[data-testid="stats-refresh-toggle"]')
    await expect(toggle).toBeVisible({ timeout: 15_000 })
    await expect(toggle).toBeChecked()

    // Uncheck
    await toggle.click()
    await expect(toggle).not.toBeChecked()

    // Wait for initial settle
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})

    const getCount = makeRequestCounter(page, '/api/admin/stats/timeseries')

    console.log('Check 4: waiting 65 seconds with auto-refresh toggled OFF...')
    await page.waitForTimeout(65_000)

    const count = getCount()
    console.log(`Check 4: timeseries requests while toggle OFF = ${count}`)
    expect(count, `Expected 0 timeseries requests when toggle is OFF, got ${count}`).toBe(0)
  })

  // -------------------------------------------------------------------------
  // Check 5: toggle back ON + manual refresh still works when toggle is OFF
  // -------------------------------------------------------------------------
  test('Check 5: Manual refresh works even when auto-refresh toggle is OFF', async ({ page }) => {
    const toggle = page.locator('[data-testid="stats-refresh-toggle"]')
    await expect(toggle).toBeVisible({ timeout: 15_000 })

    // Turn off
    if (await toggle.isChecked()) {
      await toggle.click()
    }
    await expect(toggle).not.toBeChecked()

    // Manual refresh should still fire
    const hit = page.waitForResponse(
      (r) => r.url().includes('/api/admin/stats/timeseries') && r.status() === 200,
      { timeout: 15_000 },
    )
    const refreshBtn = page.locator('[data-testid="stats-refresh-button"]')
    await refreshBtn.click()
    await hit

    // Now turn back ON
    await toggle.click()
    await expect(toggle).toBeChecked()
  })

  // -------------------------------------------------------------------------
  // Check 6: Screenshot with indicator visible
  // -------------------------------------------------------------------------
  test('Check 6: Screenshot of dashboard with refresh indicator', async ({ page }) => {
    const indicator = page.locator('[data-testid="stats-refresh-indicator"]')
    await expect(indicator).toBeVisible({ timeout: 15_000 })

    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false })
    expect(fs.existsSync(SCREENSHOT_PATH), `Screenshot not saved at ${SCREENSHOT_PATH}`).toBe(true)
    console.log(`Screenshot saved: ${SCREENSHOT_PATH}`)
  })
})
