/**
 * QA E2E Test: Supervisor Role (組長) Full Journey
 * Tests Create Project → Join as Supervisor → Discover → Define → Develop → Deliver
 *
 * Routes:
 *   /projects          — project list
 *   /projects/:id/lobby     — lobby (seat selection)
 *   /projects/:id/workspace — workspace (canvas + chat)
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

const CREDS = { email: 'teacher@test.com', password: 'teacher123' };

// Unique name per run to avoid reusing old projects
const RUN_ID = Date.now();
const PROJECT_DATA = {
  name: `QA驗證-超市購物車重新設計-組長測試-${RUN_ID}`,
  description: '超市購物車的重新設計。設計限制：寬度≤60cm、嵌套堆疊、手把高度95-105cm、滿載推行力<5kg、量產成本≤NT$3000、可回收材質≥80%',
  aiContribution: 'high',
};

const bugs = [];
let authToken = '';
let projectId = '';
const consoleErrors = [];
const networkErrors = [];

function recordBug(id, severity, description, stepsToReproduce, expected, actual, screenshot = null) {
  const bug = { id, severity, description, stepsToReproduce, expected, actual, screenshot, timestamp: new Date().toISOString() };
  bugs.push(bug);
  console.log(`\n[BUG FOUND] ${id} [${severity}]: ${description}`);
  console.log(`  Expected: ${expected}`);
  console.log(`  Actual: ${actual}`);
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `qa1-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  Screenshot: qa1-${name}.png`);
  return filepath;
}

async function apiRequest(method, endpoint, body = null) {
  const opts = {
    method,
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${endpoint}`, opts);
  if (!res.ok) {
    const text = await res.text();
    console.log(`  API ${method} ${endpoint} => ${res.status}: ${text.slice(0, 100)}`);
    return null;
  }
  return res.json();
}

async function apiGet(endpoint) { return apiRequest('GET', endpoint); }
async function apiPost(endpoint, body) { return apiRequest('POST', endpoint, body); }

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log('='.repeat(60));
  console.log('MindCrew E2E QA: Supervisor Role Full Journey');
  console.log('='.repeat(60));

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ text: msg.text(), url: msg.location()?.url || '' });
    }
  });
  page.on('requestfailed', req => {
    networkErrors.push({ url: req.url(), method: req.method(), failure: req.failure()?.errorText });
  });

  try {
    // =============================================
    // STEP 1: AUTH
    // =============================================
    console.log('\n[STEP 1] Authenticating...');
    const loginData = await apiPost('/api/auth/login', CREDS);
    if (!loginData?.access_token) throw new Error('Login failed');
    authToken = loginData.access_token;
    console.log('  User:', loginData.user.display_name);

    // =============================================
    // STEP 2: BROWSER LOGIN
    // =============================================
    console.log('\n[STEP 2] Browser login...');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await screenshot(page, '01-login-page');

    await page.locator('input[type="email"]').fill(CREDS.email);
    await page.locator('input[type="password"]').fill(CREDS.password);
    await screenshot(page, '02-login-filled');
    await page.locator('button[type="submit"]').click();

    await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });
    await page.waitForLoadState('networkidle');
    await screenshot(page, '03-after-login');
    console.log('  Login OK. URL:', page.url());

    // =============================================
    // STEP 3: CREATE PROJECT
    // =============================================
    console.log('\n[STEP 3] Creating project...');
    await page.goto(`${BASE_URL}/projects`);
    await page.waitForLoadState('networkidle');
    await screenshot(page, '04-projects-page');

    // Check 新增專案 button
    const newProjBtn = page.locator('button').filter({ hasText: '新增專案' });
    const newProjBtnCount = await newProjBtn.count();
    console.log(`  Found ${newProjBtnCount} "新增專案" button(s)`);

    if (newProjBtnCount === 0) {
      const allBtns = await page.locator('button').allTextContents();
      recordBug('BUG-001', 'HIGH', '"新增專案" button not found on projects page',
        '1. Login 2. Navigate to /projects',
        'Button with text "新增專案" should be visible',
        `Not found. Available buttons: ${allBtns.slice(0, 6).join(', ')}`);
    } else {
      await newProjBtn.first().click();
      await sleep(800);
      await screenshot(page, '05-after-btn-click');

      // Verify dialog opened
      const dialogVisible = await page.locator('[role="dialog"]').isVisible().catch(() => false);
      if (!dialogVisible) {
        recordBug('BUG-002', 'HIGH', 'Create project dialog did not open after button click',
          '1. Click "新增專案"',
          'Dialog should appear',
          'Dialog not visible');
        await screenshot(page, '05-no-dialog-bug');
      } else {
        console.log('  Dialog opened');
      }
    }

    // =============================================
    // STEP 4: FILL FORM
    // =============================================
    console.log('\n[STEP 4] Filling create project form...');

    const nameInput = page.locator('input[placeholder*="校園永續"]');
    const nameVisible = await nameInput.isVisible().catch(() => false);

    if (!nameVisible) {
      recordBug('BUG-FORM-1', 'CRITICAL', 'Project name input not found in dialog',
        '1. Open create dialog',
        'Name input should be visible',
        'Input not found');
    } else {
      await nameInput.click();
      await nameInput.fill(PROJECT_DATA.name);
      const val = await nameInput.inputValue();
      console.log(`  Name input value: "${val.slice(0, 40)}..."`);
      if (!val) {
        recordBug('BUG-FORM-2', 'CRITICAL', 'Project name field does not retain typed value',
          '1. Open create dialog 2. Type in name field',
          'Field should retain typed value',
          'Field value is empty after fill');
      }
    }

    // Fill description
    const descTA = page.locator('[role="dialog"] textarea');
    if (await descTA.isVisible().catch(() => false)) {
      await descTA.fill(PROJECT_DATA.description);
      console.log('  Description filled');
    }

    // Select "高" AI contribution
    const highBtn = page.locator('[role="dialog"] button').filter({ hasText: '高' });
    if (await highBtn.isVisible().catch(() => false)) {
      await highBtn.click();
      console.log('  AI contribution set to 高');
    }

    await screenshot(page, '06-form-filled');

    // Submit
    await page.locator('[role="dialog"] button').filter({ hasText: '建立專案' }).click();
    await sleep(3000);
    await screenshot(page, '07-after-submit');

    // Check result
    const dialogAfter = await page.locator('[role="dialog"]').isVisible().catch(() => false);
    if (dialogAfter) {
      const errMsg = await page.locator('[role="dialog"]').locator('[class*="error"], [class*="text-error"]').textContent().catch(() => '');
      const nameVal = await nameInput.inputValue().catch(() => '');
      console.log(`  Dialog still open after submit. Error: "${errMsg}". Name value: "${nameVal.slice(0, 40)}"`);
      if (errMsg.includes('請輸入專案名稱') || !nameVal) {
        recordBug('BUG-FORM-3', 'CRITICAL', 'Project name field was empty despite fill — validation error shown',
          '1. Open create dialog 2. Fill name 3. Submit',
          'Project should be created',
          `Validation error shown: "${errMsg}". Name was empty.`);
      }
    }

    // After submit, check URL first (fast path), then fall back to API
    await sleep(2000);
    const urlAfterSubmit = page.url();
    const urlProjMatch = urlAfterSubmit.match(/\/projects\/([a-f0-9-]{36})/);
    if (urlProjMatch) {
      projectId = urlProjMatch[1];
      console.log('  Project created — ID from URL:', projectId);
    } else {
      // Look in API by exact name (name is unique per run due to timestamp)
      const allProjects = await apiGet('/api/projects');
      const qaProject = allProjects?.find(p => p.name === PROJECT_DATA.name);
      if (qaProject) {
        projectId = qaProject.id;
        console.log('  Project found in API by name. ID:', projectId);
      } else {
        throw new Error(`Project "${PROJECT_DATA.name}" not found in API after creation`);
      }
    }

    // =============================================
    // STEP 5: JOIN AS SUPERVISOR via Lobby UI
    // =============================================
    console.log('\n[STEP 5] Navigating to project lobby...');
    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(1500);
    await screenshot(page, '08-lobby');
    console.log('  Lobby URL:', page.url());

    // Look for 入座 buttons
    const inzuoButtons = page.locator('button').filter({ hasText: '入座' });
    const inzuoCount = await inzuoButtons.count();
    console.log(`  Found ${inzuoCount} "入座" buttons`);

    if (inzuoCount === 0) {
      const allBtns = await page.locator('button').allTextContents();
      recordBug('BUG-005', 'CRITICAL', 'No 入座 buttons found in project lobby',
        '1. Create project 2. Navigate to /projects/:id/lobby',
        'Should see 入座 buttons for seat selection',
        `No 入座 buttons. Available: ${allBtns.slice(0, 8).join(', ')}`);
      await screenshot(page, '08-no-seats-bug');
    } else {
      // The lobby renders SupervisorRow first, then CrewRows.
      // Supervisor "入座" button is always the FIRST button.
      // (SeatAction only renders button if seat is AI-occupied)
      console.log('  Clicking first 入座 button (supervisor seat)...');
      await inzuoButtons.first().click();
      console.log('  Clicked 入座 (supervisor = first button)');
      await sleep(3000);
      await page.waitForLoadState('networkidle');
      await screenshot(page, '09-after-join');
      console.log('  After join URL:', page.url());
    }

    // Verify we're in workspace
    const wsUrl = page.url();
    if (!wsUrl.includes('/workspace')) {
      console.log('  Not in workspace. Checking seat then navigating...');
      // Check our seat via API
      const seatsData = await apiGet(`/api/projects/${projectId}/seats`);
      const mySeat = seatsData?.find(s => s.user_id === loginData.user.id);
      console.log('  My seat from API:', JSON.stringify(mySeat));

      if (!mySeat) {
        recordBug('BUG-006', 'CRITICAL', 'User not seated after clicking 入座',
          '1. Go to lobby 2. Click 入座',
          'User should be assigned a seat',
          'No seat found for user in API');
      }

      await page.goto(`${BASE_URL}/projects/${projectId}/workspace`);
      await page.waitForLoadState('networkidle');
    }

    // =============================================
    // STEP 6: VERIFY WORKSPACE - DISCOVER PHASE
    // =============================================
    console.log('\n[STEP 6] Workspace verification - Discover phase...');
    await screenshot(page, '10-workspace-initial');

    // Check page title / project name in header
    const headerText = await page.locator('header').textContent().catch(() => '');
    console.log(`  Header: "${headerText.slice(0, 80)}"`);

    // Check stage indicator
    const discoverActive = await page.locator('*').filter({ hasText: /Discover/i }).first().isVisible().catch(() => false);
    console.log('  Discover stage indicator visible:', discoverActive);

    // Check current seat
    const seatsData = await apiGet(`/api/projects/${projectId}/seats`);
    const myUserSeat = seatsData?.find(s => s.user_id === loginData.user.id);
    console.log('  My seat:', JSON.stringify(myUserSeat));

    if (!myUserSeat) {
      recordBug('BUG-007', 'CRITICAL', 'User has no seat in workspace',
        '1. Click 入座 in lobby',
        'User should have a seat assigned',
        'No seat for current user in API');
    } else {
      const isSupervisor = myUserSeat.seat_role === 'supervisor';
      console.log('  Is supervisor:', isSupervisor, '| Role:', myUserSeat.seat_role);
      if (!isSupervisor) {
        recordBug('BUG-008', 'MEDIUM', 'User seated in non-supervisor role when clicking first 入座',
          '1. Click first 入座 button in lobby',
          'First button should be supervisor seat (組長)',
          `User seated as: ${myUserSeat.seat_role}`);
      }
    }

    // Check for "推進到" button (only visible if user is supervisor)
    await sleep(1000);
    const advanceBtnVisible = await page.locator('button').filter({ hasText: /推進到/ }).isVisible().catch(() => false);
    console.log('  "推進到" button visible:', advanceBtnVisible);

    if (!advanceBtnVisible) {
      // Check if user is supervisor
      if (myUserSeat?.seat_role === 'supervisor') {
        recordBug('BUG-009', 'HIGH', '"推進到" button not visible despite user being supervisor',
          '1. Join as supervisor 2. Enter workspace',
          '"推進到 define" button should be visible for supervisor',
          'Button not visible');
      } else {
        recordBug('BUG-009b', 'MEDIUM', 'User is not supervisor - "推進到" button correctly hidden, but wrong seat assigned',
          '1. Click first 入座 in lobby',
          'First seat should be supervisor (組長)',
          `User seated as: ${myUserSeat?.seat_role || 'unknown'}`);
        // Try to become supervisor via API
        console.log('  Attempting to join as supervisor via API...');
        const joinResult = await apiPost(`/api/projects/${projectId}/join`, { seat_role: 'supervisor' });
        console.log('  Join result:', JSON.stringify(joinResult));
        if (joinResult?.seat) {
          console.log('  Now supervisor. Refreshing workspace...');
          await page.reload();
          await page.waitForLoadState('networkidle');
          await sleep(2000);
          const advBtn2 = await page.locator('button').filter({ hasText: /推進到/ }).isVisible().catch(() => false);
          console.log('  "推進到" after role fix:', advBtn2);
          if (!advBtn2) {
            recordBug('BUG-010', 'HIGH', '"推進到" button still not visible after becoming supervisor',
              '1. Join supervisor via API 2. Reload workspace',
              '"推進到 define" should be visible',
              'Button still not visible');
          }
        }
      }
    }

    // Wait 5s for AI supervisor to speak
    console.log('\n  Waiting 5s for AI supervisor message...');
    await sleep(5000);
    await screenshot(page, '11-discover-5s');

    const msgs5s = await apiGet(`/api/projects/${projectId}/messages?limit=50`);
    const msgList5s = msgs5s?.messages || [];
    console.log(`  Messages after 5s: ${msgList5s.length}`);

    if (msgList5s.length === 0) {
      recordBug('BUG-011', 'HIGH', 'No AI messages within 5 seconds of workspace join',
        '1. Join workspace 2. Wait 5 seconds',
        'AI supervisor should speak within 5 seconds',
        'Zero messages after 5 seconds');
    } else {
      // Check for @{crew_N} template patterns
      const templateMsgs = msgList5s.filter(m => m.content && m.content.match(/crew_\d+/));
      console.log(`  Messages with "crew_N" pattern: ${templateMsgs.length}`);
      if (templateMsgs.length > 0) {
        recordBug('BUG-012', 'CRITICAL', '"crew_N" placeholder pattern found in AI messages (unresolved template)',
          '1. Join workspace 2. Wait for AI messages',
          'AI messages should use actual agent names, not "crew_1", "crew_2" etc.',
          `${templateMsgs.length} messages contain "crew_N" patterns: "${templateMsgs[0].content.slice(0, 80)}"`);
      }

      // Check all senders are supervisor only
      const senders = [...new Set(msgList5s.map(m => m.sender_id))];
      if (senders.length === 1 && senders[0] === 'agent_supervisor') {
        console.log('  Only supervisor is speaking (crew agents not responding yet - may be normal)');
      }
    }

    // Wait 30 more seconds for crew agents
    console.log('  Waiting 30s for crew agents...');
    await sleep(30000);
    await screenshot(page, '12-discover-35s');

    const msgs35s = await apiGet(`/api/projects/${projectId}/messages?limit=100`);
    const msgList35s = msgs35s?.messages || [];
    console.log(`  Messages after 35s: ${msgList35s.length}`);

    const senders35s = {};
    msgList35s.forEach(m => { const k = m.sender_id; senders35s[k] = (senders35s[k] || 0) + 1; });
    console.log('  Sender distribution:', JSON.stringify(senders35s));

    if (Object.keys(senders35s).length < 2) {
      recordBug('BUG-013', 'HIGH', 'Crew agents not responding in Discover phase after 35s',
        '1. Join workspace 2. Wait 35 seconds',
        'Multiple crew agents (crew_1-4) should respond',
        `Only ${Object.keys(senders35s).length} sender(s): ${Object.keys(senders35s).join(', ')}`);
    }

    // Check canvas for sticky notes
    const noteCount = await page.locator('[data-shape-type="note"], .tl-note-shape').count();
    console.log(`  Canvas sticky notes visible: ${noteCount}`);

    // Wait another 30s
    console.log('  Waiting 30 more seconds...');
    await sleep(30000);
    await screenshot(page, '13-discover-65s');

    const msgs65s = await apiGet(`/api/projects/${projectId}/messages?limit=100`);
    const msgList65s = msgs65s?.messages || [];
    console.log(`  Messages after 65s: ${msgList65s.length}`);

    // =============================================
    // STEP 7: ADVANCE TO DEFINE
    // =============================================
    console.log('\n[STEP 7] Advancing to Define...');

    // Re-check advance button
    const advBtn = page.locator('button').filter({ hasText: /推進到/ });
    const advBtnVisible = await advBtn.isVisible().catch(() => false);
    console.log('  "推進到" button visible:', advBtnVisible);

    if (!advBtnVisible) {
      // Check button text
      const allBtns = await page.locator('footer button').allTextContents();
      console.log('  Footer buttons:', allBtns.join(' | '));
      recordBug('BUG-014', 'HIGH', '"推進到 define" button not visible before stage advance',
        '1. Be supervisor in workspace 2. Look for advance button',
        'Button "推進到 define" should be visible in footer',
        `Not found. Footer buttons: ${allBtns.join(', ')}`);
      await screenshot(page, '14-no-advance-btn');
    } else {
      const advBtnText = await advBtn.textContent();
      console.log('  Advance button text:', advBtnText?.trim());
      await advBtn.click();
      await sleep(1000);
      await screenshot(page, '14-advance-dialog');

      // Confirm dialog
      const confirmVisible = await page.locator('[role="dialog"]').isVisible().catch(() => false);
      console.log('  Confirm dialog visible:', confirmVisible);

      if (!confirmVisible) {
        recordBug('BUG-015', 'MEDIUM', 'Stage advance confirmation dialog did not appear',
          '1. Click "推進到 define"',
          'Confirmation dialog should appear',
          'Dialog not visible');
      } else {
        const confirmBtn = page.locator('[role="dialog"] button').filter({ hasText: '確認推進' });
        const confirmBtnVisible = await confirmBtn.isVisible().catch(() => false);
        if (confirmBtnVisible) {
          await confirmBtn.click();
          console.log('  Clicked 確認推進');
        } else {
          const altConfirm = page.locator('[role="dialog"] button').last();
          await altConfirm.click();
          console.log('  Clicked last dialog button as confirm fallback');
        }
        await sleep(3000);
      }
    }

    // API verify
    const stageDefine = await apiGet(`/api/projects/${projectId}/stage`);
    console.log('  Stage after Define advance:', JSON.stringify(stageDefine));
    await screenshot(page, '15-define-start');

    if (stageDefine?.current_stage !== 'define') {
      recordBug('BUG-016', 'CRITICAL', 'Stage did not advance to Define after confirm',
        '1. Click "推進到 define" 2. Confirm',
        'current_stage should be "define"',
        `current_stage is "${stageDefine?.current_stage}"`);
    } else {
      console.log('  Stage advanced to Define');
      const microPhase = stageDefine.current_micro_phase;
      console.log('  Micro-phase after advance:', microPhase);
      if (microPhase && !microPhase.startsWith('2')) {
        recordBug('BUG-016b', 'MEDIUM', 'Micro-phase not reset to Define range after stage advance',
          '1. Advance to Define',
          'Micro-phase should start with "2" (Define range)',
          `Micro-phase is: ${microPhase}`);
      }
    }

    // Check progress bar update
    const defineHighlighted = await page.locator('*').filter({ hasText: 'Define' }).first().isVisible().catch(() => false);
    console.log('  Define stage visible in progress:', defineHighlighted);

    // Wait 60s for Define agents
    console.log('  Waiting 60s for Define agents...');
    await sleep(60000);
    await screenshot(page, '16-define-60s');

    const msgsDefine = await apiGet(`/api/projects/${projectId}/messages?limit=200`);
    const msgListDefine = msgsDefine?.messages || [];
    console.log(`  Messages in Define: ${msgListDefine.filter(m => m.stage === 'define').length}`);

    // =============================================
    // STEP 8: ADVANCE TO DEVELOP
    // =============================================
    console.log('\n[STEP 8] Advancing to Develop...');

    const advBtn2 = page.locator('button').filter({ hasText: /推進到/ });
    const advBtn2Visible = await advBtn2.isVisible().catch(() => false);

    if (!advBtn2Visible) {
      recordBug('BUG-017', 'HIGH', '"推進到 develop" button not visible in Define phase',
        '1. After advancing to Define 2. Look for advance button',
        'Button should be visible',
        'Not found');
    } else {
      await advBtn2.click();
      await sleep(1000);
      const confirmBtn2 = page.locator('[role="dialog"] button').filter({ hasText: '確認推進' });
      if (await confirmBtn2.isVisible().catch(() => false)) await confirmBtn2.click();
      else {
        const lastBtn = page.locator('[role="dialog"] button').last();
        if (await lastBtn.isVisible().catch(() => false)) await lastBtn.click();
      }
      await sleep(3000);
    }

    const stageDevelop = await apiGet(`/api/projects/${projectId}/stage`);
    console.log('  Stage after Develop advance:', stageDevelop?.current_stage);
    await screenshot(page, '17-develop-start');

    if (stageDevelop?.current_stage !== 'develop') {
      recordBug('BUG-018', 'CRITICAL', 'Stage did not advance to Develop',
        '1. Advance to Develop',
        '"develop"',
        `"${stageDevelop?.current_stage}"`);
    }

    console.log('  Waiting 60s for Develop agents...');
    await sleep(60000);
    await screenshot(page, '18-develop-60s');

    // =============================================
    // STEP 9: ADVANCE TO DELIVER
    // =============================================
    console.log('\n[STEP 9] Advancing to Deliver...');

    const advBtn3 = page.locator('button').filter({ hasText: /推進到/ });
    const advBtn3Visible = await advBtn3.isVisible().catch(() => false);

    if (!advBtn3Visible) {
      recordBug('BUG-019', 'HIGH', '"推進到 deliver" button not visible in Develop phase',
        '1. After advancing to Develop 2. Look for advance button',
        'Button should be visible',
        'Not found');
    } else {
      await advBtn3.click();
      await sleep(1000);
      const confirmBtn3 = page.locator('[role="dialog"] button').filter({ hasText: '確認推進' });
      if (await confirmBtn3.isVisible().catch(() => false)) await confirmBtn3.click();
      else {
        const lastBtn3 = page.locator('[role="dialog"] button').last();
        if (await lastBtn3.isVisible().catch(() => false)) await lastBtn3.click();
      }
      await sleep(3000);
    }

    const stageDeliver = await apiGet(`/api/projects/${projectId}/stage`);
    console.log('  Stage after Deliver advance:', stageDeliver?.current_stage);
    await screenshot(page, '19-deliver-start');

    if (stageDeliver?.current_stage !== 'deliver') {
      recordBug('BUG-020', 'CRITICAL', 'Stage did not advance to Deliver',
        '1. Advance to Deliver',
        '"deliver"',
        `"${stageDeliver?.current_stage}"`);
    }

    // Verify "推進到" button is GONE in Deliver (last stage)
    await sleep(2000);
    const advBtnInDeliver = await page.locator('button').filter({ hasText: /推進到/ }).isVisible().catch(() => false);
    if (advBtnInDeliver) {
      recordBug('BUG-021', 'MEDIUM', '"推進到" button still visible in Deliver (last stage)',
        '1. Advance to Deliver 2. Check footer',
        'Button should be hidden (no next stage)',
        'Button still visible');
    } else {
      console.log('  "推進到" correctly hidden in Deliver phase');
    }

    console.log('  Waiting 60s for Deliver agents...');
    await sleep(60000);
    await screenshot(page, '20-deliver-60s');

    // =============================================
    // STEP 10: FINAL API VERIFICATION
    // =============================================
    console.log('\n[STEP 10] Final API verification...');

    // All messages
    const finalMsgs = await apiGet(`/api/projects/${projectId}/messages?limit=200`);
    const finalMsgList = finalMsgs?.messages || [];
    console.log(`  Total messages: ${finalMsgList.length}`);

    // Template pattern check
    const templateMsgs = finalMsgList.filter(m => m.content?.match(/crew_\d+/));
    console.log(`  Messages with "crew_N" unresolved: ${templateMsgs.length}`);
    if (templateMsgs.length > 0 && !bugs.find(b => b.id === 'BUG-012')) {
      recordBug('BUG-012', 'CRITICAL', 'Unresolved "crew_N" template patterns in messages',
        '1. Run full journey 2. Check all messages',
        'No "crew_N" in message content',
        `${templateMsgs.length} messages: ${templateMsgs.slice(0, 2).map(m => m.content.slice(0, 60)).join('; ')}`);
    }

    // Stage coverage
    const stageDistrib = {};
    finalMsgList.forEach(m => { stageDistrib[m.stage] = (stageDistrib[m.stage] || 0) + 1; });
    console.log('  Messages by stage:', JSON.stringify(stageDistrib));

    if (!stageDistrib.define && !stageDistrib.develop && !stageDistrib.deliver) {
      recordBug('BUG-022', 'HIGH', 'No messages in Define/Develop/Deliver stages',
        '1. Run full 4-phase journey',
        'Messages should appear in all 4 stages',
        `Only found messages in: ${Object.keys(stageDistrib).join(', ')}`);
    }

    // Sender coverage
    const senderDistrib = {};
    finalMsgList.forEach(m => { senderDistrib[m.sender_id] = (senderDistrib[m.sender_id] || 0) + 1; });
    console.log('  Messages by sender_id:', JSON.stringify(senderDistrib));

    const supervisorOnly = Object.keys(senderDistrib).length === 1 && senderDistrib['agent_supervisor'];
    if (supervisorOnly) {
      recordBug('BUG-023', 'HIGH', 'Only supervisor agent sent messages — crew agents never responded',
        '1. Run full journey 2. Check message senders',
        'All 5 agents should contribute messages',
        'Only agent_supervisor sent messages');
    }

    // Final stage
    const finalStage = await apiGet(`/api/projects/${projectId}/stage`);
    console.log('  Final stage:', JSON.stringify(finalStage));

    if (finalStage?.current_stage !== 'deliver') {
      if (!bugs.find(b => b.id === 'BUG-020')) {
        recordBug('BUG-020b', 'CRITICAL', 'Final stage is not deliver after 4-phase journey',
          '1. Complete all 4 phases',
          'current_stage should be deliver',
          `current_stage is ${finalStage?.current_stage}`);
      }
    }

    // History
    const history = await apiGet(`/api/projects/${projectId}/history`);
    console.log('  History entries:', JSON.stringify(history)?.slice(0, 200));
    if (!history || (Array.isArray(history) && history.length === 0)) {
      recordBug('BUG-024', 'LOW', 'Project history is empty after full journey',
        '1. Complete full journey 2. Check /history endpoint',
        'Should have history entries for each stage',
        'History is empty array');
    }

    // Console errors
    const criticalJsErrors = consoleErrors.filter(e =>
      e.text.includes('Uncaught') || e.text.includes('Cannot read properties') || e.text.includes('TypeError')
    );
    if (criticalJsErrors.length > 0) {
      recordBug('BUG-025', 'HIGH', `${criticalJsErrors.length} unhandled JS errors during journey`,
        '1. Navigate through full journey',
        'No JS errors',
        `Errors: ${criticalJsErrors.slice(0, 2).map(e => e.text.slice(0, 80)).join('; ')}`);
    }

    console.log(`\n  Console errors total: ${consoleErrors.length} (critical: ${criticalJsErrors.length})`);
    console.log(`  Network errors total: ${networkErrors.length}`);

    await screenshot(page, '21-final-state');

  } catch (err) {
    console.error('\n[FATAL ERROR]', err.message);
    console.error(err.stack?.slice(0, 500));
    try { await screenshot(page, '99-fatal-error'); } catch {}
    recordBug('BUG-FATAL', 'CRITICAL', `Fatal test error: ${err.message}`,
      'Running E2E test', 'Complete without fatal errors', err.message);
  } finally {
    await browser.close();
  }

  // =============================================
  // REPORT
  // =============================================
  console.log('\n' + '='.repeat(60));
  console.log('BUG REPORT');
  console.log('='.repeat(60));

  if (bugs.length === 0) {
    console.log('PASS — No bugs found');
  } else {
    const bySev = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    bugs.forEach(b => { bySev[b.severity] = (bySev[b.severity] || 0) + 1; });
    console.log(`Total bugs: ${bugs.length} | CRITICAL:${bySev.CRITICAL} HIGH:${bySev.HIGH} MEDIUM:${bySev.MEDIUM} LOW:${bySev.LOW}`);
    console.log();
    bugs.forEach(b => {
      console.log(`[${b.severity}] ${b.id}: ${b.description}`);
      console.log(`  Expected: ${b.expected}`);
      console.log(`  Actual: ${b.actual}`);
    });
  }

  const reportPath = path.join(__dirname, 'qa-supervisor-report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    projectId,
    totalBugs: bugs.length,
    bySeverity: bugs.reduce((acc, b) => { acc[b.severity] = (acc[b.severity] || 0) + 1; return acc; }, {}),
    bugs,
    consoleErrors: { total: consoleErrors.length, critical: consoleErrors.filter(e => e.text.includes('Uncaught')).length },
    networkErrors: networkErrors.length,
  }, null, 2));
  console.log(`\nReport: ${reportPath}`);
}

main().catch(console.error);
