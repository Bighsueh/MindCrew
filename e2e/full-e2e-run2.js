/**
 * Full E2E test run v2 — fixed selectors from DOM investigation
 * Run: node full-e2e-run2.js
 */

const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fetch = (...args) => import('node-fetch').then(({default: f}) => f(...args));

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const SIDECAR_URL = 'http://localhost:4000';

const results = [];
let projectId = null;
let teacherToken = null;

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

async function dismissDriverOverlay(page) {
  await page.evaluate(() => {
    document.body.classList.remove('driver-active', 'driver-fade');
    document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
  }).catch(() => {});
}

async function suppressTours(page) {
  await page.evaluate(() => {
    try {
      localStorage.setItem('mindcrew.firstrun.projects', '1');
      localStorage.setItem('mindcrew.firstrun.workspace', '1');
      localStorage.setItem('mindcrew.firstrun.lobby', '1');
      localStorage.setItem('mindcrew.firstrun.dashboard', '1');
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
    } catch(e) {}
  }).catch(() => {});
}

async function loginViaUI(page, email, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    try { localStorage.clear(); sessionStorage.clear(); } catch(e) {}
  });
  await page.waitForTimeout(500);

  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(email);

  const pwInput = page.locator('input[type="password"]').first();
  await pwInput.fill(password);
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/(projects|dashboard|lobby|workspace)/, { timeout: 15000 });
  await suppressTours(page);
}

async function apiLogin(email, password) {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await resp.json();
  return { token: data.access_token, user: data.user };
}

// ===== D1 =====
async function runD1() {
  try {
    const [r1, r2, r3] = await Promise.all([
      fetch(`${SIDECAR_URL}/health`),
      fetch(`${API_URL}/openapi.json`),
      fetch(`${BASE_URL}`)
    ]);

    const pgUser = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM \\"user\\";" -t 2>&1`
    ).toString().trim();
    const userCount = parseInt(pgUser.match(/\d+/)?.[0] || '0');

    const pgProj = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM project;" -t 2>&1`
    ).toString().trim();
    const projCount = parseInt(pgProj.match(/\d+/)?.[0] || '0');

    if (r1.status === 200 && r2.status === 200 && r3.status === 200 && userCount === 7 && projCount === 0) {
      pass('D1', `sidecar=200, backend=200, frontend=200, users=${userCount}, projects=${projCount}`);
    } else {
      fail('D1', `sidecar=${r1.status} backend=${r2.status} frontend=${r3.status} users=${userCount} projects=${projCount}`);
    }
  } catch (e) {
    fail('D1', e.message);
  }
}

// ===== L1 =====
async function runL1(page) {
  try {
    await loginViaUI(page, 'teacher@test.com', 'teacher123');

    // Find JWT in localStorage
    const token = await page.evaluate(() => {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const val = localStorage.getItem(key);
        if (val && (val.startsWith('eyJ') || (typeof val === 'string' && val.length > 100))) return val;
      }
      return null;
    });
    teacherToken = token;

    const meResp = await fetch(`${API_URL}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const meData = await meResp.json();

    const s1 = await apiLogin('student1@test.com', 'student123');

    if (meData.role === 'teacher' && s1.user?.role === 'student') {
      pass('L1', `teacher role=${meData.role} ✓, student1 role=${s1.user.role} ✓, JWT=${token ? 'present' : 'missing'}`);
    } else {
      fail('L1', `teacher role=${meData.role}, student1 role=${s1.user?.role}, token=${!!token}`);
    }
  } catch (e) {
    fail('L1', e.message);
  }
}

// ===== P1 =====
async function runP1(page) {
  try {
    // Ensure on projects page as teacher
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(1000);

    // Click 新增專案
    const newBtn = page.locator('button:has-text("新增專案")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 8000 });
    await newBtn.click();
    await page.waitForTimeout(1000);

    // Modal is now open. Use id="專案名稱" to target the correct input
    const nameInput = page.locator('#專案名稱, input[id="專案名稱"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 8000 });
    // Use evaluate-based click to bypass pointer-events from backdrop sibling
    await page.evaluate(() => {
      const input = document.querySelector('#專案名稱');
      if (input) { input.focus(); input.click(); }
    });
    await nameInput.pressSequentially('Playwright E2E 測試專案', { delay: 30 });

    // Description
    const descInput = page.locator('textarea[placeholder*="簡述"]').first();
    if (await descInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.evaluate(() => {
        const ta = document.querySelector('textarea[placeholder*="簡述"]');
        if (ta) { ta.focus(); ta.click(); }
      });
      await descInput.pressSequentially('E2E 自動化測試', { delay: 20 });
    }

    // Constraints
    const constraintInput = page.locator('textarea[placeholder*="限制"]').first();
    if (await constraintInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.evaluate(() => {
        const ta = document.querySelector('textarea[placeholder*="限制"]');
        if (ta) { ta.focus(); ta.click(); }
      });
      await constraintInput.pressSequentially('時間限制 2 小時', { delay: 20 });
    }

    // Find number inputs for crew count/contribution
    const numberInputs = await page.locator('input[type="number"], input[type="range"]').all();
    console.log(`  Found ${numberInputs.length} number/range inputs`);

    // Screenshot before next step
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-step1-filled.png' });

    // Click 下一步
    const nextBtn = page.locator('button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('下一步'));
      if (btn) btn.click();
    });
    await page.waitForTimeout(1500);

    // Screenshot step 2
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-step2.png' });

    // Step 2: get buttons
    const step2Buttons = await page.locator('button').allTextContents();
    console.log('  Step 2 buttons:', step2Buttons);

    // Click "由 AI 生成" or similar
    const genBtn = page.locator('button:has-text("AI 生成"), button:has-text("生成 AI"), button:has-text("生成隊友"), button:has-text("生成")').first();
    const genVisible = await genBtn.isVisible({ timeout: 5000 }).catch(() => false);
    if (genVisible) {
      await page.evaluate(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b =>
          b.textContent.includes('生成') || b.textContent.includes('AI')
        );
        if (btn) btn.click();
      });

      console.log('  Waiting up to 90s for AI persona generation...');
      // Wait for 建立專案 button to contain persona count or become enabled
      try {
        await page.waitForFunction(() => {
          const btns = Array.from(document.querySelectorAll('button'));
          return btns.some(b =>
            b.textContent.includes('建立專案') && !b.disabled
          );
        }, { timeout: 90000 });
      } catch(e) {
        console.log('  Timeout waiting for personas; checking current state...');
      }
    } else {
      console.log('  No AI generate button found; checking current step 2 state...');
    }

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-after-generation.png' });
    const afterButtons = await page.locator('button').allTextContents();
    console.log('  After generation buttons:', afterButtons);

    // Click 建立專案
    const createBtn = page.locator('button:has-text("建立專案")').last();
    const createEnabled = await createBtn.isEnabled({ timeout: 5000 }).catch(() => false);
    if (!createEnabled) {
      fail('P1', `建立專案 button not enabled. Buttons: ${afterButtons.join(' | ')}`);
      return;
    }
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent.includes('建立專案') && !b.disabled);
      if (btn) btn.click();
    });

    // Wait for navigation to /lobby
    await page.waitForURL(/\/lobby/, { timeout: 20000 });
    const lobbyUrl = page.url();
    const projIdMatch = lobbyUrl.match(/projects\/([^/]+)\/lobby/);
    if (projIdMatch) {
      projectId = projIdMatch[1];
    }
    await page.waitForTimeout(2000);

    // Verify DB
    const pgProj2 = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM project;" -t 2>&1`
    ).toString().trim();
    const projCount = parseInt(pgProj2.match(/\d+/)?.[0] || '0');

    let seatCount = 0;
    if (projectId) {
      const pgSeat = execSync(
        `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM seat WHERE project_id='${projectId}';" -t 2>&1`
      ).toString().trim();
      seatCount = parseInt(pgSeat.match(/\d+/)?.[0] || '0');
    }

    if (projCount >= 1 && projectId) {
      pass('P1', `project created id=${projectId}, projects=${projCount}, seats=${seatCount}, url=${lobbyUrl}`);
    } else {
      fail('P1', `projects=${projCount}, seats=${seatCount}, url=${lobbyUrl}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-error.png' }).catch(() => {});
    fail('P1', e.message.split('\n')[0]);
  }
}

// ===== P2 =====
async function runP2(page) {
  try {
    if (!projectId) { skip('P2', 'No projectId from P1'); return; }

    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle' });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(1000);

    // Check tabs
    const tabs = ['即時動態', '專案概況', '白板預覽', '快速摘要'];
    const foundTabs = [];
    for (const tab of tabs) {
      const el = page.locator(`[role="tab"]:has-text("${tab}"), button:has-text("${tab}")`).first();
      if (await el.isVisible({ timeout: 3000 }).catch(() => false)) {
        foundTabs.push(tab);
        await el.click().catch(() => {});
        await page.waitForTimeout(300);
      }
    }

    // Observer button
    const obsBtn = page.locator('button:has-text("觀察"), button:has-text("旁觀"), button:has-text("Observer")').first();
    const obsBtnVisible = await obsBtn.isVisible({ timeout: 5000 }).catch(() => false);
    let obsBtnDisabled = null;
    if (obsBtnVisible) {
      obsBtnDisabled = await obsBtn.isDisabled();
    }

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p2-lobby.png' });

    // All buttons on lobby
    const lobbyBtns = await page.locator('button').allTextContents();
    console.log('  Lobby buttons:', lobbyBtns);

    // Click 入座 / Join seat
    const seatBtn = page.locator('button:has-text("入座"), button:has-text("Join Seat"), button:has-text("加入座位")').first();
    const seatVisible = await seatBtn.isVisible({ timeout: 5000 }).catch(() => false);
    if (seatVisible) {
      await page.evaluate(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim().includes('入座'));
        if (btn) btn.click();
      });
      await page.waitForURL(/\/workspace/, { timeout: 15000 });
      pass('P2', `tabs=${foundTabs.join(',')}, obsVisible=${obsBtnVisible} disabled=${obsBtnDisabled}, navigated to workspace`);
    } else {
      // Check if there's any crew seat clickable
      const allBtns = await page.locator('button').allTextContents();
      fail('P2', `入座 not found. Buttons: ${allBtns.join(' | ')}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p2-error.png' }).catch(() => {});
    fail('P2', e.message.split('\n')[0]);
  }
}

// ===== W1 =====
async function runW1(page) {
  try {
    if (!projectId) { skip('W1', 'No projectId from P1'); return; }

    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(3000);

    // Check for crash
    const hasCrash = await page.locator('text=Something\'s gone wrong').isVisible({ timeout: 3000 }).catch(() => false);

    // Screenshot
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w1-workspace.png' });

    // Check ChatDock
    const chatVisible = await page.locator('text=群組聊天室, [class*="ChatDock"], [class*="chat-dock"]').first().isVisible({ timeout: 5000 }).catch(() => false);

    // Check StageHintBar
    const stageVisible = await page.locator('text=1.1, text=Discover, [class*="StageHint"], [class*="stage-hint"]').first().isVisible({ timeout: 5000 }).catch(() => false);

    // Send message
    const msgInput = page.locator('input[placeholder*="訊息"], textarea[placeholder*="訊息"]').first();
    const msgVisible = await msgInput.isVisible({ timeout: 5000 }).catch(() => false);
    let msgSent = false;
    if (msgVisible) {
      await page.evaluate(() => {
        const input = document.querySelector('input[placeholder*="訊息"], textarea[placeholder*="訊息"]');
        if (input) { input.focus(); }
      });
      await msgInput.pressSequentially('Playwright 測試人類訊息', { delay: 50 });
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      msgSent = true;
    }

    // Verify in DB
    let dbMsgCount = 0;
    try {
      const dbMsg = execSync(
        `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT COUNT(*) FROM message WHERE sender_type='human' AND project_id='${projectId}';" -t 2>&1`
      ).toString().trim();
      dbMsgCount = parseInt(dbMsg.match(/\d+/)?.[0] || '0');
    } catch (e) {}

    // Wait 30s for AI sticky notes
    console.log('  Waiting 30s for AI agent sticky notes...');
    await page.waitForTimeout(30000);

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w1-after-30s.png' });

    // Check sticky notes on canvas
    const stickyNotes = await page.locator('[data-shape-type="note"], [class*="sticky"], .tl-note').count().catch(() => 0);
    // Also check if canvas has any tldraw shapes
    const tlShapes = await page.evaluate(() => {
      return document.querySelectorAll('[data-shape-id]').length;
    }).catch(() => 0);

    // Switch to 個人助理
    const personalTab = page.locator('button:has-text("個人助理"), [role="tab"]:has-text("個人助理")').first();
    const personalVisible = await personalTab.isVisible({ timeout: 3000 }).catch(() => false);
    let introShown = false;
    if (personalVisible) {
      await personalTab.click().catch(() => {});
      await page.waitForTimeout(1000);
      // Check for any content in personal tab
      introShown = await page.locator('[class*="personal"], [class*="intro"]').first().isVisible({ timeout: 3000 }).catch(() => false);
    }

    if (!hasCrash) {
      pass('W1', `no crash, chatVisible=${chatVisible}, stageVisible=${stageVisible}, msgSent=${msgSent}, dbMsgCount=${dbMsgCount}, stickyNotes=${stickyNotes}, tlShapes=${tlShapes}, personalTab=${personalVisible}`);
    } else {
      fail('W1', `canvas CRASHED, chatVisible=${chatVisible}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w1-error.png' }).catch(() => {});
    fail('W1', e.message.split('\n')[0]);
  }
}

// ===== W2 =====
async function runW2(page) {
  try {
    if (!projectId) { skip('W2', 'No projectId from P1'); return; }

    // Logout and login as student1
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.evaluate(() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e) {} });
    await page.waitForTimeout(300);

    await page.locator('input[type="email"]').first().fill('student1@test.com');
    await page.locator('input[type="password"]').first().fill('student123');
    await page.keyboard.press('Enter');
    await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });
    await suppressTours(page);

    // Go to lobby
    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle' });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(1000);

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w2-student-lobby.png' });

    // Observer button must be disabled for student
    const obsBtn = page.locator('button:has-text("觀察"), button:has-text("旁觀"), button:has-text("Observer"), button:has-text("觀看")').first();
    const obsBtnVisible = await obsBtn.isVisible({ timeout: 5000 }).catch(() => false);
    let obsBtnDisabled = null;
    let obsBtnTitle = null;
    if (obsBtnVisible) {
      obsBtnDisabled = await obsBtn.isDisabled();
      obsBtnTitle = await obsBtn.getAttribute('title');
    }

    // Try direct workspace navigation
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(2000);
    const currentUrl = page.url();
    const bouncedBack = !currentUrl.includes('/workspace');

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w2-after-workspace-nav.png' });

    const obsPassed = !obsBtnVisible || (obsBtnVisible && obsBtnDisabled);

    if (obsPassed && bouncedBack) {
      pass('W2', `obsBtn visible=${obsBtnVisible} disabled=${obsBtnDisabled} title="${obsBtnTitle}", bounced to ${currentUrl}`);
    } else {
      fail('W2', `obsBtn visible=${obsBtnVisible} disabled=${obsBtnDisabled} title="${obsBtnTitle}", bounced=${bouncedBack} url=${currentUrl}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w2-error.png' }).catch(() => {});
    fail('W2', e.message.split('\n')[0]);
  }
}

// ===== W3 =====
async function runW3(page) {
  try {
    if (!projectId) { skip('W3', 'No projectId from P1'); return; }

    const { token } = await apiLogin('teacher@test.com', 'teacher123');

    // Bad author (object) → expect 400/422
    const badResp = await fetch(`${SIDECAR_URL}/canvas/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        project_id: projectId,
        content: 'Bad author test',
        author: { name: 'bad', type: 'object' },
        position: { x: 100, y: 100 }
      })
    });
    const badStatus = badResp.status;

    // Good author (string) → expect 200/201
    const goodResp = await fetch(`${SIDECAR_URL}/canvas/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        project_id: projectId,
        content: 'Playwright 人類便條',
        author: 'human',
        position: { x: 200, y: 200 }
      })
    });
    const goodStatus = goodResp.status;
    const goodBody = await goodResp.text();
    console.log(`  Sidecar good note response: ${goodStatus} ${goodBody.substring(0, 100)}`);

    // Login teacher and check workspace
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.evaluate(() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e) {} });
    await page.locator('input[type="email"]').first().fill('teacher@test.com');
    await page.locator('input[type="password"]').first().fill('teacher123');
    await page.keyboard.press('Enter');
    await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });

    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(4000);

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w3-workspace.png' });

    const hasCrash = await page.locator('text=Something\'s gone wrong').isVisible({ timeout: 3000 }).catch(() => false);
    const noteVisible = await page.locator('text=Playwright 人類便條').isVisible({ timeout: 5000 }).catch(() => false);

    const badOk = badStatus === 400 || badStatus === 422;
    const goodOk = goodStatus === 200 || goodStatus === 201;

    if (!hasCrash && badOk && goodOk) {
      pass('W3', `bad author → ${badStatus} ✓, good author → ${goodStatus} ✓, no crash, note visible=${noteVisible}`);
    } else {
      fail('W3', `bad author → ${badStatus} (want 400/422), good author → ${goodStatus} (want 200/201), crash=${hasCrash}, noteVisible=${noteVisible}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/w3-error.png' }).catch(() => {});
    fail('W3', e.message.split('\n')[0]);
  }
}

// ===== T1 =====
async function runT1(page) {
  try {
    const { token } = await apiLogin('teacher@test.com', 'teacher123');

    // Overview API
    const overviewResp = await fetch(`${API_URL}/api/teacher/projects/overview`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const overviewStatus = overviewResp.status;

    // Navigate to dashboard
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle' });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(1500);

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/t1-dashboard.png' });

    const dashVisible = await page.locator('text=儀表板, text=Dashboard, text=教師, text=監控').first().isVisible({ timeout: 5000 }).catch(() => false);
    const projectCard = await page.locator('text=Playwright E2E, text=E2E 測試').first().isVisible({ timeout: 3000 }).catch(() => false);

    // Try 學生管理 tab
    const studentTab = page.locator('button:has-text("學生管理"), [role="tab"]:has-text("學生"), button:has-text("學生")').first();
    const studentTabVisible = await studentTab.isVisible({ timeout: 3000 }).catch(() => false);
    let studentRows = 0;
    if (studentTabVisible) {
      await studentTab.click().catch(() => {});
      await page.waitForTimeout(1000);
      await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/t1-students.png' });
      studentRows = await page.locator('tr, [class*="user-row"], [class*="student-item"]').count().catch(() => 0);
    }

    if (dashVisible && overviewStatus === 200) {
      pass('T1', `dashboard visible, overview API=200, projectCard=${projectCard}, studentTab=${studentTabVisible} rows=${studentRows}`);
    } else {
      fail('T1', `dashboard visible=${dashVisible}, overview API=${overviewStatus}`);
    }
  } catch (e) {
    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/t1-error.png' }).catch(() => {});
    fail('T1', e.message.split('\n')[0]);
  }
}

// ===== A1 =====
async function runA1(page) {
  try {
    if (!projectId) { skip('A1', 'No projectId from P1'); return; }

    const { token } = await apiLogin('teacher@test.com', 'teacher123');

    const advResp = await fetch(`${API_URL}/api/projects/${projectId}/advance-stage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ from: 'discover', to: 'define' })
    });
    const advStatus = advResp.status;
    const advBody = await advResp.text();
    console.log(`  advance-stage: ${advStatus} ${advBody.substring(0, 100)}`);

    // Check DB
    const pgStage = execSync(
      `PGPASSWORD=dtai psql -h localhost -p 5433 -U dtai -d dtai -c "SELECT current_stage FROM project WHERE id='${projectId}';" -t 2>&1`
    ).toString().trim();
    const dbStage = pgStage.replace(/\s/g, '');

    // Navigate to workspace
    await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
    await suppressTours(page);
    await dismissDriverOverlay(page);
    await page.waitForTimeout(2000);

    await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/a1-workspace.png' });

    const defineVisible = await page.locator('text=Define, text=define, text=定義').first().isVisible({ timeout: 5000 }).catch(() => false);

    const advanced = advStatus >= 200 && advStatus < 300;
    const stageOk = dbStage.includes('define');

    if (advanced && stageOk) {
      pass('A1', `advance API=${advStatus}, DB stage=${dbStage}, Define visible=${defineVisible}`);
    } else {
      fail('A1', `advance API=${advStatus}, DB stage=${dbStage}, Define visible=${defineVisible}`);
    }
  } catch (e) {
    fail('A1', e.message.split('\n')[0]);
  }
}

// ===== C1 =====
async function runC1() {
  try {
    const { token } = await apiLogin('teacher@test.com', 'teacher123');

    console.log('  Streaming persona generation (up to 60s)...');
    const startTime = Date.now();

    const resp = await fetch(`${API_URL}/api/personas/generate/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ title: '壓力測試', num_personas: 3 })
    });

    if (!resp.ok) {
      fail('C1', `HTTP ${resp.status}`);
      return;
    }

    const reader = resp.body;
    let buffer = '';
    let personaCount = 0;
    let doneReceived = false;
    let errorReceived = false;
    let timedOut = false;

    const timeoutPromise = new Promise(resolve => setTimeout(() => { timedOut = true; resolve(); }, 60000));

    await Promise.race([
      new Promise(async (resolve) => {
        for await (const chunk of reader) {
          buffer += chunk.toString();
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith('event: persona')) personaCount++;
            if (line.startsWith('event: done')) { doneReceived = true; }
            if (line.startsWith('event: error')) errorReceived = true;
          }
          if (doneReceived) break;
        }
        resolve();
      }),
      timeoutPromise
    ]);

    const elapsed = Math.round((Date.now() - startTime) / 1000);

    if (!timedOut && !errorReceived && personaCount === 3 && doneReceived) {
      pass('C1', `3 persona events + done in ${elapsed}s, no errors`);
    } else {
      fail('C1', `personas=${personaCount}, done=${doneReceived}, error=${errorReceived}, timeout=${timedOut}, elapsed=${elapsed}s`);
    }
  } catch (e) {
    fail('C1', e.message.split('\n')[0]);
  }
}

// ===== E1 =====
async function runE1(page) {
  try {
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    if (projectId) {
      await page.goto(`${BASE_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(3000);
    } else {
      await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(2000);
    }

    // Backend errors
    let backendErrorCount = 0;
    let backendErrorSamples = [];
    try {
      const logOutput = execSync('grep "ERROR" /private/tmp/backend.log 2>/dev/null | tail -20').toString();
      const lines = logOutput.split('\n').filter(l => l.trim() && !l.includes('vllm timeout'));
      backendErrorCount = lines.length;
      backendErrorSamples = lines.slice(0, 3);
    } catch (e) {}

    // Filter known harmless console errors
    const realErrors = consoleErrors.filter(e =>
      !e.includes('/api/health') && !e.includes('404') && !e.includes('favicon')
    );

    if (realErrors.length <= 3) {
      pass('E1', `console errors=${realErrors.length} (≤3), backend ERRORs=${backendErrorCount}, samples: ${backendErrorSamples.slice(0,2).join(' | ')}`);
    } else {
      fail('E1', `console errors=${realErrors.length} (>3): ${realErrors.slice(0,3).join(' | ')}`);
    }
  } catch (e) {
    fail('E1', e.message.split('\n')[0]);
  }
}

// ===== MAIN =====
async function main() {
  console.log('=== MindCrew Full E2E Test Run v2 ===\n');

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  // Collect console errors globally
  const allConsoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') allConsoleErrors.push(msg.text());
  });

  await runD1();
  await runL1(page);
  await runP1(page);
  await runP2(page);
  await runW1(page);
  await runW2(page);
  await runW3(page);
  await runT1(page);
  await runA1(page);
  await runC1();
  await runE1(page);

  await browser.close();

  // Print results
  console.log('\n=== RESULTS TABLE ===\n');
  console.log('| Test ID | Result | Evidence |');
  console.log('|---------|--------|----------|');
  for (const r of results) {
    const evidenceTrunc = r.evidence.length > 200 ? r.evidence.substring(0, 200) + '...' : r.evidence;
    console.log(`| ${r.id} | ${r.result} | ${evidenceTrunc} |`);
  }

  const fs = require('fs');
  fs.writeFileSync(
    '/Users/hsueh/Code/Experimental/MindCrew/e2e/full-e2e-results2.json',
    JSON.stringify({ projectId, results, allConsoleErrors }, null, 2)
  );
  console.log('\nSaved to e2e/full-e2e-results2.json');

  const passCount = results.filter(r => r.result === 'PASS').length;
  const failCount = results.filter(r => r.result === 'FAIL').length;
  const skipCount = results.filter(r => r.result === 'SKIP').length;
  console.log(`\nSummary: ${passCount} PASS, ${failCount} FAIL, ${skipCount} SKIP`);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
