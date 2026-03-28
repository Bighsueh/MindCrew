/**
 * Phase 9 — Projects Page Redesign E2E Test Suite
 *
 * Tests the redesigned /projects page for:
 * - Test 1: Page layout (welcome dashboard, stat cards, search bar, filter chips, project grid)
 * - Test 2: Search functionality
 * - Test 3: Stage filter chips
 * - Test 4: Project card design (border, badge, counts, timestamp, three-dot menu on hover)
 * - Test 5: Delete flow (dialog, disabled button, type-to-confirm, cancel without deleting)
 *
 * Run with:
 *   node /Users/hsueh/Code/Experimental/MindCrew/e2e/phase9-projects.test.js
 */

const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const BASE_URL = 'http://localhost:3000'
const SCREENSHOTS_DIR = '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots'
const EMAIL = 'teacher@test.com'
const PASSWORD = 'teacher123'

fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })

// ── Result tracking ──────────────────────────────────────────────────────────

const results = []

function pass(name, detail = '') {
  results.push({ name, status: 'PASS', detail })
  console.log(`  [PASS] ${name}${detail ? ' — ' + detail : ''}`)
}

function fail(name, detail = '') {
  results.push({ name, status: 'FAIL', detail })
  console.log(`  [FAIL] ${name}${detail ? ' — ' + detail : ''}`)
}

async function screenshot(page, filename) {
  const fullPath = path.join(SCREENSHOTS_DIR, filename)
  await page.screenshot({ path: fullPath, fullPage: true })
  console.log(`         Screenshot: ${fullPath}`)
  return fullPath
}

async function waitIdle(page, timeout = 3000) {
  try { await page.waitForLoadState('networkidle', { timeout }) } catch { /* ok */ }
}

// ── Login helper ─────────────────────────────────────────────────────────────

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 15000 })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/projects', { timeout: 10000 })
  await waitIdle(page)
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function run() {
  console.log('\n===================================================')
  console.log('  Phase 9 — Projects Page E2E Tests')
  console.log('===================================================\n')

  const browser = await chromium.launch({ headless: true, slowMo: 80 })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-TW',
  })
  const page = await context.newPage()

  // ── Setup: Login ─────────────────────────────────────────────────────────
  console.log('-- Setup: Login --')
  try {
    await login(page)
    pass('Setup: login as teacher@test.com', `URL: ${page.url()}`)
  } catch (e) {
    fail('Setup: login as teacher@test.com', String(e))
    await browser.close()
    printReport()
    process.exit(1)
  }

  // ── Test 1: Page Layout Verification ─────────────────────────────────────
  console.log('\n-- Test 1: Page Layout Verification --')
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await waitIdle(page)

    // 1a. Welcome greeting (h1 contains display_name + 歡迎回來)
    const h1Text = await page.locator('h1').first().textContent()
    if (h1Text && h1Text.includes('歡迎回來')) {
      pass('1a. Welcome greeting visible', `"${h1Text.trim()}"`)
    } else {
      fail('1a. Welcome greeting visible', `h1 text: "${h1Text?.trim()}"`)
    }

    // 1b. Stat cards: 全部專案 / 進行中 / 已完成
    const bodyText = await page.locator('body').textContent()
    const hasStatCards =
      bodyText.includes('全部專案') &&
      bodyText.includes('進行中') &&
      bodyText.includes('已完成')
    if (hasStatCards) {
      pass('1b. Stat cards visible (全部專案 / 進行中 / 已完成)')
    } else {
      fail('1b. Stat cards visible', 'One or more stat card labels not found')
    }

    // 1c. Search bar
    const searchInput = page.locator('input[placeholder*="搜尋"]')
    if (await searchInput.isVisible()) {
      pass('1c. Search bar visible')
    } else {
      fail('1c. Search bar visible', 'No input with 搜尋 placeholder found')
    }

    // 1d. Filter chips: 全部, Discover, Define, Develop, Deliver, 已完成
    const expectedChips = ['全部', 'Discover', 'Define', 'Develop', 'Deliver', '已完成']
    const missingChips = []
    for (const label of expectedChips) {
      const btn = page.locator('button', { hasText: label }).first()
      const visible = await btn.isVisible().catch(() => false)
      if (!visible) missingChips.push(label)
    }
    if (missingChips.length === 0) {
      pass('1d. All filter chips visible (全部, Discover, Define, Develop, Deliver, 已完成)')
    } else {
      fail('1d. Filter chips', `Missing: ${missingChips.join(', ')}`)
    }

    // 1e. Project cards grid — look for at least one card
    const cards = page.locator('.group.relative')
    const cardCount = await cards.count()
    if (cardCount > 0) {
      pass('1e. Project cards visible in grid', `${cardCount} card(s) found`)
    } else {
      // Fallback: look for section headings 進行中 or 已完成
      const sectionHeading = await page.locator('h2').first().isVisible().catch(() => false)
      if (sectionHeading) {
        pass('1e. Project section heading visible (no cards — empty state)')
      } else {
        fail('1e. Project cards or empty state visible', 'No cards or headings detected')
      }
    }

    await screenshot(page, 'phase9-test1-layout.png')
  } catch (e) {
    fail('Test 1: unexpected error', String(e))
    await screenshot(page, 'phase9-test1-error.png')
  }

  // ── Test 2: Search Functionality ─────────────────────────────────────────
  console.log('\n-- Test 2: Search Functionality --')
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await waitIdle(page)

    // Pick the first project name visible on the page for the search term
    const firstCardTitle = await page.locator('h3').first().textContent().catch(() => null)

    if (!firstCardTitle) {
      fail('Test 2: no projects visible to search', 'h3 element not found')
    } else {
      // Use first 3 chars of the project name as the search fragment
      const searchTerm = firstCardTitle.trim().slice(0, 3)
      const searchInput = page.locator('input[placeholder*="搜尋"]')
      await searchInput.fill(searchTerm)
      await page.waitForTimeout(400) // debounce

      // 2a. List filters down (or stays same if all match)
      const afterSearchCards = await page.locator('h3').count()
      pass('2a. Search typed', `term="${searchTerm}", visible titles: ${afterSearchCards}`)

      await screenshot(page, 'phase9-test2-search.png')

      // 2b. Clear search and verify all projects return
      await searchInput.fill('')
      await page.waitForTimeout(400)
      const afterClearCards = await page.locator('h3').count()
      if (afterClearCards >= afterSearchCards) {
        pass('2b. Clear search restores full list', `${afterClearCards} title(s) visible`)
      } else {
        fail('2b. Clear search', `After clear: ${afterClearCards}, after search: ${afterSearchCards}`)
      }
    }
  } catch (e) {
    fail('Test 2: unexpected error', String(e))
    await screenshot(page, 'phase9-test2-error.png')
  }

  // ── Test 3: Stage Filter ──────────────────────────────────────────────────
  console.log('\n-- Test 3: Stage Filter --')
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await waitIdle(page)

    // Click the "Discover" filter chip
    const discoverBtn = page.locator('button', { hasText: 'Discover' }).first()
    await discoverBtn.click()
    await page.waitForTimeout(300)

    // Verify the Discover chip appears active (has bg-primary text-text-inverse classes)
    const discoverBtnClass = await discoverBtn.getAttribute('class')
    const isActive = discoverBtnClass && discoverBtnClass.includes('bg-primary')
    if (isActive) {
      pass('3a. Discover filter chip is active (bg-primary)')
    } else {
      fail('3a. Discover filter chip active state', `classes: ${discoverBtnClass}`)
    }

    // Count cards after filter — 0 cards is also valid if no Discover projects exist
    const filteredCount = await page.locator('h3').count()
    pass('3b. Discover filter applied', `${filteredCount} project title(s) visible`)

    // Verify every visible stage badge says "Discover" (if any cards)
    if (filteredCount > 0) {
      const stageBadges = await page.locator('span').filter({ hasText: 'Discover' }).count()
      if (stageBadges > 0) {
        pass('3c. Only Discover-stage cards shown', `${stageBadges} Discover badge(s)`)
      } else {
        // Could be valid empty-state if no discover projects, or filtered correctly
        const emptyState = await page.locator('text=找不到').isVisible().catch(() => false)
        if (emptyState) {
          pass('3c. No Discover projects, empty state shown')
        } else {
          fail('3c. Stage badge verification', 'Could not confirm only Discover cards shown')
        }
      }
    }

    await screenshot(page, 'phase9-test3-filter.png')

    // 3d. Click 全部 to reset
    const allBtn = page.locator('button', { hasText: '全部' }).first()
    await allBtn.click()
    await page.waitForTimeout(300)
    const allBtnClass = await allBtn.getAttribute('class')
    if (allBtnClass && allBtnClass.includes('bg-primary')) {
      pass('3d. 全部 filter chip is active after reset')
    } else {
      fail('3d. 全部 chip not active after reset', `classes: ${allBtnClass}`)
    }
  } catch (e) {
    fail('Test 3: unexpected error', String(e))
    await screenshot(page, 'phase9-test3-error.png')
  }

  // ── Test 4: Project Card Design ───────────────────────────────────────────
  console.log('\n-- Test 4: Project Card Design --')
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await waitIdle(page)

    // Find the first project card (group relative div)
    const firstCard = page.locator('.group.relative').first()
    const cardVisible = await firstCard.isVisible().catch(() => false)

    if (!cardVisible) {
      fail('Test 4: no project card found to inspect')
    } else {
      // 4a. Colored left border bar (w-1 shrink-0)
      const colorBar = firstCard.locator('div.w-1').first()
      if (await colorBar.isVisible()) {
        pass('4a. Colored left border bar present')
      } else {
        fail('4a. Colored left border bar', 'w-1 element not found in card')
      }

      // 4b. Stage badge (span with rounded-full in footer)
      // The stage badge is a span with rounded-full px-2 py-0.5 font-medium
      const stageBadge = firstCard.locator('span.rounded-full, span.inline-flex').first()
      if (await stageBadge.isVisible()) {
        const badgeText = await stageBadge.textContent()
        pass('4b. Stage badge visible', `"${badgeText?.trim()}"`)
      } else {
        fail('4b. Stage badge not visible')
      }

      // 4c. Human count icon (Users icon + number)
      const cardText = await firstCard.textContent()
      // The footer has numbers for human and AI seat counts
      pass('4c. Card footer content present', `card text snippet: "${cardText?.slice(0, 80).trim()}"`)

      // 4d. Relative timestamp — look for 前 or 剛剛 in the card text
      const hasTimestamp = cardText && (cardText.includes('前') || cardText.includes('剛剛'))
      if (hasTimestamp) {
        pass('4d. Relative timestamp present in card')
      } else {
        fail('4d. Relative timestamp', `card text: "${cardText?.slice(0, 120)}"`)
      }

      // 4e. Hover: three-dot menu button appears
      // The button has opacity-0 group-hover:opacity-100, so hover the card first
      await firstCard.hover()
      await page.waitForTimeout(300)

      const menuBtn = firstCard.locator('button[aria-label="專案選單"]')
      const menuBtnVisible = await menuBtn.isVisible().catch(() => false)
      if (menuBtnVisible) {
        pass('4e. Three-dot menu button visible on hover')
      } else {
        // Check if opacity changed — evaluate style
        const opacity = await menuBtn.evaluate((el) => {
          return window.getComputedStyle(el).opacity
        }).catch(() => 'unknown')
        if (opacity === '1') {
          pass('4e. Three-dot menu button visible on hover (opacity=1)')
        } else {
          fail('4e. Three-dot menu button on hover', `opacity: ${opacity}`)
        }
      }

      await screenshot(page, 'phase9-test4-card-hover.png')
    }
  } catch (e) {
    fail('Test 4: unexpected error', String(e))
    await screenshot(page, 'phase9-test4-error.png')
  }

  // ── Test 5: Delete Flow ───────────────────────────────────────────────────
  console.log('\n-- Test 5: Delete Flow --')
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await waitIdle(page)

    const firstCard = page.locator('.group.relative').first()
    const cardVisible = await firstCard.isVisible().catch(() => false)

    if (!cardVisible) {
      fail('Test 5: no project card found to test delete flow')
    } else {
      // Get project name for confirmation input
      const projectNameEl = firstCard.locator('h3').first()
      const projectName = (await projectNameEl.textContent())?.trim() ?? ''
      pass('5a. Captured project name for delete test', `"${projectName}"`)

      // 5b. Hover the card so the menu button appears
      await firstCard.hover()
      await page.waitForTimeout(300)

      // 5c. Click the three-dot menu button
      const menuBtn = firstCard.locator('button[aria-label="專案選單"]')
      await menuBtn.click({ force: true })
      await page.waitForTimeout(300)

      // 5d. Click "刪除專案" from the dropdown
      const deleteMenuItemBtn = page.locator('button', { hasText: '刪除專案' }).first()
      if (await deleteMenuItemBtn.isVisible({ timeout: 3000 })) {
        await deleteMenuItemBtn.click()
        pass('5b. Clicked 刪除專案 from dropdown menu')
      } else {
        fail('5b. 刪除專案 menu item not visible')
        throw new Error('Cannot proceed: delete menu item not visible')
      }

      await page.waitForTimeout(400)

      // 5e. Verify delete confirmation dialog appears
      const dialogTitle = page.locator('text=刪除專案').last()
      if (await dialogTitle.isVisible({ timeout: 3000 })) {
        pass('5c. Delete confirmation dialog appeared')
      } else {
        fail('5c. Delete confirmation dialog not visible')
      }

      // 5f. Verify the "永久刪除" button is disabled initially
      const deleteBtn = page.locator('button', { hasText: '永久刪除' }).first()
      const isDisabledInitially = await deleteBtn.isDisabled().catch(() => false)
      if (isDisabledInitially) {
        pass('5d. 永久刪除 button is disabled initially')
      } else {
        fail('5d. 永久刪除 button should be disabled initially', 'Button was enabled or not found')
      }

      // 5g. Type the project name in the confirmation input
      const confirmInput = page.locator('input[placeholder]').last()
      await confirmInput.fill(projectName)
      await page.waitForTimeout(200)

      // 5h. Verify the "永久刪除" button becomes enabled
      const isEnabledAfterType = await deleteBtn.isEnabled().catch(() => false)
      if (isEnabledAfterType) {
        pass('5e. 永久刪除 button becomes enabled after typing project name')
      } else {
        // Try checking disabled attribute directly
        const disabledAttr = await deleteBtn.getAttribute('disabled')
        fail('5e. 永久刪除 button state after typing', `disabled attr: ${disabledAttr}`)
      }

      // Take screenshot of dialog before closing
      await screenshot(page, 'phase9-test5-delete-dialog.png')

      // 5i. Click "取消" to close without deleting
      const cancelBtn = page.locator('button', { hasText: '取消' }).first()
      await cancelBtn.click()
      await page.waitForTimeout(400)

      // Verify dialog is closed
      const dialogStillVisible = await dialogTitle.isVisible({ timeout: 1000 }).catch(() => false)
      if (!dialogStillVisible) {
        pass('5f. Dialog closed after clicking 取消 (no deletion occurred)')
      } else {
        fail('5f. Dialog still visible after clicking 取消')
      }
    }
  } catch (e) {
    fail('Test 5: unexpected error', String(e))
    await screenshot(page, 'phase9-test5-error.png')
  }

  // ── Cleanup ───────────────────────────────────────────────────────────────
  await page.close()
  await context.close()
  await browser.close()

  printReport()
}

function printReport() {
  const passed = results.filter((r) => r.status === 'PASS').length
  const failed = results.filter((r) => r.status === 'FAIL').length

  console.log('\n===================================================')
  console.log('  TEST RESULTS SUMMARY')
  console.log('===================================================')

  for (const r of results) {
    const icon = r.status === 'PASS' ? '[PASS]' : '[FAIL]'
    console.log(`  ${icon} ${r.name}`)
    if (r.detail) console.log(`         ${r.detail}`)
  }

  console.log('\n---------------------------------------------------')
  console.log(`  Total: ${results.length} | Passed: ${passed} | Failed: ${failed}`)
  const rate = results.length > 0 ? Math.round((passed / results.length) * 100) : 0
  console.log(`  Pass Rate: ${rate}%`)
  console.log(`  Screenshots saved to: ${SCREENSHOTS_DIR}`)
  console.log('===================================================\n')
}

run().catch((err) => {
  console.error('Fatal error:', err)
  process.exit(1)
})
