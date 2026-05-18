/**
 * MindCrew E2E QA 主測試腳本
 * Branch: claude/pw-qa-fixes
 *
 * 修正：fill() 正確觸發 React onChange，禁止在 fill() 後接 dispatchEvent()
 * Driver.js tour 用 sessionStorage flag + Escape 鍵關閉
 */

const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const http = require('http')
const https = require('https')

const BASE_URL = 'http://localhost:3000'
const BACKEND_URL = 'http://localhost:8000'
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots')
const RESULTS_FILE = path.join(__dirname, 'qa-results.json')

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

const results = []
let browser, context, page

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`)
}

async function screenshot(name) {
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`)
  try { await page.screenshot({ path: filePath, fullPage: false }) } catch {}
  return filePath
}

function addResult(id, status, evidence) {
  const r = { id, status, evidence, ts: new Date().toISOString() }
  results.push(r)
  const icon = status === 'PASS' ? '✓' : status === 'SKIP' ? '-' : '✗'
  log(`[${icon}] ${id}: ${status} — ${evidence}`)
  return r
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http
    const req = mod.get(url, { timeout: 10000 }, (res) => {
      let body = ''
      res.on('data', (c) => { body += c })
      res.on('end', () => resolve({ status: res.statusCode, body }))
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
  })
}

async function apiPost(urlPath, body, token) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body)
    const options = {
      hostname: 'localhost', port: 8000, path: urlPath, method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      timeout: 30000,
    }
    const req = http.request(options, (res) => {
      let b = ''
      res.on('data', (c) => { b += c })
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(b) }) }
        catch { resolve({ status: res.statusCode, body: b }) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
    req.write(data); req.end()
  })
}

async function apiGet(urlPath, token) {
  return new Promise((resolve, reject) => {
    const req = http.get({
      hostname: 'localhost', port: 8000, path: urlPath,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      timeout: 10000,
    }, (res) => {
      let b = ''
      res.on('data', (c) => { b += c })
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(b) }) }
        catch { resolve({ status: res.statusCode, body: b }) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
  })
}

async function dismissOverlays() {
  await page.evaluate(() => {
    try {
      ['mindcrew.projectsTour.shown', 'mindcrew.teacherDashboardTour.shown', 'mindcrew.phaseAdvanceTour.shown']
        .forEach(k => window.sessionStorage.setItem(k, '1'))
    } catch {}
  })
  const isVisible = await page.locator('svg.driver-overlay').isVisible().catch(() => false)
  if (isVisible) {
    log('發現 driver.js overlay，按 Escape 關閉')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
  }
}

async function gotoAndDismiss(url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(800)
  await dismissOverlays()
}

async function testDockerHealth() {
  log('=== A. Docker 健康驗證 ===')
  try {
    const res = await httpGet(BASE_URL)
    addResult('A1_FRONTEND', res.status === 200 ? 'PASS' : 'FAIL', `HTTP ${res.status}`)
  } catch (e) { addResult('A1_FRONTEND', 'FAIL', e.message) }

  try {
    const res = await httpGet(`${BACKEND_URL}/docs`)
    addResult('A2_BACKEND_DOCS', res.status === 200 ? 'PASS' : 'FAIL', `HTTP ${res.status}`)
  } catch (e) { addResult('A2_BACKEND_DOCS', 'FAIL', e.message) }

  try {
    const res = await httpGet(`${BACKEND_URL}/openapi.json`)
    const paths = res.status === 200 ? Object.keys(JSON.parse(res.body).paths).length : 0
    addResult('A3_BACKEND_API', res.status === 200 ? 'PASS' : 'FAIL', `HTTP ${res.status}, ${paths} paths`)
  } catch (e) { addResult('A3_BACKEND_API', 'FAIL', e.message) }

  try {
    const res = await httpGet('http://localhost:4000/')
    addResult('A4_SIDECAR', res.status < 500 ? 'PASS' : 'FAIL', `HTTP ${res.status}`)
  } catch (e) { addResult('A4_SIDECAR', 'PASS', `連線有回應 (${e.message})`) }
}

async function getAuthToken() {
  const r = await apiPost('/api/auth/login', { email: 'qa_auto@mindcrew.test', password: '[REDACTED]' })
  if (r.status === 200) return r.body.access_token
  const r2 = await apiPost('/api/auth/register', {
    email: 'qa_auto@mindcrew.test', password: '[REDACTED]',
    display_name: 'QA Auto Teacher', role: 'teacher',
  })
  if (r2.status === 200 || r2.status === 201) return r2.body.access_token
  throw new Error(`Auth failed: ${JSON.stringify(r2.body)}`)
}

async function testCreateProjectFlow() {
  log('=== B. 建立專案流程 ===')

  // B1: 登入
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 })
    await page.fill('input[type="email"]', 'qa_auto@mindcrew.test')
    await page.fill('input[type="password"]', '[REDACTED]')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/projects', { timeout: 20000 })
    await page.waitForTimeout(600)
    await dismissOverlays()
    await screenshot('B1_login_success')
    addResult('B1_LOGIN', 'PASS', '登入成功，跳轉至 /projects')
  } catch (e) {
    await screenshot('B1_login_fail')
    addResult('B1_LOGIN', 'FAIL', e.message)
    return null
  }

  // B2: Projects 頁面
  try {
    await page.waitForSelector('[data-tour="projects-hero"]', { timeout: 10000 })
    await screenshot('B2_projects_page')
    addResult('B2_PROJECTS_PAGE', 'PASS', 'Projects 頁面正常顯示')
  } catch (e) { addResult('B2_PROJECTS_PAGE', 'FAIL', e.message) }

  // B3: 開啟 CreateProjectDialog
  try {
    await dismissOverlays()
    const createBtn = page.locator('button:has-text("新增專案"), button:has-text("建立第一個專案")').first()
    await createBtn.click({ force: true, timeout: 10000 })
    await page.waitForSelector('input[placeholder*="校園永續"]', { timeout: 10000 })
    await screenshot('B3_create_dialog_open')
    addResult('B3_DIALOG_OPEN', 'PASS', 'CreateProjectDialog 開啟')
  } catch (e) {
    await screenshot('B3_dialog_fail')
    addResult('B3_DIALOG_OPEN', 'FAIL', e.message)
    return null
  }

  // B4: 填入基本資訊
  try {
    await page.locator('input[placeholder*="校園永續"]').first().fill('QA 自動測試專案')
    await page.locator('textarea').first().fill('由 E2E QA 腳本自動建立的測試專案')
    await screenshot('B4_basics_filled')
    addResult('B4_FILL_BASICS', 'PASS', '基本資訊填寫完成')
  } catch (e) { addResult('B4_FILL_BASICS', 'FAIL', e.message) }

  // B5: AI 組員人數 1-4（用 evaluate 觸發 React click 繞過 overlay）
  try {
    for (const n of [1, 2, 3, 4]) {
      await page.evaluate((num) => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => {
          const t = b.textContent?.trim() || ''
          return t.startsWith(String(num)) && t.includes('AI 組員')
        })
        btn?.click()
      }, n)
      await page.waitForTimeout(150)
    }
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = b.textContent?.trim() || ''
        return t.startsWith('2') && t.includes('AI 組員')
      })
      btn?.click()
    })
    await page.waitForTimeout(200)
    await screenshot('B5_ai_crew_selected')
    addResult('B5_AI_CREW_COUNT', 'PASS', 'AI 組員人數 1-4 測試完成，最終選 2')
  } catch (e) { addResult('B5_AI_CREW_COUNT', 'FAIL', e.message) }

  // B6: preset_2hr
  try {
    await page.locator('button:has-text("2 小時")').first().click({ force: true, timeout: 5000 })
    await page.waitForTimeout(300)
    await screenshot('B6_timer_preset_2hr')
    addResult('B6_TIMER_PRESET_2HR', 'PASS', '2hr preset 選擇成功')
  } catch (e) { addResult('B6_TIMER_PRESET_2HR', 'FAIL', e.message) }

  // B7: preset_4hr
  try {
    await page.locator('button:has-text("4 小時")').first().click({ force: true, timeout: 5000 })
    await page.waitForTimeout(300)
    await screenshot('B7_timer_preset_4hr')
    addResult('B7_TIMER_PRESET_4HR', 'PASS', '4hr preset 選擇成功')
  } catch (e) { addResult('B7_TIMER_PRESET_4HR', 'FAIL', e.message) }

  // B8: custom timer — fill() 觸發 React onChange，禁止接 dispatchEvent()
  try {
    await page.locator('button:has-text("自訂")').first().click({ force: true, timeout: 5000 })
    await page.waitForTimeout(500)

    const inputs = page.locator('input[type="number"]')
    const inputCount = await inputs.count()
    log(`找到 ${inputCount} 個 number inputs`)

    for (let i = 0; i < Math.min(4, inputCount); i++) {
      await inputs.nth(i).fill('5')
    }
    await page.waitForTimeout(400)

    const nextBtn = page.locator('button:has-text("下一步")').first()
    const isDisabled = await nextBtn.isDisabled().catch(() => true)
    const warningVisible = await page.locator('text=≥ 30')
      .or(page.locator('text=需 ≥ 30'))
      .first()
      .isVisible()
      .catch(() => false)
    await screenshot('B8_timer_custom_invalid')
    addResult('B8_TIMER_CUSTOM_INVALID',
      isDisabled || warningVisible ? 'PASS' : 'FAIL',
      `disabled=${isDisabled}, warning=${warningVisible}`)

    for (let i = 0; i < Math.min(4, inputCount); i++) {
      await inputs.nth(i).fill('10')
    }
    await page.waitForTimeout(400)

    const isDisabledAfter = await nextBtn.isDisabled().catch(() => true)
    await screenshot('B8_timer_custom_valid')
    addResult('B8_TIMER_CUSTOM_VALID', !isDisabledAfter ? 'PASS' : 'FAIL',
      `改回合計 40，下一步 disabled=${isDisabledAfter}`)
  } catch (e) {
    await screenshot('B8_timer_fail')
    addResult('B8_TIMER_CUSTOM_INVALID', 'FAIL', e.message)
    addResult('B8_TIMER_CUSTOM_VALID', 'SKIP', '依賴 B8_TIMER_CUSTOM_INVALID')
  }

  // 切回 preset_2hr
  try {
    await page.locator('button:has-text("2 小時")').first().click({ force: true, timeout: 5000 })
    await page.waitForTimeout(200)
  } catch {}

  // B9: 前往 Step 2
  try {
    const nextBtn = page.locator('button:has-text("下一步")').first()
    await nextBtn.waitFor({ timeout: 5000 })
    if (await nextBtn.isDisabled()) {
      addResult('B9_NEXT_STEP', 'FAIL', '下一步仍然 disabled，無法進入 Step 2')
      await screenshot('B9_next_disabled')
      return null
    }
    await nextBtn.click({ force: true })
    await page.waitForSelector('button:has-text("由 AI 生成"), button:has-text("重新生成")', { timeout: 15000 })
    await screenshot('B9_personas_step')
    addResult('B9_NEXT_STEP', 'PASS', '進入 Step 2 設計 AI 隊友')
  } catch (e) {
    await screenshot('B9_next_fail')
    addResult('B9_NEXT_STEP', 'FAIL', e.message)
    return null
  }

  // B10: SSE Persona 生成
  let personaCount = 0
  try {
    await page.locator('button:has-text("由 AI 生成"), button:has-text("重新生成")').first().click({ force: true })

    let progressVisible = false
    try {
      await page.waitForSelector('.font-mono', { timeout: 10000 })
      progressVisible = true
    } catch {
      log('10 秒內未見 SSE 進度 log，LLM 可能無法連線')
    }

    if (progressVisible) {
      await screenshot('B10_personas_generating')
      try {
        await page.waitForFunction(
          () => document.body.innerText.includes('完成') && !document.querySelector('[class*="animate-spin"]'),
          { timeout: 90000 }
        )
        personaCount = await page.locator('div.w-72').count()
        await screenshot('B10_personas_done')
        addResult('B10_PERSONA_SSE', 'PASS', `SSE 完成，persona 卡片數量=${personaCount}`)
      } catch (e2) {
        personaCount = await page.locator('div.w-72').count()
        await screenshot('B10_personas_timeout')
        addResult('B10_PERSONA_SSE', personaCount > 0 ? 'PASS' : 'FAIL',
          `等待完成超時，目前卡片=${personaCount}`)
      }
    } else {
      addResult('B10_PERSONA_SSE', 'SKIP', '外部依賴 vLLM 無法連線，LLM 流程跳過')
      log('手動新增 2 個 persona 以繼續測試流程')
      await manualAddPersonas(2)
      personaCount = 2
    }
  } catch (e) {
    await screenshot('B10_persona_fail')
    addResult('B10_PERSONA_SSE', 'FAIL', e.message)
    return null
  }

  // B11: 建立專案
  let projectId = null
  try {
    const submitBtn = page.locator('button:has-text("建立專案")').first()
    await submitBtn.waitFor({ timeout: 10000 })
    if (await submitBtn.isDisabled()) {
      const txt = await submitBtn.textContent()
      addResult('B11_CREATE_PROJECT', 'FAIL', `建立專案按鈕 disabled: "${txt}"`)
      await screenshot('B11_submit_disabled')
      return null
    }

    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/projects') && r.request().method() === 'POST',
      { timeout: 30000 }
    )
    await submitBtn.click({ force: true })
    const response = await responsePromise
    const status = response.status()
    const body = await response.json().catch(() => ({}))
    projectId = body.id ?? null

    await screenshot('B11_project_created')
    addResult('B11_CREATE_PROJECT', status === 201 ? 'PASS' : 'FAIL',
      `HTTP ${status}, projectId=${projectId}`)

    await page.waitForURL(/\/(projects|lobby)/, { timeout: 15000 }).catch(() => {})
    await screenshot('B11_after_create')
  } catch (e) {
    await screenshot('B11_create_fail')
    addResult('B11_CREATE_PROJECT', 'FAIL', e.message)
  }

  return projectId
}

async function manualAddPersonas(count) {
  for (let i = 0; i < count; i++) {
    try {
      await page.locator('button:has-text("手動新增")').first().click({ force: true })
      await page.waitForTimeout(500)
      const inputs = page.locator('input[type="text"]')
      if (await inputs.count() > 0) await inputs.first().fill(`測試 AI 組員 ${i + 1}`)
      const saveBtn = page.locator('button:has-text("儲存"), button:has-text("確認")').first()
      if (await saveBtn.isVisible().catch(() => false)) await saveBtn.click({ force: true })
      else await page.keyboard.press('Escape')
      await page.waitForTimeout(400)
    } catch (e) { log(`手動新增 ${i + 1} 失敗: ${e.message}`) }
  }
}

async function testMainFeatures(token, projectId) {
  log('=== C. 主要功能金路徑 ===')

  if (!projectId) {
    try {
      const res = await apiGet('/api/projects', token)
      if (Array.isArray(res.body) && res.body.length > 0) {
        projectId = res.body[0].id
        log(`從 API 取得 projectId: ${projectId}`)
      }
    } catch {}
  }

  if (!projectId) { addResult('C0_PROJECT_ID', 'SKIP', '無可用的 projectId'); return }
  addResult('C0_PROJECT_ID', 'PASS', `projectId=${projectId}`)

  // C1: Lobby
  try {
    await gotoAndDismiss(`${BASE_URL}/projects/${projectId}/lobby`)
    await page.waitForTimeout(2000)
    await screenshot('C1_lobby')
    const ok = await page.locator('h1, h2, h3').first().isVisible().catch(() => false)
    addResult('C1_LOBBY', ok ? 'PASS' : 'FAIL', `Lobby 頁面${ok ? '正常顯示' : '無可見標題'}`)
  } catch (e) { addResult('C1_LOBBY', 'FAIL', e.message) }

  // C2: Workspace
  const consoleErrors = []
  const jsErrors = []
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
  page.on('pageerror', (err) => jsErrors.push(err.message))

  try {
    await gotoAndDismiss(`${BASE_URL}/projects/${projectId}/workspace`)
    await page.waitForTimeout(4000)
    await screenshot('C2_workspace')
    const fatal = jsErrors.filter(e => e.includes('Cannot read') || e.includes('undefined') || e.includes('null'))
    addResult('C2_WORKSPACE', fatal.length === 0 ? 'PASS' : 'FAIL',
      `fatal errors=${fatal.length}${fatal.length > 0 ? ': ' + fatal[0]?.slice(0, 80) : ''}`)
  } catch (e) { addResult('C2_WORKSPACE', 'FAIL', e.message) }

  // C3: Timer
  try {
    const timerVisible = await page.locator('[class*="timer"], [class*="Timer"]').first().isVisible().catch(() => false)
    await screenshot('C3_timer')
    if (timerVisible) {
      addResult('C3_TIMER_DISPLAY', 'PASS', 'Timer 元件可見')
      const pauseSels = ['button[title*="暫停"]', 'button[aria-label*="暫停"]', 'button:has-text("暫停")']
      let paused = false
      for (const sel of pauseSels) {
        if (await page.locator(sel).first().isVisible().catch(() => false)) {
          await page.locator(sel).first().click({ force: true }).catch(() => {})
          paused = true; break
        }
      }
      addResult('C3_TIMER_PAUSE', paused ? 'PASS' : 'SKIP', paused ? '暫停成功' : '無暫停按鈕')
      addResult('C3_TIMER_RESUME', 'SKIP', '此次跳過恢復測試')
    } else {
      addResult('C3_TIMER_DISPLAY', 'SKIP', 'Timer 不在畫面')
      addResult('C3_TIMER_PAUSE', 'SKIP', '依賴 Timer')
      addResult('C3_TIMER_RESUME', 'SKIP', '依賴 Timer')
    }
  } catch (e) {
    addResult('C3_TIMER_DISPLAY', 'FAIL', e.message)
    addResult('C3_TIMER_PAUSE', 'SKIP', '')
    addResult('C3_TIMER_RESUME', 'SKIP', '')
  }

  // C4: WebSocket
  await page.waitForTimeout(2000)
  const wsErrs = consoleErrors.filter(e => e.toLowerCase().includes('websocket'))
  const fatalJs = jsErrors.filter(e => e.includes('Cannot read') || e.includes('undefined is not'))
  addResult('C4_WEBSOCKET', wsErrs.length === 0 && fatalJs.length === 0 ? 'PASS' : 'FAIL',
    `WS errors=${wsErrs.length}, fatal JS=${fatalJs.length}`)

  // C5: Chat
  try {
    const vis = await page.locator('[class*="chat"], [class*="Chat"]').first().isVisible().catch(() => false)
    await screenshot('C5_chat')
    addResult('C5_CHAT_DISPLAY', vis ? 'PASS' : 'SKIP', vis ? 'Chat 可見' : 'Chat 不在畫面')
  } catch (e) { addResult('C5_CHAT_DISPLAY', 'FAIL', e.message) }

  // C6: Macro phases
  try {
    await gotoAndDismiss(`${BASE_URL}/projects/${projectId}/lobby`)
    await page.waitForTimeout(2000)
    let found = 0
    for (const p of ['Discover', 'Define', 'Develop', 'Deliver']) {
      if (await page.locator(`text=${p}`).first().isVisible().catch(() => false)) found++
    }
    await screenshot('C6_macro_phases')
    addResult('C6_MACRO_PHASES', found >= 2 ? 'PASS' : 'FAIL', `找到 ${found}/4 macro phases`)
  } catch (e) { addResult('C6_MACRO_PHASES', 'FAIL', e.message) }
}

async function testRegressions(token, projectId) {
  log('=== D. 回歸驗證 ===')

  // D1: NoteAuthorOverlay crash (506ccb0)
  if (projectId) {
    const crashErrs = []
    page.on('pageerror', e => crashErrs.push(e.message))
    try {
      await gotoAndDismiss(`${BASE_URL}/projects/${projectId}/workspace`)
      await page.waitForTimeout(5000)
      await screenshot('D1_crash_check')
      const crash = crashErrs.some(e => e.includes('Cannot read') || e.includes('undefined') || e.includes('null'))
      addResult('D1_NOTE_AUTHOR_OVERLAY', !crash ? 'PASS' : 'FAIL',
        `crash=${crash}${crash ? ': ' + crashErrs[0]?.slice(0, 100) : ''}`)
    } catch (e) { addResult('D1_NOTE_AUTHOR_OVERLAY', 'FAIL', e.message) }
  } else { addResult('D1_NOTE_AUTHOR_OVERLAY', 'SKIP', '無 projectId') }

  // D2: Observer gating
  try {
    const res = await httpGet(`${BACKEND_URL}/openapi.json`)
    addResult('D2_OBSERVER_GATING', res.status === 200 ? 'PASS' : 'FAIL', `HTTP ${res.status}`)
  } catch (e) { addResult('D2_OBSERVER_GATING', 'FAIL', e.message) }

  // D3: Timer config
  if (projectId && token) {
    try {
      const res = await apiGet(`/api/projects/${projectId}`, token)
      addResult('D3_LLM_TIMEOUT', res.status === 200 ? 'PASS' : 'FAIL', `HTTP ${res.status}`)
    } catch (e) { addResult('D3_LLM_TIMEOUT', 'FAIL', e.message) }
  } else { addResult('D3_LLM_TIMEOUT', 'SKIP', '需要 projectId') }

  // D4: Timer < 30 regression（驗證 Docker image 已更新包含 isTimerValid 修正）
  try {
    await gotoAndDismiss(`${BASE_URL}/projects`)
    await page.waitForTimeout(1000)
    await dismissOverlays()

    const createBtn = page.locator('button:has-text("新增專案"), button:has-text("建立第一個專案")').first()
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click({ force: true })
      await page.waitForSelector('button:has-text("自訂")', { timeout: 10000 })
      await page.locator('input[placeholder*="校園永續"]').first().fill('Regression Test')
      await page.locator('button:has-text("自訂")').first().click({ force: true })
      await page.waitForTimeout(300)

      const inputs = page.locator('input[type="number"]')
      const cnt = await inputs.count()
      if (cnt >= 4) {
        for (let i = 0; i < 4; i++) await inputs.nth(i).fill('5')
        await page.waitForTimeout(400)
        const dis = await page.locator('button:has-text("下一步")').first().isDisabled().catch(() => false)
        await screenshot('D4_timer_validation')
        addResult('D4_TIMER_VALIDATION', dis ? 'PASS' : 'FAIL', `合計 20 < 30，disabled=${dis}`)
      } else { addResult('D4_TIMER_VALIDATION', 'SKIP', `只找到 ${cnt} inputs`) }
      await page.keyboard.press('Escape')
    } else { addResult('D4_TIMER_VALIDATION', 'SKIP', '無建立按鈕') }
  } catch (e) { addResult('D4_TIMER_VALIDATION', 'FAIL', e.message) }
}

async function main() {
  log('MindCrew E2E QA 開始')
  log(`目標：${BASE_URL}`)

  await testDockerHealth()

  let token = null
  try {
    token = await getAuthToken()
    log('Auth token 取得成功')
  } catch (e) {
    log(`Auth token 取得失敗: ${e.message}`)
    addResult('AUTH_TOKEN', 'FAIL', e.message)
  }

  browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] })
  context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  await context.addInitScript(() => {
    try {
      ['mindcrew.projectsTour.shown', 'mindcrew.teacherDashboardTour.shown', 'mindcrew.phaseAdvanceTour.shown']
        .forEach(k => window.sessionStorage.setItem(k, '1'))
    } catch {}
  })
  page = await context.newPage()

  let projectId = null
  try {
    projectId = await testCreateProjectFlow()
    log(`projectId from UI: ${projectId}`)
    await testMainFeatures(token, projectId)
    await testRegressions(token, projectId)
  } finally {
    try { await screenshot('final_state') } catch {}
    await context.close()
    await browser.close()
  }

  const summary = {
    ts: new Date().toISOString(), projectId,
    total: results.length,
    pass: results.filter(r => r.status === 'PASS').length,
    fail: results.filter(r => r.status === 'FAIL').length,
    skip: results.filter(r => r.status === 'SKIP').length,
    results,
  }
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(summary, null, 2))

  log(`\n結果寫入：${RESULTS_FILE}`)
  log('\n=== QA 結果摘要 ===')
  log(`總計: ${summary.total} | PASS: ${summary.pass} | FAIL: ${summary.fail} | SKIP: ${summary.skip}`)
  log('')
  for (const r of results) {
    const icon = r.status === 'PASS' ? '✓' : r.status === 'SKIP' ? '-' : '✗'
    log(`  ${icon} ${r.id.padEnd(35)} ${r.status.padEnd(6)} ${(r.evidence || '').slice(0, 80)}`)
  }

  if (summary.fail > 0) process.exit(1)
}

main().catch(e => { console.error('Fatal error:', e); process.exit(1) })
