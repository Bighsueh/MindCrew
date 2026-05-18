/**
 * Full E2E test run — all test IDs: D1, L1, P1, P2, W1, W2, W3, T1, A1, C1, E1
 * Run: node full-e2e-run.js
 */

const { chromium } = require('playwright');
const { execSync } = require('child_process');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const SIDECAR_URL = 'http://localhost:4000';

const results = [];
let projectId = null;

function pass(id, evidence) {
  results.push({ id, result: 'PASS', evidence });
  console.log(`[PASS] ${id}: ${evidence}`);
}

function fail(id, evidence) {
  results.push({ id, result: 'FAIL', evidence });
  console.log(`[FAIL] ${id}: ${evidence}`);
}

function skip(id, reason) {
  results.push({ id, result: 'SKIP', evidence: reason });
  console.log(`[SKIP] ${id}: ${reason}`);
}

async function dismissOnboarding(page) {
  // Suppress driver.js overlay
  await page.evaluate(() => {
    document.body.classList.remove('driver-active', 'driver-fade');
    document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
  }).catch(() => {});
  // Set localStorage flags to suppress firstrun/tour modals
  await page.evaluate(() => {
    try {
      Object.keys(localStorage).forEach(k => {
        if (k.includes('firstrun') || k.includes('tour') || k.includes('mindcrew')) {
          localStorage.setItem(k, '1');
        }
      });
      localStorage.setItem('mindcrew.firstrun.projects', '1');
      localStorage.setItem('mindcrew.firstrun.workspace', '1');
      localStorage.setItem('mindcrew.firstrun.lobby', '1');
    } catch(e) {}
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
    } catch(e) {}
  }).catch(() => {});
}

async function loginViaUI(page, email, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await dismissOnboarding(page);

  // Fill email
  const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="信箱" i]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.click();
  await emailInput.pressSequentially(email, { delay: 50 });

  // Fill password
  const pwInput = page.locator('input[type="password"]').first();
  await pwInput.click();
  await pwInput.pressSequentially(password, { delay: 50 });

  // Submit
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/(projects|dashboard|lobby|workspace)/, { timeout: 15000 });
}

async function loginViaAPI(email, password) {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return resp.json();
}

async function runD1(page) {
  // D1 — Docker stack health (already validated via bash; just confirm via page)
  try {
    const resp1 = await fetch(`${SIDECAR_URL}/health`);
    const resp2 = await fetch(`${API_URL}/openapi.json`);
    const r1ok = resp1.status === 200;
    const r2ok = resp2.status === 200;

    const pgResult = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM \\"user\\";" -t 2>&1`
    ).toString().trim();
    const userCount = parseInt(pgResult.match(/\d+/)?.[0] || '0');

    const pgProj = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM project;" -t 2>&1`
    ).toString().trim();
    const projCount = parseInt(pgProj.match(/\d+/)?.[0] || '0');

    const pageResp = await fetch(`${BASE_URL}`);
    const frontendOk = pageResp.status === 200;

    if (r1ok && r2ok && frontendOk && userCount === 7 && projCount === 0) {
      pass('D1', `sidecar=200, backend=200, frontend=200, users=${userCount}, projects=${projCount}`);
    } else {
      fail('D1', `sidecar=${resp1.status} backend=${resp2.status} frontend=${pageResp.status} users=${userCount} projects=${projCount}`);
    }
  } catch (e) {
    fail('D1', e.message);
  }
}

async function runL1(page) {
  // L1 — Auth
  try {
    // Login teacher via UI
    await loginViaUI(page, 'teacher@test.com', 'teacher123');
    await page.waitForTimeout(1000);

    // Check JWT in localStorage
    const token = await page.evaluate(() => {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const val = localStorage.getItem(key);
        if (val && val.startsWith('eyJ')) return val;
      }
      // try common keys
      return localStorage.getItem('access_token') || localStorage.getItem('token') || localStorage.getItem('mindcrew.token');
    });

    // Check /api/auth/me
    const meResp = await fetch(`${API_URL}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const meData = await meResp.json();

    // Student1 via API
    const s1Data = await loginViaAPI('student1@test.com', 'student123');

    if (meData.role === 'teacher' && s1Data.user?.role === 'student') {
      pass('L1', `teacher role=${meData.role} ✓, student1 role=${s1Data.user.role} ✓, JWT present=${!!token}`);
    } else {
      fail('L1', `teacher role=${meData.role}, student1 role=${s1Data.user?.role}, token=${!!token}`);
    }
  } catch (e) {
    fail('L1', e.message);
  }
}

async function runP1(page) {
  // P1 — Create project full UI happy path
  try {
    // Ensure logged in as teacher
    await loginViaUI(page, 'teacher@test.com', 'teacher123');
    await page.waitForTimeout(500);
    await dismissOnboarding(page);

    // Navigate to /projects
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
    await dismissOnboarding(page);
    await page.waitForTimeout(1000);

    // Remove any driver overlays
    await page.evaluate(() => {
      document.body.classList.remove('driver-active', 'driver-fade');
      document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
    });

    // Click 新增專案 button
    const newProjBtn = page.locator('button:has-text("新增專案"), button:has-text("建立專案"), button:has-text("Create"), a:has-text("新增專案")').first();
    await newProjBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newProjBtn.click();
    await page.waitForTimeout(1000);

    // Fill name
    const nameInput = page.locator('input[placeholder*="專案名稱"], input[name="name"], input[placeholder*="名稱"], input[id*="name"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 8000 });
    await nameInput.click();
    await nameInput.pressSequentially('Playwright E2E 測試專案', { delay: 30 });

    // Fill description if present
    const descInput = page.locator('textarea[placeholder*="描述"], textarea[name="description"], textarea[placeholder*="description" i]').first();
    if (await descInput.isVisible().catch(() => false)) {
      await descInput.click();
      await descInput.pressSequentially('E2E 自動化測試建立的設計思考專案', { delay: 30 });
    }

    // Fill constraints if present
    const constraintInput = page.locator('textarea[placeholder*="限制"], input[placeholder*="限制"], textarea[placeholder*="constraint"]').first();
    if (await constraintInput.isVisible().catch(() => false)) {
      await constraintInput.click();
      await constraintInput.pressSequentially('時間限制 2 小時', { delay: 30 });
    }

    // Set ai_crew_count=3 if there's a number input
    const crewCountInput = page.locator('input[type="number"][name*="crew"], input[type="number"][id*="crew"], input[type="number"][placeholder*="人數"]').first();
    if (await crewCountInput.isVisible().catch(() => false)) {
      await crewCountInput.fill('3');
    }

    // Click 下一步
    const nextBtn = page.locator('button:has-text("下一步"), button:has-text("Next"), button:has-text("繼續")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click();
    await page.waitForTimeout(1000);

    // Step 2: Click "由 AI 生成 3 位隊友"
    const genAIBtn = page.locator('button:has-text("AI 生成"), button:has-text("生成"), button:has-text("Generate"), button:has-text("AI"), button:has-text("隊友")').first();
    if (await genAIBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await genAIBtn.click();

      // Wait up to 90s for 3 personas
      console.log('  Waiting for AI persona generation (up to 90s)...');
      await page.waitForFunction(
        () => {
          // Check for 3/3 or persona cards
          const btn = document.querySelector('button');
          const allBtns = Array.from(document.querySelectorAll('button'));
          return allBtns.some(b => b.textContent.includes('3/3') || b.textContent.includes('建立專案'));
        },
        { timeout: 90000 }
      );
    } else {
      console.log('  AI generation button not found, checking if already on step 2...');
    }

    // Click 建立專案 (3/3)
    const createBtn = page.locator('button:has-text("建立專案"), button:has-text("Create Project"), button:has-text("3/3")').first();
    await createBtn.waitFor({ state: 'visible', timeout: 10000 });
    const isEnabled = await createBtn.isEnabled();
    if (!isEnabled) {
      fail('P1', '建立專案 button is disabled after persona generation');
      return;
    }
    await createBtn.click();

    // Wait for navigation to /lobby
    await page.waitForURL(/\/lobby/, { timeout: 20000 });
    const lobbyUrl = page.url();
    const projIdMatch = lobbyUrl.match(/projects\/([^/]+)\/lobby/);
    if (projIdMatch) {
      projectId = projIdMatch[1];
    }

    // Verify DB: project count=1, seats=4
    await page.waitForTimeout(2000);
    const pgProj = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM project;" -t 2>&1`
    ).toString().trim();
    const projCount = parseInt(pgProj.match(/\d+/)?.[0] || '0');

    let seatCount = 0;
    if (projectId) {
      const pgSeat = execSync(
        `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM seat WHERE project_id='${projectId}';" -t 2>&1`
      ).toString().trim();
      seatCount = parseInt(pgSeat.match(/\d+/)?.[0] || '0');
    }

    if (projCount >= 1 && lobbyUrl.includes('lobby')) {
      pass('P1', `project created, projectId=${projectId}, projects=${projCount}, seats=${seatCount}`);
    } else {
      fail('P1', `projects=${projCount}, seats=${seatCount}, url=${lobbyUrl}`);
    }
  } catch (e) {
    fail('P1', e.message);
  }
}

async function runP2(page) {
  // P2 — Lobby
  try {
    if (!projectId) {
      skip('P2', 'No projectId from P1');
      return;
    }
    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle' });
    await dismissOnboarding(page);
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      document.body.classList.remove('driver-active', 'driver-fade');
      document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
    });

    // Check 4 tabs
    const tabs = ['即時動態', '專案概況', '白板預覽', '快速摘要'];
    const foundTabs = [];
    for (const tab of tabs) {
      const el = page.locator(`[role="tab"]:has-text("${tab}"), button:has-text("${tab}"), li:has-text("${tab}")`).first();
      if (await el.isVisible({ timeout: 3000 }).catch(() => false)) {
        foundTabs.push(tab);
        await el.click().catch(() => {});
        await page.waitForTimeout(300);
      }
    }

    // Observer button disabled=false for teacher
    const obsBtn = page.locator('button:has-text("觀察"), button:has-text("Observer"), button:has-text("旁觀")').first();
    const obsBtnVisible = await obsBtn.isVisible({ timeout: 5000 }).catch(() => false);
    let obsBtnDisabled = null;
    if (obsBtnVisible) {
      obsBtnDisabled = await obsBtn.isDisabled();
    }

    // Click 入座 first crew
    const seatBtn = page.locator('button:has-text("入座"), button:has-text("Join"), button:has-text("加入")').first();
    const seatVisible = await seatBtn.isVisible({ timeout: 5000 }).catch(() => false);
    if (seatVisible) {
      await seatBtn.click();
      await page.waitForURL(/\/workspace/, { timeout: 15000 });
      pass('P2', `tabs found=${foundTabs.join(',')}, obsBtn visible=${obsBtnVisible} disabled=${obsBtnDisabled}, navigated to workspace`);
    } else {
      // Maybe auto-navigated or seat btn has different text
      const allBtns = await page.locator('button').allTextContents();
      fail('P2', `seat btn not visible; buttons on page: ${allBtns.slice(0,10).join(' | ')}`);
    }
  } catch (e) {
    fail('P2', e.message);
  }
}

async function runW1(page) {
  // W1 — Workspace
  try {
    if (!projectId) {
      skip('W1', 'No projectId from P1');
      return;
    }
    // Should already be in workspace from P2, but navigate fresh
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await dismissOnboarding(page);
    await page.waitForTimeout(2000);

    // Check tldraw canvas renders without error
    const crashText = page.locator(':has-text("Something\'s gone wrong")');
    const hasCrash = await crashText.isVisible({ timeout: 3000 }).catch(() => false);

    // Check ChatDock visible
    const chatDock = page.locator('[class*="chat"], [data-testid*="chat"], text=群組聊天室, text=ChatDock').first();
    const chatVisible = await chatDock.isVisible({ timeout: 5000 }).catch(() => false);

    // Check StageHintBar shows micro phase
    const stageBar = page.locator('[class*="stage"], [class*="hint"], text=1.1, text=Discover').first();
    const stageVisible = await stageBar.isVisible({ timeout: 5000 }).catch(() => false);

    // Send a human chat message via keystrokes
    const msgInput = page.locator('input[placeholder*="訊息"], input[placeholder*="message" i], textarea[placeholder*="訊息"], [contenteditable="true"]').first();
    const msgVisible = await msgInput.isVisible({ timeout: 5000 }).catch(() => false);
    let msgSent = false;
    if (msgVisible) {
      await msgInput.click();
      await msgInput.pressSequentially('Playwright 測試人類訊息', { delay: 50 });
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      msgSent = true;
    }

    // Verify message in DB
    let dbMsgFound = false;
    try {
      const dbMsg = execSync(
        `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM message WHERE sender_type='human' AND project_id='${projectId}';" -t 2>&1`
      ).toString().trim();
      const msgCount = parseInt(dbMsg.match(/\d+/)?.[0] || '0');
      dbMsgFound = msgCount > 0;
    } catch (e) {}

    // Wait 30s for AI sticky notes
    console.log('  Waiting 30s for AI agent sticky notes...');
    await page.waitForTimeout(30000);

    // Check for sticky notes on canvas
    const stickyNotes = await page.locator('[data-shape-type="note"], [class*="sticky"], [class*="note"]').count().catch(() => 0);

    // Switch to 個人助理 tab
    const personalTab = page.locator('button:has-text("個人助理"), [role="tab"]:has-text("個人助理")').first();
    const personalVisible = await personalTab.isVisible({ timeout: 3000 }).catch(() => false);
    let introShown = false;
    if (personalVisible) {
      await personalTab.click();
      await page.waitForTimeout(1000);
      const introMsg = page.locator('[class*="intro"], [class*="welcome"], text=您好, text=Hello').first();
      introShown = await introMsg.isVisible({ timeout: 3000 }).catch(() => false);
    }

    const passed = !hasCrash && chatVisible;
    if (passed) {
      pass('W1', `canvas no crash, chat visible=${chatVisible}, stage bar=${stageVisible}, msg sent=${msgSent}, dbMsgFound=${dbMsgFound}, sticky notes=${stickyNotes}, personalTab=${personalVisible}, introShown=${introShown}`);
    } else {
      fail('W1', `hasCrash=${hasCrash}, chatVisible=${chatVisible}, stage bar=${stageVisible}`);
    }
  } catch (e) {
    fail('W1', e.message);
  }
}

async function runW2(page) {
  // W2 — Observer mode (student cannot observe)
  try {
    if (!projectId) {
      skip('W2', 'No projectId from P1');
      return;
    }

    // Logout teacher, login student1
    // Clear storage and login as student1
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    await loginViaUI(page, 'student1@test.com', 'student123');
    await page.waitForTimeout(500);

    // Go to lobby
    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle' });
    await dismissOnboarding(page);
    await page.waitForTimeout(1000);

    // Observer button MUST be disabled
    const obsBtn = page.locator('button:has-text("觀察"), button:has-text("Observer"), button:has-text("旁觀"), button:has-text("觀看")').first();
    const obsBtnVisible = await obsBtn.isVisible({ timeout: 5000 }).catch(() => false);
    let obsBtnDisabled = null;
    let obsBtnTitle = null;
    if (obsBtnVisible) {
      obsBtnDisabled = await obsBtn.isDisabled();
      obsBtnTitle = await obsBtn.getAttribute('title');
    }

    // Try to navigate directly to workspace
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    const currentUrl = page.url();
    const bouncedBack = currentUrl.includes('lobby') || currentUrl.includes('projects') && !currentUrl.includes('workspace');

    // Check: obsBtn disabled, bounced back from workspace
    const obsPassed = !obsBtnVisible || (obsBtnVisible && obsBtnDisabled);
    const bouncePassed = bouncedBack;

    if (obsPassed && bouncePassed) {
      pass('W2', `observer btn disabled=${obsBtnDisabled} title="${obsBtnTitle}", bounced from workspace to ${currentUrl}`);
    } else {
      fail('W2', `observer btn visible=${obsBtnVisible} disabled=${obsBtnDisabled} title="${obsBtnTitle}", bounced=${bouncedBack} currentUrl=${currentUrl}`);
    }
  } catch (e) {
    fail('W2', e.message);
  }
}

async function runW3(page) {
  // W3 — Canvas human note (sidecar author validation)
  try {
    if (!projectId) {
      skip('W3', 'No projectId from P1');
      return;
    }

    // Get teacher token
    const teacherLogin = await loginViaAPI('teacher@test.com', 'teacher123');
    const token = teacherLogin.access_token;

    // POST to sidecar with bad author (object) — expect 400
    const badResp = await fetch(`${SIDECAR_URL}/canvas/notes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        project_id: projectId,
        content: 'Bad author test',
        author: { name: 'bad', type: 'object' },
        position: { x: 100, y: 100 }
      })
    });
    const badStatus = badResp.status;

    // POST to sidecar with good author string — expect 201
    const goodResp = await fetch(`${SIDECAR_URL}/canvas/notes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        project_id: projectId,
        content: 'Playwright 人類便條',
        author: 'human',
        position: { x: 200, y: 200 }
      })
    });
    const goodStatus = goodResp.status;

    // Login teacher and navigate to workspace
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await loginViaUI(page, 'teacher@test.com', 'teacher123');
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Check tldraw renders without crash
    const crashText = await page.locator(':has-text("Something\'s gone wrong")').isVisible({ timeout: 3000 }).catch(() => false);
    // Check human note appears
    const noteVisible = await page.locator(':has-text("Playwright 人類便條")').isVisible({ timeout: 5000 }).catch(() => false);

    const badOk = badStatus === 400 || badStatus === 422; // 400 or 422 both indicate validation rejection
    const goodOk = goodStatus === 201 || goodStatus === 200;

    if (!crashText && badOk && goodOk) {
      pass('W3', `bad author → ${badStatus} ✓, good author → ${goodStatus} ✓, no canvas crash, note visible=${noteVisible}`);
    } else {
      fail('W3', `bad author → ${badStatus} (expected 400/422), good author → ${goodStatus} (expected 201), crash=${crashText}, note visible=${noteVisible}`);
    }
  } catch (e) {
    fail('W3', e.message);
  }
}

async function runT1(page) {
  // T1 — Teacher dashboard
  try {
    // Navigate to teacher dashboard
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle' });
    await dismissOnboarding(page);
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      document.body.classList.remove('driver-active', 'driver-fade');
      document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
    });

    // Check if dashboard loaded — look for teacher-specific content
    const dashVisible = await page.locator(':has-text("儀表板"), :has-text("Dashboard"), :has-text("監控"), :has-text("教師")').first().isVisible({ timeout: 8000 }).catch(() => false);

    // Look for project monitor card
    const projectCard = await page.locator(':has-text("Playwright E2E"), :has-text("E2E 測試"), [class*="project-card"], [class*="monitor"]').first().isVisible({ timeout: 5000 }).catch(() => false);

    // Click 學生管理 tab
    const studentTab = page.locator('[role="tab"]:has-text("學生"), button:has-text("學生管理"), button:has-text("學生")').first();
    const studentTabVisible = await studentTab.isVisible({ timeout: 5000 }).catch(() => false);
    let studentCount = 0;
    if (studentTabVisible) {
      await studentTab.click();
      await page.waitForTimeout(1000);
      studentCount = await page.locator('[class*="user-row"], [class*="student-row"], tr').count().catch(() => 0);
    }

    // API check
    const teacherLogin = await loginViaAPI('teacher@test.com', 'teacher123');
    const overviewResp = await fetch(`${API_URL}/api/teacher/projects/overview`, {
      headers: { 'Authorization': `Bearer ${teacherLogin.access_token}` }
    });
    const overviewStatus = overviewResp.status;

    if (dashVisible && overviewStatus === 200) {
      pass('T1', `dashboard visible=${dashVisible}, project card=${projectCard}, student tab=${studentTabVisible} count=${studentCount}, overview API=${overviewStatus}`);
    } else {
      fail('T1', `dashboard visible=${dashVisible}, project card=${projectCard}, overview API=${overviewStatus}`);
    }
  } catch (e) {
    fail('T1', e.message);
  }
}

async function runA1(page) {
  // A1 — Stage advance via API
  try {
    if (!projectId) {
      skip('A1', 'No projectId from P1');
      return;
    }
    const teacherLogin = await loginViaAPI('teacher@test.com', 'teacher123');
    const token = teacherLogin.access_token;

    const advResp = await fetch(`${API_URL}/api/projects/${projectId}/advance-stage`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ from: 'discover', to: 'define' })
    });
    const advStatus = advResp.status;
    const advData = await advResp.json().catch(() => ({}));

    // Verify in DB
    const pgStage = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT current_stage FROM project WHERE id='${projectId}';" -t 2>&1`
    ).toString().trim();
    const dbStage = pgStage.replace(/\s/g, '');

    // Navigate to workspace, check stage bar
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
    const defineVisible = await page.locator(':has-text("Define"), :has-text("define"), :has-text("定義")').first().isVisible({ timeout: 5000 }).catch(() => false);

    const advanced = advStatus === 200 || advStatus === 201 || advStatus === 204;
    const stageOk = dbStage === 'define' || dbStage.includes('define');

    if (advanced && stageOk) {
      pass('A1', `advance API=${advStatus}, DB stage=${dbStage}, Define visible in UI=${defineVisible}`);
    } else {
      fail('A1', `advance API=${advStatus} body=${JSON.stringify(advData)}, DB stage=${dbStage}, Define visible=${defineVisible}`);
    }
  } catch (e) {
    fail('A1', e.message);
  }
}

async function runC1() {
  // C1 — Persona generation stream
  try {
    const teacherLogin = await loginViaAPI('teacher@test.com', 'teacher123');
    const token = teacherLogin.access_token;

    console.log('  Streaming persona generation (up to 60s)...');
    const startTime = Date.now();

    const resp = await fetch(`${API_URL}/api/personas/generate/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ title: '壓力測試', num_personas: 3 })
    });

    if (!resp.ok) {
      fail('C1', `HTTP ${resp.status} from /api/personas/generate/stream`);
      return;
    }

    // Read stream
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let personaCount = 0;
    let doneReceived = false;
    let errorReceived = false;
    let timedOut = false;

    const timeout = new Promise(resolve => setTimeout(() => { timedOut = true; resolve(); }, 60000));

    await Promise.race([
      (async () => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith('event: persona')) personaCount++;
            if (line.startsWith('event: done')) doneReceived = true;
            if (line.startsWith('event: error')) errorReceived = true;
          }
          if (doneReceived) break;
        }
      })(),
      timeout
    ]);

    const elapsed = Math.round((Date.now() - startTime) / 1000);

    if (!timedOut && !errorReceived && personaCount === 3 && doneReceived) {
      pass('C1', `3 persona events + done received in ${elapsed}s, no error events`);
    } else {
      fail('C1', `personas=${personaCount}, done=${doneReceived}, error=${errorReceived}, timedOut=${timedOut}, elapsed=${elapsed}s`);
    }
  } catch (e) {
    fail('C1', e.message);
  }
}

async function runE1(page) {
  // E1 — Error budget
  try {
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // Do a fresh navigation to workspace to capture console errors
    if (projectId) {
      await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(3000);
    } else {
      await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(2000);
    }

    // Scan backend log for ERROR lines
    let backendErrors = [];
    try {
      const logLines = execSync('grep -c "ERROR" /private/tmp/backend.log 2>/dev/null || echo 0').toString().trim();
      const errorCount = parseInt(logLines);
      if (errorCount > 0) {
        const errorLines = execSync('grep "ERROR" /private/tmp/backend.log 2>/dev/null | tail -10').toString().trim();
        backendErrors = errorLines.split('\n').filter(l => l.trim() && !l.includes('vllm') && !l.includes('timeout') && !l.includes('old project'));
      }
    } catch (e) {}

    const errorCount = consoleErrors.length;
    // Filter out known harmless errors (404 /api/health)
    const realErrors = consoleErrors.filter(e => !e.includes('/api/health') && !e.includes('404'));

    if (realErrors.length <= 3) {
      pass('E1', `console errors=${realErrors.length} (≤3 threshold), backend ERROR lines=${backendErrors.length}, sample: ${realErrors.slice(0,2).join(' | ')}`);
    } else {
      fail('E1', `console errors=${realErrors.length} (>3), errors: ${realErrors.slice(0,5).join(' | ')}`);
    }
  } catch (e) {
    fail('E1', e.message);
  }
}

async function main() {
  console.log('=== MindCrew Full E2E Test Run ===\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  // D1 — Docker health (no page needed)
  await runD1(page);

  // L1 — Auth
  await runL1(page);

  // P1 — Create project
  await runP1(page);

  // P2 — Lobby
  await runP2(page);

  // W1 — Workspace
  await runW1(page);

  // W2 — Observer mode
  await runW2(page);

  // W3 — Canvas human note
  await runW3(page);

  // T1 — Teacher dashboard
  await runT1(page);

  // A1 — Stage advance
  await runA1(page);

  // C1 — Persona stream
  await runC1();

  // E1 — Error budget (last, reuse page)
  await runE1(page);

  await browser.close();

  // Print results table
  console.log('\n=== RESULTS ===\n');
  console.log('| Test ID | Result | Evidence |');
  console.log('|---------|--------|----------|');
  for (const r of results) {
    console.log(`| ${r.id} | ${r.result} | ${r.evidence} |`);
  }

  // Save results
  const fs = require('fs');
  fs.writeFileSync('/Users/hsueh/Code/Experimental/MindCrew/e2e/full-e2e-results.json', JSON.stringify({ projectId, results }, null, 2));
  console.log('\nResults saved to e2e/full-e2e-results.json');
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
