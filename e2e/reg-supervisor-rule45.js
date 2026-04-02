/**
 * Regression Test: Supervisor Full 4-Phase Journey (Rule 4.5 change)
 *
 * Tests that ALL previous fixes remain working after the Rule 4.5 update:
 * 1. Supervisor speaks within 10s
 * 2. Crew responds within 60s
 * 3. ≥3 unique senders in Discover
 * 4. No template crew_N patterns
 * 5. micro_phase correct per stage (1.x, 2.x, 3.x, 4.x)
 * 6. Advance button present/absent correctly
 *
 * Uses pre-created project: 1aefaca9-cc05-4d27-983d-5f56da1df42a
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';
const SS_DIR = path.join(__dirname, 'screenshots');
const PROJECT_ID = '1aefaca9-cc05-4d27-983d-5f56da1df42a';
const CREDS = { email: 'teacher@test.com', password: 'teacher123' };

const bugs = [];
const consoleErrors = [];
const results = {};

function pass(checkId, detail = '') {
  results[checkId] = { status: 'PASS', detail };
  console.log(`  [PASS] ${checkId}${detail ? ': ' + detail : ''}`);
}

function fail(checkId, severity, expected, actual, detail = '') {
  results[checkId] = { status: 'FAIL', severity, expected, actual, detail };
  bugs.push({ id: checkId, severity, expected, actual, detail });
  console.log(`  [FAIL][${severity}] ${checkId}`);
  console.log(`    Expected: ${expected}`);
  console.log(`    Actual:   ${actual}`);
}

async function ss(page, name) {
  const filepath = path.join(SS_DIR, `reg-sup-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  Screenshot: reg-sup-${name}.png`);
  return filepath;
}

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function apiGet(endpoint, token) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    });
    if (!res.ok) { console.log(`  API GET ${endpoint} => ${res.status}`); return null; }
    return res.json();
  } catch (e) { console.log(`  API GET error: ${e.message}`); return null; }
}

async function apiPost(endpoint, body, token = null) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST', headers, body: JSON.stringify(body)
    });
    if (!res.ok) { const t = await res.text(); console.log(`  API POST ${endpoint} => ${res.status}: ${t.slice(0, 100)}`); return null; }
    return res.json();
  } catch (e) { console.log(`  API POST error: ${e.message}`); return null; }
}

async function main() {
  console.log('='.repeat(60));
  console.log('REGRESSION TEST: Supervisor Full 4-Phase (Rule 4.5)');
  console.log('Project:', PROJECT_ID);
  console.log('Time:', new Date().toISOString());
  console.log('='.repeat(60));

  // Auth
  console.log('\n[AUTH] Logging in...');
  const loginData = await apiPost('/api/auth/login', CREDS);
  if (!loginData?.access_token) { console.error('Login failed'); process.exit(1); }
  const token = loginData.access_token;
  console.log('  User:', loginData.user.display_name, '| Role:', loginData.user.role);

  // Verify project exists
  const projectData = await apiGet(`/api/projects/${PROJECT_ID}`, token);
  if (!projectData) { console.error('Project not found:', PROJECT_ID); process.exit(1); }
  console.log('  Project:', projectData.name, '| Stage:', projectData.current_stage);

  // Launch browser
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ text: msg.text(), url: msg.location()?.url || '' });
    }
  });

  try {
    // =============================================
    // STEP 1: BROWSER LOGIN
    // =============================================
    console.log('\n[STEP 1] Browser login...');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await ss(page, '01-login-page');

    await page.locator('input[type="email"]').fill(CREDS.email);
    await page.locator('input[type="password"]').fill(CREDS.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });
    await page.waitForLoadState('networkidle');
    console.log('  Logged in. URL:', page.url());

    // =============================================
    // STEP 2: NAVIGATE TO LOBBY AND JOIN AS SUPERVISOR
    // =============================================
    console.log('\n[STEP 2] Navigating to project lobby...');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(1500);
    await ss(page, '02-lobby');

    // Find 入座 buttons (supervisor is first)
    const inzuoButtons = page.locator('button').filter({ hasText: '入座' });
    const inzuoCount = await inzuoButtons.count();
    console.log(`  Found ${inzuoCount} "入座" buttons`);

    if (inzuoCount === 0) {
      fail('CHECK-LOBBY-JOIN', 'CRITICAL', 'At least 1 入座 button visible', `0 buttons found`);
      // Try direct workspace navigation
      console.log('  Attempting direct workspace nav...');
    } else {
      pass('CHECK-LOBBY-JOIN', `${inzuoCount} 入座 buttons visible`);
      console.log('  Clicking first 入座 (supervisor seat)...');
      await inzuoButtons.first().click();
      await sleep(3000);
      await page.waitForLoadState('networkidle');
      await ss(page, '03-after-join');
      console.log('  After join URL:', page.url());
    }

    // Navigate to workspace if not already there
    if (!page.url().includes('/workspace')) {
      await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`);
      await page.waitForLoadState('networkidle');
    }

    // Verify seat via API
    const seatsData = await apiGet(`/api/projects/${PROJECT_ID}/seats`, token);
    const mySeat = seatsData?.find(s => s.user_id === loginData.user.id);
    console.log('  My seat:', JSON.stringify(mySeat));

    if (!mySeat) {
      fail('CHECK-SEAT-ASSIGNED', 'CRITICAL', 'User has a seat after clicking 入座', 'No seat found in API');
    } else if (mySeat.seat_role === 'supervisor') {
      pass('CHECK-SEAT-ROLE', 'User seated as supervisor');
    } else {
      fail('CHECK-SEAT-ROLE', 'HIGH', 'seat_role = supervisor', `seat_role = ${mySeat.seat_role}`);
    }

    // =============================================
    // STEP 3: DISCOVER PHASE — Initial workspace
    // =============================================
    console.log('\n[STEP 3] DISCOVER PHASE verification...');
    await sleep(1000);
    await ss(page, '04-workspace-initial');

    // Check advance button visible (supervisor only)
    const advBtn = page.locator('button').filter({ hasText: /推進到/ });
    const advBtnVisible = await advBtn.isVisible().catch(() => false);
    console.log('  "推進到" button visible:', advBtnVisible);

    if (!advBtnVisible) {
      fail('CHECK-ADV-DISCOVER', 'HIGH', '"推進到 define" button visible for supervisor in Discover', 'Button not visible');
    } else {
      pass('CHECK-ADV-DISCOVER', '"推進到" button visible in Discover');
    }

    // Check micro_phase starts with "1."
    const stageDiscover = await apiGet(`/api/projects/${PROJECT_ID}/stage`, token);
    console.log('  Stage/micro_phase:', JSON.stringify(stageDiscover));

    if (stageDiscover?.current_stage !== 'discover') {
      fail('CHECK-DISCOVER-STAGE', 'CRITICAL', 'current_stage = discover', `current_stage = ${stageDiscover?.current_stage}`);
    } else {
      pass('CHECK-DISCOVER-STAGE', 'current_stage = discover');
      const mp = stageDiscover.current_micro_phase;
      if (mp && mp.startsWith('1')) {
        pass('CHECK-DISCOVER-MICRO', `micro_phase = ${mp} (starts with 1)`);
      } else if (mp) {
        fail('CHECK-DISCOVER-MICRO', 'MEDIUM', 'micro_phase starts with "1"', `micro_phase = ${mp}`);
      }
    }

    // Wait 10s — supervisor should speak
    console.log('\n  Waiting 10s for supervisor first message...');
    await sleep(10000);
    await ss(page, '05-discover-10s');

    const msgs10s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=50`, token);
    const msgList10s = msgs10s?.messages || [];
    console.log(`  Messages after 10s: ${msgList10s.length}`);

    const supMsgs10s = msgList10s.filter(m => m.sender_id === 'agent_supervisor');
    if (supMsgs10s.length > 0) {
      pass('CHECK-SUP-SPEAKS-10S', `Supervisor spoke within 10s (${supMsgs10s.length} msg)`);
    } else {
      fail('CHECK-SUP-SPEAKS-10S', 'HIGH', 'Supervisor speaks within 10s', `0 supervisor messages after 10s (total: ${msgList10s.length})`);
    }

    // Template pattern check at 10s
    const templateMsgs10s = msgList10s.filter(m => m.content?.match(/crew_\d+/));
    if (templateMsgs10s.length === 0) {
      pass('CHECK-NO-TEMPLATE-10S', 'No crew_N template patterns');
    } else {
      fail('CHECK-NO-TEMPLATE-10S', 'CRITICAL', 'No crew_N pattern in messages',
        `${templateMsgs10s.length} msgs contain crew_N: "${templateMsgs10s[0].content.slice(0, 80)}"`);
    }

    // Wait 50 more seconds for crew to respond (total 60s)
    console.log('  Waiting 50 more seconds for crew agents (total 60s)...');
    await sleep(50000);
    await ss(page, '06-discover-60s');

    const msgs60s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=100`, token);
    const msgList60s = msgs60s?.messages || [];
    console.log(`  Messages after 60s: ${msgList60s.length}`);

    const senderSet60s = new Set(msgList60s.map(m => m.sender_id));
    const uniqueSenders60s = [...senderSet60s];
    console.log('  Unique senders after 60s:', uniqueSenders60s);

    if (senderSet60s.size >= 3) {
      pass('CHECK-CREW-RESPONDS', `≥3 unique senders: ${uniqueSenders60s.join(', ')}`);
    } else {
      fail('CHECK-CREW-RESPONDS', 'HIGH', '≥3 unique senders within 60s',
        `Only ${senderSet60s.size} sender(s): ${uniqueSenders60s.join(', ')}`);
    }

    // Template pattern check at 60s
    const templateMsgs60s = msgList60s.filter(m => m.content?.match(/crew_\d+/));
    if (templateMsgs60s.length === 0) {
      pass('CHECK-NO-TEMPLATE-60S', 'No crew_N template patterns in any message');
    } else {
      fail('CHECK-NO-TEMPLATE-60S', 'CRITICAL', 'No crew_N pattern in any message',
        `${templateMsgs60s.length} msgs contain crew_N: "${templateMsgs60s[0].content.slice(0, 80)}"`);
    }

    // Check chat UI visible
    const chatInput = page.locator('[data-testid="chat-input"], textarea[placeholder*="訊息"], textarea[placeholder*="message"]');
    const chatCount = await chatInput.count();
    console.log('  Chat input elements found:', chatCount);

    // =============================================
    // STEP 4: ADVANCE TO DEFINE
    // =============================================
    console.log('\n[STEP 4] Advancing to DEFINE...');

    const advBtnDefine = page.locator('button').filter({ hasText: /推進到/ });
    const advDefineVisible = await advBtnDefine.isVisible().catch(() => false);

    if (!advDefineVisible) {
      const footerBtns = await page.locator('footer button').allTextContents().catch(() => []);
      fail('CHECK-ADV-BTN-BEFORE-DEFINE', 'HIGH',
        '"推進到" button visible before advancing to Define',
        `Not visible. Footer: ${footerBtns.join(' | ')}`);
      await ss(page, '07-no-advance-btn');
    } else {
      const btnTxt = await advBtnDefine.textContent();
      console.log('  Advance button text:', btnTxt?.trim());
      await advBtnDefine.click();
      await sleep(1000);
      await ss(page, '07-advance-dialog');

      // Confirm dialog
      const confirmDialog = page.locator('[role="dialog"]');
      const confirmVisible = await confirmDialog.isVisible().catch(() => false);
      console.log('  Confirm dialog visible:', confirmVisible);

      if (confirmVisible) {
        const confirmBtn = confirmDialog.locator('button').filter({ hasText: '確認推進' });
        const hasConfirm = await confirmBtn.isVisible().catch(() => false);
        if (hasConfirm) {
          await confirmBtn.click();
          console.log('  Clicked 確認推進');
        } else {
          const lastBtn = confirmDialog.locator('button').last();
          await lastBtn.click();
          console.log('  Clicked last button in dialog');
        }
      } else {
        console.log('  No confirm dialog — advance may be immediate');
      }
      await sleep(4000);
    }

    // Verify Define stage
    await ss(page, '08-define-start');
    const stageDefine = await apiGet(`/api/projects/${PROJECT_ID}/stage`, token);
    console.log('  Stage after advance:', JSON.stringify(stageDefine));

    if (stageDefine?.current_stage === 'define') {
      pass('CHECK-DEFINE-STAGE', 'current_stage = define');
      const mp = stageDefine.current_micro_phase;
      console.log('  Define micro_phase:', mp);
      if (mp && mp.startsWith('2')) {
        pass('CHECK-DEFINE-MICRO', `micro_phase = ${mp} (starts with 2)`);
      } else {
        fail('CHECK-DEFINE-MICRO', 'MEDIUM', 'micro_phase starts with "2" (Define range)',
          `micro_phase = ${mp}`);
      }
    } else {
      fail('CHECK-DEFINE-STAGE', 'CRITICAL', 'current_stage = define',
        `current_stage = ${stageDefine?.current_stage}`);
    }

    // Check advance button still visible in Define
    await sleep(2000);
    const advInDefine = await page.locator('button').filter({ hasText: /推進到/ }).isVisible().catch(() => false);
    if (advInDefine) {
      pass('CHECK-ADV-IN-DEFINE', '"推進到" button visible in Define for supervisor');
    } else {
      fail('CHECK-ADV-IN-DEFINE', 'HIGH', '"推進到" button visible in Define phase', 'Button not visible');
    }

    // Wait 60s for Define agents
    console.log('  Waiting 60s for Define agents...');
    await sleep(60000);
    await ss(page, '09-define-60s');

    const msgsDefine = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`, token);
    const defineMsgs = (msgsDefine?.messages || []).filter(m => m.stage === 'define');
    console.log(`  Define stage messages: ${defineMsgs.length}`);

    if (defineMsgs.length > 0) {
      pass('CHECK-DEFINE-MSGS', `${defineMsgs.length} messages in Define stage`);
    } else {
      fail('CHECK-DEFINE-MSGS', 'HIGH', 'Messages generated in Define stage', '0 define messages after 60s');
    }

    // =============================================
    // STEP 5: ADVANCE TO DEVELOP
    // =============================================
    console.log('\n[STEP 5] Advancing to DEVELOP...');

    const advBtnDevelop = page.locator('button').filter({ hasText: /推進到/ });
    const advDevelopVisible = await advBtnDevelop.isVisible().catch(() => false);

    if (!advDevelopVisible) {
      fail('CHECK-ADV-BTN-DEVELOP', 'HIGH', '"推進到" visible before advancing to Develop', 'Not visible');
    } else {
      await advBtnDevelop.click();
      await sleep(1000);
      const confirmDialog2 = page.locator('[role="dialog"]');
      if (await confirmDialog2.isVisible().catch(() => false)) {
        const cb2 = confirmDialog2.locator('button').filter({ hasText: '確認推進' });
        if (await cb2.isVisible().catch(() => false)) await cb2.click();
        else await confirmDialog2.locator('button').last().click();
      }
      await sleep(4000);
    }

    await ss(page, '10-develop-start');
    const stageDevelop = await apiGet(`/api/projects/${PROJECT_ID}/stage`, token);
    console.log('  Stage after Develop advance:', JSON.stringify(stageDevelop));

    if (stageDevelop?.current_stage === 'develop') {
      pass('CHECK-DEVELOP-STAGE', 'current_stage = develop');
      const mp = stageDevelop.current_micro_phase;
      console.log('  Develop micro_phase:', mp);
      if (mp && mp.startsWith('3')) {
        pass('CHECK-DEVELOP-MICRO', `micro_phase = ${mp} (starts with 3)`);
      } else {
        fail('CHECK-DEVELOP-MICRO', 'MEDIUM', 'micro_phase starts with "3" (Develop range)',
          `micro_phase = ${mp}`);
      }
    } else {
      fail('CHECK-DEVELOP-STAGE', 'CRITICAL', 'current_stage = develop',
        `current_stage = ${stageDevelop?.current_stage}`);
    }

    // Wait 60s for Develop agents
    console.log('  Waiting 60s for Develop agents...');
    await sleep(60000);
    await ss(page, '11-develop-60s');

    const msgsDevelop = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`, token);
    const developMsgs = (msgsDevelop?.messages || []).filter(m => m.stage === 'develop');
    console.log(`  Develop stage messages: ${developMsgs.length}`);

    if (developMsgs.length > 0) {
      pass('CHECK-DEVELOP-MSGS', `${developMsgs.length} messages in Develop stage`);
    } else {
      fail('CHECK-DEVELOP-MSGS', 'HIGH', 'Messages generated in Develop stage', '0 develop messages after 60s');
    }

    // =============================================
    // STEP 6: ADVANCE TO DELIVER
    // =============================================
    console.log('\n[STEP 6] Advancing to DELIVER...');

    const advBtnDeliver = page.locator('button').filter({ hasText: /推進到/ });
    const advDeliverVisible = await advBtnDeliver.isVisible().catch(() => false);

    if (!advDeliverVisible) {
      fail('CHECK-ADV-BTN-DELIVER', 'HIGH', '"推進到" visible before advancing to Deliver', 'Not visible');
    } else {
      await advBtnDeliver.click();
      await sleep(1000);
      const confirmDialog3 = page.locator('[role="dialog"]');
      if (await confirmDialog3.isVisible().catch(() => false)) {
        const cb3 = confirmDialog3.locator('button').filter({ hasText: '確認推進' });
        if (await cb3.isVisible().catch(() => false)) await cb3.click();
        else await confirmDialog3.locator('button').last().click();
      }
      await sleep(4000);
    }

    await ss(page, '12-deliver-start');
    const stageDeliver = await apiGet(`/api/projects/${PROJECT_ID}/stage`, token);
    console.log('  Stage after Deliver advance:', JSON.stringify(stageDeliver));

    if (stageDeliver?.current_stage === 'deliver') {
      pass('CHECK-DELIVER-STAGE', 'current_stage = deliver');
      const mp = stageDeliver.current_micro_phase;
      console.log('  Deliver micro_phase:', mp);
      if (mp && mp.startsWith('4')) {
        pass('CHECK-DELIVER-MICRO', `micro_phase = ${mp} (starts with 4)`);
      } else {
        fail('CHECK-DELIVER-MICRO', 'MEDIUM', 'micro_phase starts with "4" (Deliver range)',
          `micro_phase = ${mp}`);
      }
    } else {
      fail('CHECK-DELIVER-STAGE', 'CRITICAL', 'current_stage = deliver',
        `current_stage = ${stageDeliver?.current_stage}`);
    }

    // Verify NO advance button in Deliver (last stage)
    await sleep(2000);
    const advInDeliver = await page.locator('button').filter({ hasText: /推進到/ }).isVisible().catch(() => false);
    if (!advInDeliver) {
      pass('CHECK-NO-ADV-IN-DELIVER', '"推進到" correctly absent in Deliver (last stage)');
    } else {
      fail('CHECK-NO-ADV-IN-DELIVER', 'MEDIUM', '"推進到" NOT visible in Deliver (last stage)', 'Button still visible');
    }

    // Wait 30s for Deliver agents
    console.log('  Waiting 30s for Deliver agents...');
    await sleep(30000);
    await ss(page, '13-deliver-30s');

    const msgsDeliver = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`, token);
    const deliverMsgs = (msgsDeliver?.messages || []).filter(m => m.stage === 'deliver');
    console.log(`  Deliver stage messages: ${deliverMsgs.length}`);

    if (deliverMsgs.length > 0) {
      pass('CHECK-DELIVER-MSGS', `${deliverMsgs.length} messages in Deliver stage`);
    } else {
      fail('CHECK-DELIVER-MSGS', 'HIGH', 'Messages generated in Deliver stage', '0 deliver messages after 30s');
    }

    // =============================================
    // STEP 7: FINAL API VERIFICATION
    // =============================================
    console.log('\n[STEP 7] Final API verification...');

    const finalMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`, token);
    const allMsgs = finalMsgs?.messages || [];
    console.log(`  Total messages: ${allMsgs.length}`);

    // Stage coverage
    const stageDistrib = {};
    allMsgs.forEach(m => { stageDistrib[m.stage] = (stageDistrib[m.stage] || 0) + 1; });
    console.log('  Messages by stage:', JSON.stringify(stageDistrib));

    const requiredStages = ['discover', 'define', 'develop', 'deliver'];
    const missingStages = requiredStages.filter(s => !stageDistrib[s]);
    if (missingStages.length === 0) {
      pass('CHECK-ALL-STAGES-HAVE-MSGS', 'All 4 stages have messages');
    } else {
      fail('CHECK-ALL-STAGES-HAVE-MSGS', 'HIGH',
        'All 4 stages (discover, define, develop, deliver) have messages',
        `Missing messages in: ${missingStages.join(', ')}`);
    }

    // Sender coverage
    const senderDistrib = {};
    allMsgs.forEach(m => { senderDistrib[m.sender_id] = (senderDistrib[m.sender_id] || 0) + 1; });
    console.log('  Messages by sender:', JSON.stringify(senderDistrib));

    const uniqueSendersFinal = Object.keys(senderDistrib);
    if (uniqueSendersFinal.length >= 3) {
      pass('CHECK-FINAL-SENDERS', `${uniqueSendersFinal.length} unique senders total: ${uniqueSendersFinal.join(', ')}`);
    } else {
      fail('CHECK-FINAL-SENDERS', 'HIGH',
        '≥3 unique senders in full journey',
        `Only ${uniqueSendersFinal.length}: ${uniqueSendersFinal.join(', ')}`);
    }

    // Template pattern — final check
    const templateFinal = allMsgs.filter(m => m.content?.match(/crew_\d+/));
    if (templateFinal.length === 0) {
      pass('CHECK-NO-TEMPLATE-FINAL', 'No crew_N template patterns across entire journey');
    } else {
      fail('CHECK-NO-TEMPLATE-FINAL', 'CRITICAL',
        'Zero crew_N patterns in all messages',
        `${templateFinal.length} messages: "${templateFinal[0].content.slice(0, 80)}"`);
    }

    // Final stage state
    const finalStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`, token);
    console.log('  Final stage state:', JSON.stringify(finalStage));

    if (finalStage?.current_stage === 'deliver') {
      pass('CHECK-FINAL-STAGE', 'Final stage = deliver as expected');
    } else {
      fail('CHECK-FINAL-STAGE', 'CRITICAL', 'Final current_stage = deliver', `${finalStage?.current_stage}`);
    }

    // Console errors
    const criticalJsErrors = consoleErrors.filter(e =>
      e.text.includes('Uncaught') || e.text.includes('Cannot read properties') || e.text.includes('TypeError')
    );
    console.log(`  Console errors: ${consoleErrors.length} total, ${criticalJsErrors.length} critical`);

    if (criticalJsErrors.length === 0) {
      pass('CHECK-NO-JS-ERRORS', `${consoleErrors.length} non-critical console messages`);
    } else {
      fail('CHECK-NO-JS-ERRORS', 'HIGH', '0 critical JS errors',
        `${criticalJsErrors.length} errors: ${criticalJsErrors.slice(0, 2).map(e => e.text.slice(0, 80)).join('; ')}`);
    }

    await ss(page, '14-final-state');

  } catch (err) {
    console.error('\n[FATAL ERROR]', err.message);
    console.error(err.stack?.slice(0, 500));
    try { await ss(page, '99-fatal-error'); } catch {}
    fail('CHECK-FATAL', 'CRITICAL', 'No fatal errors during test', err.message);
  } finally {
    await browser.close();
  }

  // =============================================
  // REPORT
  // =============================================
  console.log('\n' + '='.repeat(60));
  console.log('REGRESSION TEST REPORT — Rule 4.5 Supervisor Journey');
  console.log('='.repeat(60));

  const passCount = Object.values(results).filter(r => r.status === 'PASS').length;
  const failCount = Object.values(results).filter(r => r.status === 'FAIL').length;
  const bySev = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  bugs.forEach(b => { bySev[b.severity] = (bySev[b.severity] || 0) + 1; });

  console.log(`\nPASS: ${passCount} | FAIL: ${failCount}`);
  console.log(`Failures: CRITICAL:${bySev.CRITICAL} HIGH:${bySev.HIGH} MEDIUM:${bySev.MEDIUM} LOW:${bySev.LOW}`);

  if (bugs.length === 0) {
    console.log('\nRESULT: ALL CHECKS PASSED — Rule 4.5 regression confirmed clean');
  } else {
    console.log('\nRESULT: REGRESSION DETECTED — Issues found after Rule 4.5 change');
    console.log('\nFailed checks:');
    bugs.forEach(b => {
      console.log(`\n  [${b.severity}] ${b.id}`);
      console.log(`    Expected: ${b.expected}`);
      console.log(`    Actual:   ${b.actual}`);
      if (b.detail) console.log(`    Detail:   ${b.detail}`);
    });
  }

  // Save report
  const report = {
    testName: 'Regression Supervisor Rule 4.5',
    timestamp: new Date().toISOString(),
    projectId: PROJECT_ID,
    summary: { pass: passCount, fail: failCount, bySeverity: bySev },
    results,
    bugs,
    consoleErrors: { total: consoleErrors.length, critical: consoleErrors.filter(e => e.text.includes('Uncaught')).length }
  };

  const reportPath = path.join(__dirname, 'reg-sup-rule45-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport saved: ${reportPath}`);

  process.exit(bugs.filter(b => b.severity === 'CRITICAL' || b.severity === 'HIGH').length > 0 ? 1 : 0);
}

main().catch(console.error);
