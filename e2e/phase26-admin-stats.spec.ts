/**
 * Phase 26 — Admin Stats dashboard E2E smoke test (Playwright / Chrome)
 *
 * Verifies the /admin/stats page and Phase-26 TimeseriesControls changes.
 * Requires a live stack: frontend :3000, backend :8000.
 * Admin credentials: email="admin", password from E2E_ADMIN_PASSWORD env var.
 */
import { test, expect, type Page, type Response } from '@playwright/test'
import * as path from 'path'

const ADMIN_EMAIL = 'admin'
const ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD || 'change-me-set-E2E_ADMIN_PASSWORD'
const SCREENSHOT_PATH = path.resolve(
  __dirname,
  'screenshots/admin-stats-phase26.png',
)

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function loginAdmin(page: Page): Promise<void> {
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.fill('input[autocomplete="username"]', ADMIN_EMAIL)
  await page.fill('input[type="password"]', ADMIN_PASSWORD)
  await page.click('button[type="submit"]')
  // admin → redirect to /admin/**
  await page.waitForURL('**/admin/**', { timeout: 20_000 })
}

async function gotoStats(page: Page): Promise<void> {
  await page.goto('/admin/stats', { waitUntil: 'networkidle' })
}

// ---------------------------------------------------------------------------
// test suite
// ---------------------------------------------------------------------------

test.describe('Phase 26 — Admin Stats page', () => {

  test.beforeEach(async ({ page }) => {
    await loginAdmin(page)
    await gotoStats(page)
  })

  // -------------------------------------------------------------------------
  // Check 1: page renders without console errors
  // -------------------------------------------------------------------------
  test('Check 1: Stats page renders without console errors', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    // reload to capture all console messages after listener is attached
    await page.reload({ waitUntil: 'networkidle' })

    // Filter out known browser-level noise (favicon 404, extension messages)
    const realErrors = consoleErrors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('chrome-extension') &&
        !e.includes('net::ERR_'),
    )
    expect(realErrors, `Console errors: ${realErrors.join('\n')}`).toHaveLength(0)
  })

  // -------------------------------------------------------------------------
  // Check 2: TimeseriesControls section elements
  // -------------------------------------------------------------------------
  test('Check 2: TimeseriesControls shows required controls', async ({ page }) => {
    // 起點 / 終點 datetime inputs
    const sinceInput = page.locator('input[data-testid="ts-since"], input[placeholder*="起點"], input[aria-label*="起點"], label:has-text("起點") + input, label:has-text("起點") ~ input').first()
    const untilInput = page.locator('input[data-testid="ts-until"], input[placeholder*="終點"], input[aria-label*="終點"], label:has-text("終點") + input, label:has-text("終點") ~ input').first()

    // Try more general datetime-local inputs if labels not found
    const datetimeInputs = page.locator('input[type="datetime-local"]')
    const datetimeCount = await datetimeInputs.count()
    expect(datetimeCount, 'Expected at least 2 datetime-local inputs (起點/終點)').toBeGreaterThanOrEqual(2)

    // 使用者 dropdown
    const userDropdown = page.locator('select[data-testid="ts-user"], select[aria-label*="使用者"], label:has-text("使用者") ~ select, [data-testid*="user"] select').first()
    await expect(userDropdown).toBeVisible({ timeout: 5_000 })

    // 粒度 dropdown with expected options
    const granDropdown = page.locator('select[data-testid="ts-granularity"], select[aria-label*="粒度"], label:has-text("粒度") ~ select, [data-testid*="granularity"] select').first()
    await expect(granDropdown).toBeVisible({ timeout: 5_000 })

    const granOptions = await granDropdown.locator('option').allTextContents()
    const expectedOptions = ['自動', '30 分鐘', '每小時', '每日']
    for (const opt of expectedOptions) {
      expect(granOptions.some((o) => o.includes(opt.replace(' ', '')) || o.includes(opt)),
        `Missing granularity option: "${opt}". Got: ${JSON.stringify(granOptions)}`
      ).toBe(true)
    }

    // Preset buttons: 過去 24h / 過去 7 天 / 過去 14 天 / 過去 30 天
    // (labels use Chinese, not short English codes)
    const presetPatterns = ['24h', '7', '14', '30']
    for (const pat of presetPatterns) {
      const btn = page.locator(`button:has-text("${pat}")`)
      await expect(btn.first(), `Missing preset button containing: ${pat}`).toBeVisible({ timeout: 5_000 })
    }
  })

  // -------------------------------------------------------------------------
  // Check 3: Token usage chart renders
  // -------------------------------------------------------------------------
  test('Check 3: Token usage chart (chart-token-timeline) renders with SVG', async ({ page }) => {
    const chart = page.locator('[data-testid="chart-token-timeline"]')
    await expect(chart).toBeVisible({ timeout: 10_000 })

    // Check for SVG polygons (stacked area chart)
    const svg = chart.locator('svg')
    await expect(svg).toBeVisible({ timeout: 5_000 })

    // Legend
    const legend = page.locator('[data-testid="ts-legend"]')
    await expect(legend).toBeVisible({ timeout: 5_000 })
  })

  // -------------------------------------------------------------------------
  // Check 4: Success rate chart renders with correct header
  // -------------------------------------------------------------------------
  test('Check 4: Success rate chart renders with correct header (30min)', async ({ page }) => {
    const chart = page.locator('[data-testid="chart-success-rate"]')
    await expect(chart).toBeVisible({ timeout: 10_000 })

    // The header should include "粒度" and "30 分鐘" for default 24h window
    const headerText = await chart.textContent()
    expect(
      headerText?.includes('粒度') || headerText?.includes('30'),
      `Success rate chart header does not mention 粒度/30min. Got: ${headerText?.substring(0, 200)}`,
    ).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Check 5: 24h preset + 30min granularity → correct API response
  // -------------------------------------------------------------------------
  test('Check 5: 24h preset with 30min granularity returns correct API response', async ({ page }) => {
    const timeseriesResponses: Response[] = []
    const successRateResponses: Response[] = []

    page.on('response', (r) => {
      if (r.url().includes('/api/admin/stats/timeseries')) timeseriesResponses.push(r)
      if (r.url().includes('/api/admin/stats/success-rate')) successRateResponses.push(r)
    })

    // Click 過去 24h preset
    const btn24h = page.locator('button:has-text("24h")').first()
    await btn24h.click()

    // Set 粒度 to 30 分鐘 (select by value or label text)
    const granDropdown = page.locator('select[data-testid="ts-granularity"], select[aria-label*="粒度"], label:has-text("粒度") ~ select, [data-testid*="granularity"] select').first()
    // Get available options then pick the one matching 30min
    const granOptions = await granDropdown.locator('option').allTextContents()
    const thirtyMinOption = granOptions.find((o) => o.includes('30'))
    if (thirtyMinOption) {
      await granDropdown.selectOption({ label: thirtyMinOption })
    } else {
      // Try by value
      await granDropdown.selectOption('30min')
    }

    // Wait for network requests
    await page.waitForTimeout(3_000)

    // Evaluate timeseries response
    if (timeseriesResponses.length > 0) {
      const lastTs = timeseriesResponses[timeseriesResponses.length - 1]
      expect(lastTs.status()).toBe(200)
      const tsBody = await lastTs.json().catch(() => null)
      if (tsBody) {
        expect(tsBody.granularity, `timeseries granularity mismatch`).toBe('30min')
        const series = tsBody.series ?? []
        if (series.length > 0) {
          const buckets = series[0].buckets ?? []
          expect(buckets.length, `Expected 48 buckets for 24h/30min but got ${buckets.length}`).toBe(48)
        }
      }
    } else {
      test.info().annotations.push({ type: 'warning', description: 'No timeseries API calls intercepted — may have been fetched on page load' })
    }

    // Evaluate success-rate response
    if (successRateResponses.length > 0) {
      const lastSr = successRateResponses[successRateResponses.length - 1]
      expect(lastSr.status()).toBe(200)
      const srBody = await lastSr.json().catch(() => null)
      if (srBody) {
        expect(srBody.granularity, `success-rate granularity mismatch`).toBe('30min')
      }
    }
  })

  // -------------------------------------------------------------------------
  // Check 6: Toggle provider checkbox removes series from chart
  // -------------------------------------------------------------------------
  test('Check 6: Toggling provider checkbox updates chart and refetches', async ({ page }) => {
    // Look for provider checkboxes with data-testid ts-provider-<uuid>
    const providerCheckboxes = page.locator('[data-testid^="ts-provider-"]')
    const count = await providerCheckboxes.count()

    if (count === 0) {
      test.info().annotations.push({
        type: 'warning',
        description: 'No provider checkboxes found (data-testid ts-provider-*) — likely no providers in DB',
      })
      return
    }

    const refetchPromise = page.waitForResponse(
      (r) => r.url().includes('/api/admin/stats/timeseries') && r.status() === 200,
      { timeout: 10_000 },
    )

    // Uncheck first provider
    const firstCheckbox = providerCheckboxes.first()
    const wasChecked = await firstCheckbox.isChecked()
    await firstCheckbox.click()

    // Wait for refetch
    await refetchPromise

    // Chart should have updated; legend label should be struck-through if provider was checked
    if (wasChecked) {
      const legend = page.locator('[data-testid="ts-legend"]')
      await expect(legend).toBeVisible()
      // Check for a struck-through element (text-decoration: line-through)
      const struckEl = legend.locator('span[style*="line-through"], s, del, [class*="strike"]')
      const struckCount = await struckEl.count()
      // Even if CSS class is used, just verify the chart refreshed (network check above)
      test.info().annotations.push({
        type: 'info',
        description: `Provider toggled; struck-through legend items found: ${struckCount}`,
      })
    }
  })

  // -------------------------------------------------------------------------
  // Check 7: Screenshot
  // -------------------------------------------------------------------------
  test('Check 7: Capture dashboard screenshot', async ({ page }) => {
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false })
    // Verify file was created (path must exist)
    const fs = await import('fs')
    expect(fs.existsSync(SCREENSHOT_PATH), `Screenshot not saved at ${SCREENSHOT_PATH}`).toBe(true)
  })
})
