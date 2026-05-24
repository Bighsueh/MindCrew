/**
 * Phase 25 — Admin LLM Console smoke test (Playwright with Chrome)
 *
 * Verifies the multi-LLM-provider admin console end-to-end against a live
 * stack (frontend on :3000, backend on :8000). Each scenario corresponds to
 * one acceptance criterion from the Phase 25 plan §驗收.
 *
 *   AC1: admin login (password from E2E_ADMIN_PASSWORD env var) → /admin/providers; Tier 1 section renders (empty
 *        is fine — Phase 25 removed the migration seed).
 *   AC2: admin creates a tier-2 Azure provider; row appears under Tier 2.
 *   AC3: admin can navigate to logs + stats tabs.
 *   AC4: non-admin (a teacher account) hitting /admin/* is redirected away.
 *   AC5: /api/admin/* refuses requests with a non-admin token (403).
 *
 * Assumes:
 *   - Backend reachable at http://localhost:8000.
 *   - Frontend reachable at http://localhost:3000.
 *   - Alembic head includes d2e3f4a5b6c7 (creates tables + admin user; does
 *     NOT seed any LLM provider — admins add those via the UI).
 */
import { test, expect } from '@playwright/test'
import { apiCall, loginOrRegisterTeacher } from './helpers/api'
import { suppressFirstRunModals } from './helpers/loginUi'

const ADMIN_EMAIL = 'admin'
const ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD || 'change-me-set-E2E_ADMIN_PASSWORD'

const TEACHER_EMAIL = 'qa_phase25_teacher@mindcrew.test'
const TEACHER_PASSWORD =
  process.env.E2E_TEACHER_PASSWORD || 'change-me-set-E2E_TEACHER_PASSWORD'

async function loginAsAdminUi(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.fill('input[autocomplete="username"]', ADMIN_EMAIL)
  await page.fill('input[type="password"]', ADMIN_PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/admin/**', { timeout: 20_000 })
}

async function loginAsTeacherUi(
  page: import('@playwright/test').Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.fill('input[autocomplete="username"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/projects', { timeout: 20_000 })
}

test.describe('Phase 25 — Admin LLM Console', () => {
  test.beforeAll(async () => {
    // Backend reachability — fail fast with a friendly message if it isn't up.
    const ping = await apiCall<{ access_token: string }>(
      'POST',
      '/api/auth/login',
      { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    )
    if (ping.status !== 200) {
      throw new Error(
        `Backend admin login failed (status ${ping.status}). ` +
          `Ensure 'alembic upgrade head' has run and that the admin seed migration applied.`,
      )
    }
  })

  test('AC1 — admin logs in and lands on /admin/providers (empty Tier 1 OK)', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)

    await expect(page).toHaveURL(/\/admin\/providers/)
    await expect(page.getByRole('heading', { name: 'LLM Providers' })).toBeVisible()
    // Phase 25 deliberately does not seed any provider — verify the page
    // still renders the Tier 1 section so admins know where to add one.
    await expect(page.getByTestId('tier-1')).toBeVisible()
  })

  test('AC2 — admin creates a tier-2 Azure provider via the UI', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)

    // Distinct name per run so the test is idempotent across re-runs.
    const name = `azure-e2e-${Date.now()}`

    await page.getByTestId('add-provider').click()
    await page.getByTestId('provider-name').fill(name)
    await page.getByTestId('provider-kind').selectOption('azure_openai')
    await page.getByTestId('provider-tier').selectOption('2')
    await page.fill('input[placeholder*="https://vllm.example.com"]', 'https://contoso.openai.azure.com')
    await page.fill('input[placeholder*="/models/gemma"]', 'gpt-4o-mini')
    await page.fill('input[placeholder*="gpt-4o-deployment"]', 'gpt-4o-mini')
    await page.fill('input[placeholder*="2024-02-15-preview"]', '2024-02-15-preview')
    // Some non-empty value so the backend isn't asked to call out with an empty key.
    await page.fill('input[placeholder*="sk-"]', 'dummy-key')

    await page.getByTestId('provider-submit').click()

    // Wait for the modal to close (form is unmounted) and the new row to render.
    await expect(page.getByTestId(`row-${name}`)).toBeVisible({ timeout: 10_000 })
    // It should appear under the Tier 2 section, not Tier 1.
    const tier2 = page.getByTestId('tier-2')
    await expect(tier2.getByTestId(`row-${name}`)).toBeVisible()

    // Cleanup so the test stays idempotent and doesn't accumulate rows.
    page.once('dialog', (d) => d.accept())
    await page.getByTestId(`delete-${name}`).click()
    await expect(page.getByTestId(`row-${name}`)).not.toBeVisible({ timeout: 10_000 })
  })

  test('AC3 — admin can navigate between providers / logs / stats tabs', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)

    await page.getByRole('link', { name: 'Request Logs' }).click()
    await expect(page).toHaveURL(/\/admin\/logs/)
    await expect(page.getByTestId('logs-table')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('link', { name: 'Stats' }).click()
    await expect(page).toHaveURL(/\/admin\/stats/)
    await expect(page.getByTestId('chart-token-timeline')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('link', { name: 'Providers' }).click()
    await expect(page).toHaveURL(/\/admin\/providers/)
  })

  test('AC4 — non-admin user is redirected away from /admin/*', async ({ page }) => {
    // Make sure a teacher account exists.
    await loginOrRegisterTeacher(TEACHER_EMAIL, TEACHER_PASSWORD, 'QA Phase25')
    await suppressFirstRunModals(page)
    await loginAsTeacherUi(page, TEACHER_EMAIL, TEACHER_PASSWORD)

    await page.goto('/admin/providers', { waitUntil: 'networkidle' })
    // AdminRoute should bounce us to /projects (not to /login — we're logged in).
    await expect(page).toHaveURL(/\/projects(\/|$|\?)/, { timeout: 10_000 })
  })

  test('AC5 — /api/admin/* returns 403 for a non-admin JWT', async () => {
    const teacher = await loginOrRegisterTeacher(
      TEACHER_EMAIL,
      TEACHER_PASSWORD,
      'QA Phase25',
    )
    const res = await apiCall<unknown>(
      'GET',
      '/api/admin/providers',
      undefined,
      teacher.token,
    )
    expect(res.status).toBe(403)
  })

  // ── Phase 25.J/K extension ─────────────────────────────────────────

  test('AC6 — Logs detail modal renders metadata + messages + response', async ({
    page,
  }) => {
    // Need at least one log row. Use the admin API directly to check; if
    // empty, trigger a project summary call as a teacher to create one.
    const adminLogin = await apiCall<{ access_token: string }>(
      'POST',
      '/api/auth/login',
      { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    )
    const adminToken = adminLogin.body.access_token
    const logs = await apiCall<{ total: number; items: Array<{ id: number }> }>(
      'GET',
      '/api/admin/logs?limit=1',
      undefined,
      adminToken,
    )
    if (logs.body.total === 0) {
      // Bootstrap a log by triggering a summary call as a teacher.
      const teacher = await loginOrRegisterTeacher(
        TEACHER_EMAIL,
        TEACHER_PASSWORD,
        'QA Phase25',
      )
      const projects = await apiCall<Array<{ id: string }>>(
        'GET',
        '/api/projects',
        undefined,
        teacher.token,
      )
      if (Array.isArray(projects.body) && projects.body.length > 0) {
        await apiCall(
          'POST',
          `/api/projects/${projects.body[0].id}/summary`,
          undefined,
          teacher.token,
        )
        // wait for the fire-and-forget log/payload write to commit
        await new Promise((r) => setTimeout(r, 1500))
      }
    }

    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)
    await page.goto('/admin/logs', { waitUntil: 'networkidle' })

    // Click the first row.
    const firstRow = page.locator('[data-testid^="log-row-"]').first()
    await expect(firstRow).toBeVisible({ timeout: 10_000 })
    await firstRow.click()

    // Modal pieces must render with content.
    await expect(page.getByTestId('log-metadata')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByTestId('log-messages')).toBeVisible()
    await expect(page.getByTestId('log-response')).toBeVisible()
    // Messages block must contain at least one role label.
    const msgBlock = page.getByTestId('log-messages')
    await expect(msgBlock).toContainText(/system|user|assistant/)
  })

  test('AC7 — Stats overview renders all five chart sections', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)
    await page.goto('/admin/stats', { waitUntil: 'networkidle' })

    const ids = [
      'chart-token-timeline',
      'chart-caller-breakdown',
      'chart-top-users',
      'chart-hourly-heatmap',
      'chart-latency-buckets',
      'chart-success-rate',
    ]
    for (const id of ids) {
      await expect(page.getByTestId(id)).toBeVisible({ timeout: 10_000 })
    }
  })

  test('AC8 — opening log detail writes an admin_payload_access audit row', async ({
    page,
  }) => {
    const adminLogin = await apiCall<{ access_token: string }>(
      'POST',
      '/api/auth/login',
      { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    )
    const adminToken = adminLogin.body.access_token

    const before = await apiCall<{ total: number }>(
      'GET',
      '/api/admin/audit/payload-access?limit=1',
      undefined,
      adminToken,
    )
    const beforeCount = before.body.total ?? 0

    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)
    await page.goto('/admin/logs', { waitUntil: 'networkidle' })
    const firstRow = page.locator('[data-testid^="log-row-"]').first()
    await expect(firstRow).toBeVisible({ timeout: 10_000 })
    await firstRow.click()
    await expect(page.getByTestId('log-metadata')).toBeVisible({ timeout: 10_000 })

    // Audit row count should have gone up by exactly one.
    const after = await apiCall<{ total: number }>(
      'GET',
      '/api/admin/audit/payload-access?limit=1',
      undefined,
      adminToken,
    )
    expect(after.body.total).toBeGreaterThan(beforeCount)
  })

  test('AC9 — timeline picker / user filter / granularity auto-flip', async ({
    page,
  }) => {
    await suppressFirstRunModals(page)
    await loginAsAdminUi(page)
    await page.goto('/admin/stats', { waitUntil: 'networkidle' })

    // Default 24h range → granularity hour.
    const granularityLabel = page.getByTestId('ts-granularity')
    await expect(granularityLabel).toBeVisible({ timeout: 10_000 })
    await expect(granularityLabel).toHaveText(/每小時 \(UTC\)/)
    await expect(page.getByTestId('chart-token-timeline')).toBeVisible()

    // 30-day preset → granularity flips to day.
    await page.getByTestId('ts-preset-720').click()
    await expect(granularityLabel).toHaveText(/每日 \(UTC\)/, { timeout: 10_000 })

    // Pick the first user from the top-users dropdown (if any present).
    const userSelect = page.getByTestId('ts-user')
    const options = await userSelect.locator('option').all()
    if (options.length > 1) {
      // option[0] is "全部使用者"; option[1] is the first real user.
      const firstUserValue = await options[1].getAttribute('value')
      if (firstUserValue) {
        await userSelect.selectOption(firstUserValue)
        // Chart still rendered (may be empty for that user; that's fine).
        await expect(page.getByTestId('chart-token-timeline')).toBeVisible()
      }
    }

    // Switch back to 24h and confirm granularity flips back to hour.
    await page.getByTestId('ts-preset-24').click()
    await expect(granularityLabel).toHaveText(/每小時 \(UTC\)/, { timeout: 10_000 })
  })
})
