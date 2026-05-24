import { defineConfig, devices } from '@playwright/test'

/**
 * Phase 24 / 23 — Playwright test runner config。
 *
 * 範圍：只跑 `*.spec.ts`（純 standalone `.js` 腳本沿用既有 `node e2e/xxx.js` 路徑）。
 * 假設前後端 + sidecar 已在 localhost:3000 / 8000 / 4000 起好。
 */
export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
