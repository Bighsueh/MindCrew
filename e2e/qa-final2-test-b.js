/**
 * Test B: EDGE CASES
 * - Join then leave then rejoin with different role
 * - API stage skip validation (discover -> develop without going through define)
 * - API backward stage validation (define -> discover)
 * - Invalid stage name rejection
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

const PROJECT_ID = '8f509f4a-a1cb-4b24-9f26-7ce180c7458d';
const CREDS = { email: 'teacher@test.com', password: 'teacher123' };

const report = {
  testName: 'Test B: EDGE CASES',
  projectId: PROJECT_ID,
  projectName: 'QA-Edge-購物車邊界測試',
  startTime: new Date().toISOString(),
  checks: [],
  bugs: [],
  screenshots: []
};

function addCheck(name, passed, detail) {
  const status = passed ? 'PASS' : 'FAIL';
  report.checks.push({ name, status, detail });
  console.log(`[${status}] ${name}: ${detail}`);
}

function addBug(severity, description, detail) {
  report.bugs.push({ severity, description, detail });
  console.log(`[BUG:${severity}] ${description}: ${detail}`);
}

async function screenshot(page, name) {
  const filename = `qa-final2-${name}.png`;
  const filepath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  report.screenshots.push(filepath);
  console.log(`[SCREENSHOT] ${filepath}`);
  return filepath;
}

async function getToken() {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(CREDS)
  });
  const data = await res.json();
  return data.access_token;
}

async function apiRequest(method, urlPath, token, body) {
  const opts = {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_URL}${urlPath}`, opts);
  let data;
  try { data = await res.json(); } catch { data = null; }
  return { status: res.status, ok: res.ok, data };
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function runTestB() {
  console.log('\n=== TEST B: EDGE CASES ===\n');

  const token = await getToken();
  console.log('Token obtained');

  // Verify project B in discover stage
  const proj = await apiRequest('GET', `/api/projects/${PROJECT_ID}`, token);
  addCheck('B-0: Project B exists', proj.ok, `Stage: ${proj.data?.current_stage}, Status: ${proj.data?.status}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // =======================================================
  // SECTION 1: Role Switching (Join -> Leave -> Rejoin)
  // =======================================================
  try {
    // Step 1: Login
    console.log('\n--- Step 1: Login ---');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="email"]', CREDS.email);
    await page.fill('input[type="password"]', CREDS.password);
    await page.click('button[type="submit"]');
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    addCheck('B-1: Login', !page.url().includes('/login'), `URL: ${page.url()}`);

    // Step 2: Navigate to workspace and join as supervisor
    console.log('\n--- Step 2: Join as supervisor ---');
    const joinSup = await apiRequest('POST', `/api/projects/${PROJECT_ID}/join`, token, { seat_role: 'supervisor' });
    addCheck('B-2a: Join supervisor via API', joinSup.ok, `Status: ${joinSup.status}, Role: ${joinSup.data?.seat?.seat_role}`);

    await page.goto(`${BASE_URL}/workspace/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');
    await sleep(4000);
    await screenshot(page, 'B-1-joined-as-supervisor');

    // Check supervisor can see advance button
    const advanceBtns = await page.locator('button').filter({ hasText: /推進到|下一階段/i }).count();
    addCheck('B-2b: Supervisor sees advance button', advanceBtns > 0, `Advance buttons: ${advanceBtns}`);
    if (advanceBtns === 0) {
      addBug('MEDIUM', 'Advance button not visible for supervisor', 'Supervisor should see 推進到 button to advance stages');
    }

    // Step 3: Wait 30s for agents to start
    console.log('\n--- Step 3: Wait 30s for agents ---');
    await sleep(30000);
    await screenshot(page, 'B-2-agents-30s');

    const msgs30 = await apiRequest('GET', `/api/projects/${PROJECT_ID}/messages?limit=10`, token);
    const msgList30 = msgs30.data?.messages || msgs30.data || [];
    addCheck('B-3: Agents started (messages present)', msgList30.length > 0, `Messages: ${msgList30.length}`);

    // Step 4: Leave the seat (click leave button or API)
    console.log('\n--- Step 4: Leave seat ---');
    const leaveCount = await page.locator('button').filter({ hasText: /離開|Leave/i }).count();
    console.log(`Leave buttons found: ${leaveCount}`);

    let leftViaUI = false;
    if (leaveCount > 0) {
      await page.locator('button').filter({ hasText: /離開|Leave/i }).first().click();
      await sleep(2000);
      await screenshot(page, 'B-3-after-leave-click');
      leftViaUI = true;
      addCheck('B-4a: Leave button clicked', true, `URL: ${page.url()}`);
    } else {
      addBug('LOW', 'Leave button not visible in workspace', 'Expected 離開 button to be visible for supervisor');
    }

    // Also leave via API to ensure clean state
    const leaveRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/leave`, token);
    addCheck('B-4b: API leave successful', leaveRes.ok, `Status: ${leaveRes.status}, Message: ${leaveRes.data?.message}`);

    // Verify seat is cleared
    const seatsAfterLeave = await apiRequest('GET', `/api/projects/${PROJECT_ID}/seats`, token);
    const humanSeatAfterLeave = seatsAfterLeave.data?.find(s => s.occupant_type === 'human');
    addCheck('B-4c: Seat cleared after leave', !humanSeatAfterLeave, `Human seat: ${JSON.stringify(humanSeatAfterLeave)}`);

    // Step 5: Navigate back to lobby
    console.log('\n--- Step 5: Navigate to lobby ---');
    await page.goto(`${BASE_URL}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    await screenshot(page, 'B-4-lobby-after-leave');
    addCheck('B-5: Back to lobby', page.url().includes('/lobby'), `URL: ${page.url()}`);

    // Step 6: Rejoin as crew_1 (observer role)
    console.log('\n--- Step 6: Rejoin as crew_1 (different role) ---');
    const joinCrew = await apiRequest('POST', `/api/projects/${PROJECT_ID}/join`, token, { seat_role: 'crew_1' });
    addCheck('B-6: Rejoin as crew_1', joinCrew.ok, `Status: ${joinCrew.status}, Role: ${joinCrew.data?.seat?.seat_role}`);

    await page.goto(`${BASE_URL}/workspace/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');
    await sleep(4000);
    await screenshot(page, 'B-5-rejoined-as-crew1');

    // Step 7: Check agents continue working after role switch
    console.log('\n--- Step 7: Check agents continue after role switch ---');
    await sleep(15000);
    const msgsAfterSwitch = await apiRequest('GET', `/api/projects/${PROJECT_ID}/messages?limit=20`, token);
    const msgListAfter = msgsAfterSwitch.data?.messages || msgsAfterSwitch.data || [];
    addCheck('B-7: Agents continue after role switch', msgListAfter.length >= msgList30.length,
      `Messages after switch: ${msgListAfter.length}, before: ${msgList30.length}`);
    await screenshot(page, 'B-6-agents-continue');

  } catch (err) {
    console.error('Test B section 1 error:', err);
    addBug('HIGH', 'Role switching test error', err.message);
    try { await screenshot(page, 'B-section1-error'); } catch {}
  }

  await browser.close();

  // =======================================================
  // SECTION 2: API Edge Cases (pure API, no browser)
  // =======================================================
  console.log('\n\n--- SECTION 2: API Edge Cases ---');

  const token2 = await getToken();

  // First ensure we have a supervisor seat so we can test advance
  // Leave current seat and join as supervisor
  await apiRequest('POST', `/api/projects/${PROJECT_ID}/leave`, token2);
  const joinSup2 = await apiRequest('POST', `/api/projects/${PROJECT_ID}/join`, token2, { seat_role: 'supervisor' });
  console.log('Joined as supervisor for edge case tests:', JSON.stringify(joinSup2.data?.seat));

  // Edge Case 1: Skip stage — discover -> develop (skipping define)
  console.log('\n--- Edge Case 1: Stage skip (discover->develop) ---');
  const currentStage = await apiRequest('GET', `/api/projects/${PROJECT_ID}`, token2);
  console.log(`Current stage: ${currentStage.data?.current_stage}`);

  const skipRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: currentStage.data?.current_stage || 'discover',
    to: 'develop'
  });
  console.log('Skip result:', JSON.stringify({ status: skipRes.status, data: skipRes.data }));

  const skipRejected = !skipRes.ok || skipRes.status >= 400;
  addCheck('B-8: Skip stage (discover->develop) rejected', skipRejected,
    `Status: ${skipRes.status}, Response: ${JSON.stringify(skipRes.data)}`);
  if (!skipRejected) {
    addBug('HIGH', 'Stage skip not prevented',
      `Allowed skipping from discover to develop without going through define. Status: ${skipRes.status}`);
  }

  // Verify stage unchanged after skip attempt
  const stageAfterSkip = await apiRequest('GET', `/api/projects/${PROJECT_ID}`, token2);
  const stageAfterSkipStr = stageAfterSkip.data?.current_stage;
  addCheck('B-8b: Stage unchanged after skip attempt',
    stageAfterSkipStr === 'discover' || !skipRejected,
    `Stage: ${stageAfterSkipStr}`);

  // Edge Case 2: Advance backwards (need to be in define first)
  console.log('\n--- Edge Case 2: Advance backwards ---');
  // Legitimately advance to define first
  const advToDefine = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: 'discover',
    to: 'define'
  });
  console.log('Advance to define:', JSON.stringify({ status: advToDefine.status, data: advToDefine.data }));
  addCheck('B-9a: Advance to define (legitimate)', advToDefine.ok, `Status: ${advToDefine.status}`);

  const stageAfterAdvance = await apiRequest('GET', `/api/projects/${PROJECT_ID}`, token2);
  console.log(`Stage after advance to define: ${stageAfterAdvance.data?.current_stage}`);

  // Now try going backwards: define -> discover
  const backwardRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: stageAfterAdvance.data?.current_stage || 'define',
    to: 'discover'
  });
  console.log('Backward result:', JSON.stringify({ status: backwardRes.status, data: backwardRes.data }));

  const backwardRejected = !backwardRes.ok || backwardRes.status >= 400;
  addCheck('B-9b: Backward stage advance rejected', backwardRejected,
    `Status: ${backwardRes.status}, Response: ${JSON.stringify(backwardRes.data)}`);
  if (!backwardRejected) {
    addBug('HIGH', 'Backward stage advance not prevented',
      `Was able to advance backwards from define to discover. Status: ${backwardRes.status}`);
  }

  // Edge Case 3: Invalid stage name
  console.log('\n--- Edge Case 3: Invalid stage name ---');
  const invalidRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: 'define',
    to: 'invalid_stage_xyz'
  });
  console.log('Invalid stage result:', JSON.stringify({ status: invalidRes.status, data: invalidRes.data }));

  addCheck('B-10: Invalid stage name rejected',
    !invalidRes.ok || invalidRes.status >= 400,
    `Status: ${invalidRes.status}`);
  if (invalidRes.ok) {
    addBug('HIGH', 'Invalid stage name accepted', `Status ${invalidRes.status} — system should reject unknown stage names`);
  }

  // Edge Case 4: Stage without being in correct "from" state
  console.log('\n--- Edge Case 4: Wrong from state ---');
  const wrongFromRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: 'develop', // wrong — we're in define
    to: 'deliver'
  });
  console.log('Wrong from result:', JSON.stringify({ status: wrongFromRes.status, data: wrongFromRes.data }));

  addCheck('B-11: Wrong from-state advance rejected',
    !wrongFromRes.ok || wrongFromRes.status >= 400,
    `Status: ${wrongFromRes.status}, Response: ${JSON.stringify(wrongFromRes.data)}`);
  if (wrongFromRes.ok) {
    addBug('MEDIUM', 'Wrong from-state advance not validated',
      `Was able to advance with wrong from-state. Status: ${wrongFromRes.status}`);
  }

  // Edge Case 5: Non-supervisor trying to advance
  console.log('\n--- Edge Case 5: Non-supervisor advance attempt ---');
  // Leave supervisor and join as crew
  await apiRequest('POST', `/api/projects/${PROJECT_ID}/leave`, token2);
  await apiRequest('POST', `/api/projects/${PROJECT_ID}/join`, token2, { seat_role: 'crew_2' });

  const nonSupAdvRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`, token2, {
    from: stageAfterAdvance.data?.current_stage || 'define',
    to: 'develop'
  });
  console.log('Non-supervisor advance:', JSON.stringify({ status: nonSupAdvRes.status, data: nonSupAdvRes.data }));

  const nonSupRejected = !nonSupAdvRes.ok || nonSupAdvRes.status >= 400;
  addCheck('B-12: Non-supervisor advance rejected', nonSupRejected,
    `Status: ${nonSupAdvRes.status}, Response: ${JSON.stringify(nonSupAdvRes.data)}`);
  if (!nonSupRejected) {
    addBug('HIGH', 'Non-supervisor can advance stages',
      `crew_2 role was able to advance stage. Status: ${nonSupAdvRes.status}`);
  }

  // Final stage check
  const finalStage = await apiRequest('GET', `/api/projects/${PROJECT_ID}`, token2);
  addCheck('B-13: Final stage check', finalStage.ok,
    `Stage: ${finalStage.data?.current_stage}`);

  // Report summary
  report.endTime = new Date().toISOString();
  report.consoleErrors = consoleErrors;
  const passed = report.checks.filter(c => c.status === 'PASS').length;
  const failed = report.checks.filter(c => c.status === 'FAIL').length;
  report.summary = { passed, failed, total: report.checks.length };

  console.log(`\n=== TEST B SUMMARY ===`);
  console.log(`PASSED: ${passed}/${report.checks.length}`);
  console.log(`FAILED: ${failed}`);
  console.log(`BUGS: ${report.bugs.length}`);
  report.checks.forEach(c => {
    const icon = c.status === 'PASS' ? 'v' : 'x';
    console.log(`  [${icon}] ${c.name}`);
  });

  const reportPath = path.join(__dirname, 'qa-final2-test-b-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport saved: ${reportPath}`);

  return report;
}

// Node.js compatibility for fetch
if (typeof fetch === 'undefined') {
  global.fetch = require('node:https') ? (...args) => import('node-fetch').then(m => m.default(...args)) : undefined;
}

runTestB().catch(console.error);
