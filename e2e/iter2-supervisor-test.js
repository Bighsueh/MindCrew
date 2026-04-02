/**
 * Iteration 2 E2E Test: Supervisor Full DT Journey
 * Tests whether crew agents respond after _is_mentioned() display-name fix
 * Project ID: cd2d047c-8087-46dd-8b30-3669ca975eef
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const PROJECT_ID = 'cd2d047c-8087-46dd-8b30-3669ca975eef';
const TOKEN = '***REMOVED_JWT***';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

const report = {
  timestamp: new Date().toISOString(),
  project_id: PROJECT_ID,
  issues: [],
  checks: [],
  phases: {}
};

function logCheck(name, passed, detail = '') {
  const status = passed ? 'PASS' : 'FAIL';
  console.log(`[${status}] ${name}${detail ? ': ' + detail : ''}`);
  report.checks.push({ name, passed, detail });
  if (!passed) {
    report.issues.push({ name, detail, severity: 'HIGH' });
  }
}

function logIssue(name, severity, detail) {
  console.log(`[ISSUE][${severity}] ${name}: ${detail}`);
  report.issues.push({ name, severity, detail });
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `iter2-sup-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  Screenshot saved: ${filepath}`);
  return filepath;
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    headers: { 'Authorization': `Bearer ${TOKEN}` }
  });
  return res.json();
}

async function waitMs(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTest() {
  console.log('='.repeat(60));
  console.log('MindCrew Iteration 2 E2E Test: Supervisor DT Journey');
  console.log('='.repeat(60));
  console.log(`Project ID: ${PROJECT_ID}`);
  console.log(`Started: ${new Date().toISOString()}`);
  console.log('');

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(`PageError: ${err.message}`));

  try {
    // =========================================================
    // Step 1: Login in browser
    // =========================================================
    console.log('\n--- Step 1: Browser Login ---');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await screenshot(page, '01-login-page');

    // Fill login form
    await page.fill('input[type="email"], input[name="email"]', 'teacher@test.com');
    await page.fill('input[type="password"], input[name="password"]', 'teacher123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(projects|dashboard|lobby)/, { timeout: 15000 });
    await screenshot(page, '02-after-login');
    logCheck('Login', true, 'Redirected after submit');

    // =========================================================
    // Step 2: Navigate to Lobby
    // =========================================================
    console.log('\n--- Step 2: Navigate to Lobby ---');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`, { waitUntil: 'networkidle' });
    await waitMs(2000);
    await screenshot(page, '03-lobby-page');

    // =========================================================
    // Step 3: Join as Supervisor (first "入座" button)
    // =========================================================
    console.log('\n--- Step 3: Join as Supervisor ---');
    const joinBtns = page.locator('button:has-text("入座")');
    const count = await joinBtns.count();
    console.log(`  Found ${count} "入座" buttons`);

    if (count > 0) {
      await joinBtns.first().click();
      await waitMs(3000);
      await screenshot(page, '04-after-join');
      logCheck('Join as supervisor', true, `Clicked first 入座 button`);
    } else {
      logCheck('Join as supervisor', false, 'No 入座 button found');
      logIssue('No join button', 'HIGH', 'Cannot join as supervisor - no 入座 buttons visible');
    }

    // Check if we were redirected to workspace
    const currentUrl = page.url();
    console.log(`  Current URL: ${currentUrl}`);
    const inWorkspace = currentUrl.includes('/workspace') || currentUrl.includes('/projects/');
    logCheck('Navigated to workspace', inWorkspace, currentUrl);

    // Wait for workspace to fully load
    await waitMs(3000);
    await screenshot(page, '05-workspace-initial');

    // =========================================================
    // Step 4: Discover Phase Monitoring (0-60s)
    // =========================================================
    console.log('\n--- Step 4: Discover Phase (monitoring 60s) ---');
    const discoverStart = Date.now();

    // Check supervisor speaks within 10s
    await waitMs(10000);
    await screenshot(page, '06-discover-10s');

    const msgs10s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=50`);
    const msgList10s = Array.isArray(msgs10s) ? msgs10s : (msgs10s.messages || msgs10s.data || []);
    console.log(`  Messages at 10s: ${msgList10s.length}`);
    const supervisorMsgs10s = msgList10s.filter(m =>
      m.sender_role === 'supervisor' || m.agent_id === 'agent_supervisor' ||
      (m.sender_name && (m.sender_name.includes('引導者') || m.sender_name.includes('Supervisor')))
    );
    logCheck('Supervisor speaks within 10s', supervisorMsgs10s.length > 0,
      `${supervisorMsgs10s.length} supervisor messages found`);

    // Wait until 30s total
    await waitMs(20000);
    await screenshot(page, '07-discover-30s');
    const msgs30s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=50`);
    const msgList30s = Array.isArray(msgs30s) ? msgs30s : (msgs30s.messages || msgs30s.data || []);
    console.log(`  Messages at 30s: ${msgList30s.length}`);

    // Wait until 60s total
    await waitMs(30000);
    await screenshot(page, '08-discover-60s');

    const msgs60s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=100`);
    const msgList60s = Array.isArray(msgs60s) ? msgs60s : (msgs60s.messages || msgs60s.data || []);
    console.log(`  Messages at 60s: ${msgList60s.length}`);

    // Analyze senders
    const senders60s = {};
    for (const m of msgList60s) {
      const sender = m.agent_id || m.sender_id || m.sender_role || 'unknown';
      senders60s[sender] = (senders60s[sender] || 0) + 1;
    }
    console.log('  Senders:', JSON.stringify(senders60s));

    // CRITICAL CHECK: Do ANY crew agents respond?
    const crewSenders = Object.keys(senders60s).filter(s =>
      s.includes('crew') || s.includes('crew_1') || s.includes('crew_2') ||
      s.includes('crew_3') || s.includes('crew_4')
    );
    logCheck('Crew agents respond within 60s (CRITICAL)', crewSenders.length > 0,
      `Crew senders: [${crewSenders.join(', ')}]`);

    report.phases.discover = {
      duration_s: 60,
      total_messages: msgList60s.length,
      senders: senders60s,
      crew_responded: crewSenders.length > 0
    };

    // Check for @{crew_N} template patterns (should not appear)
    const templatePattern = /@\{crew_\d\}/;
    const templateMsgs = msgList60s.filter(m => m.content && templatePattern.test(m.content));
    logCheck('No @{crew_N} template patterns in messages', templateMsgs.length === 0,
      templateMsgs.length > 0 ? `Found ${templateMsgs.length} messages with templates` : 'Clean');

    // Check canvas for sticky notes via API
    const stageInfo60s = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Stage info: ${JSON.stringify(stageInfo60s)}`);
    logCheck('Stage API returns data', !!stageInfo60s, JSON.stringify(stageInfo60s));

    // =========================================================
    // Step 5: Advance to Define Phase
    // =========================================================
    console.log('\n--- Step 5: Advance to Define Phase ---');

    // Look for advance button
    const advanceBtns = page.locator('button:has-text("推進到"), button:has-text("進入"), button:has-text("下一階段"), [data-testid="advance-phase"]');
    const advanceCount = await advanceBtns.count();
    console.log(`  Found ${advanceCount} advance buttons`);

    if (advanceCount > 0) {
      await advanceBtns.first().click();
      await waitMs(2000);
      await screenshot(page, '09-advance-modal');

      // Look for confirm button
      const confirmBtns = page.locator('button:has-text("確認"), button:has-text("確認推進"), button:has-text("繼續")');
      const confirmCount = await confirmBtns.count();
      if (confirmCount > 0) {
        await confirmBtns.first().click();
        await waitMs(3000);
      }
      await screenshot(page, '10-define-start');
      logCheck('Advanced to Define', true, 'Clicked advance + confirm');
    } else {
      await screenshot(page, '09-no-advance-btn');
      logCheck('Advanced to Define', false, 'No advance button found');
      logIssue('No advance button', 'HIGH', 'Cannot advance phase - button not found');
    }

    // Wait 60s for Define phase activity
    console.log('  Waiting 60s for Define phase activity...');
    await waitMs(30000);
    await screenshot(page, '11-define-30s');
    await waitMs(30000);
    await screenshot(page, '12-define-60s');

    const defineStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Define stage: ${JSON.stringify(defineStage)}`);
    const inDefine = defineStage && (
      (defineStage.micro_phase && defineStage.micro_phase.startsWith('2.')) ||
      defineStage.current_stage === 'define'
    );
    logCheck('Define phase micro_phase starts with "2."', inDefine,
      `micro_phase: ${defineStage && defineStage.micro_phase}`);

    const defineMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=150`);
    const defineMsgList = Array.isArray(defineMsgs) ? defineMsgs : (defineMsgs.messages || defineMsgs.data || []);
    console.log(`  Total messages after Define: ${defineMsgList.length}`);

    report.phases.define = {
      micro_phase: defineStage && defineStage.micro_phase,
      total_messages: defineMsgList.length
    };

    // =========================================================
    // Step 6: Advance to Develop Phase
    // =========================================================
    console.log('\n--- Step 6: Advance to Develop Phase ---');

    const advanceBtns2 = page.locator('button:has-text("推進到"), button:has-text("進入"), button:has-text("下一階段"), [data-testid="advance-phase"]');
    const advanceCount2 = await advanceBtns2.count();

    if (advanceCount2 > 0) {
      await advanceBtns2.first().click();
      await waitMs(2000);
      const confirmBtns2 = page.locator('button:has-text("確認"), button:has-text("確認推進"), button:has-text("繼續")');
      if (await confirmBtns2.count() > 0) {
        await confirmBtns2.first().click();
        await waitMs(3000);
      }
      logCheck('Advanced to Develop', true, '');
    } else {
      logCheck('Advanced to Develop', false, 'No advance button');
    }

    await waitMs(30000);
    await screenshot(page, '13-develop-30s');
    await waitMs(30000);
    await screenshot(page, '14-develop-60s');

    const developStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    const inDevelop = developStage && (
      (developStage.micro_phase && developStage.micro_phase.startsWith('3.')) ||
      developStage.current_stage === 'develop'
    );
    logCheck('Develop phase micro_phase starts with "3."', inDevelop,
      `micro_phase: ${developStage && developStage.micro_phase}`);

    report.phases.develop = {
      micro_phase: developStage && developStage.micro_phase
    };

    // =========================================================
    // Step 7: Advance to Deliver Phase
    // =========================================================
    console.log('\n--- Step 7: Advance to Deliver Phase ---');

    const advanceBtns3 = page.locator('button:has-text("推進到"), button:has-text("進入"), button:has-text("下一階段"), [data-testid="advance-phase"]');
    const advanceCount3 = await advanceBtns3.count();

    if (advanceCount3 > 0) {
      await advanceBtns3.first().click();
      await waitMs(2000);
      const confirmBtns3 = page.locator('button:has-text("確認"), button:has-text("確認推進"), button:has-text("繼續")');
      if (await confirmBtns3.count() > 0) {
        await confirmBtns3.first().click();
        await waitMs(3000);
      }
      logCheck('Advanced to Deliver', true, '');
    } else {
      logCheck('Advanced to Deliver', false, 'No advance button');
    }

    await waitMs(30000);
    await screenshot(page, '15-deliver-30s');
    await waitMs(30000);
    await screenshot(page, '16-deliver-60s');

    const deliverStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    const inDeliver = deliverStage && (
      (deliverStage.micro_phase && deliverStage.micro_phase.startsWith('4.')) ||
      deliverStage.current_stage === 'deliver'
    );
    logCheck('Deliver phase micro_phase starts with "4."', inDeliver,
      `micro_phase: ${deliverStage && deliverStage.micro_phase}`);

    // Check no "推進到" button at last stage
    const finalAdvanceCount = await page.locator('button:has-text("推進到")').count();
    logCheck('No "推進到" button in final stage', finalAdvanceCount === 0,
      `Found ${finalAdvanceCount} advance buttons`);

    report.phases.deliver = {
      micro_phase: deliverStage && deliverStage.micro_phase,
      no_advance_button: finalAdvanceCount === 0
    };

    // =========================================================
    // Step 8: Final API Checks
    // =========================================================
    console.log('\n--- Step 8: Final API Checks ---');
    await screenshot(page, '17-final-state');

    const finalMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`);
    const finalMsgList = Array.isArray(finalMsgs) ? finalMsgs : (finalMsgs.messages || finalMsgs.data || []);
    console.log(`  Total messages: ${finalMsgList.length}`);

    // Count unique senders
    const uniqueSenders = {};
    for (const m of finalMsgList) {
      const sender = m.agent_id || m.sender_id || m.sender_role || 'unknown';
      if (!uniqueSenders[sender]) uniqueSenders[sender] = { count: 0, name: m.sender_name || sender };
      uniqueSenders[sender].count++;
    }
    console.log('  Unique senders:', JSON.stringify(uniqueSenders, null, 2));

    logCheck('Multiple unique senders (agents active)', Object.keys(uniqueSenders).length >= 2,
      `${Object.keys(uniqueSenders).length} unique senders: [${Object.keys(uniqueSenders).join(', ')}]`);

    // Check history
    const history = await apiGet(`/api/projects/${PROJECT_ID}/history`);
    console.log(`  History: ${JSON.stringify(history)}`);

    // Verify final stage
    const finalStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Final stage: ${JSON.stringify(finalStage)}`);

    // Check console errors
    if (consoleErrors.length > 0) {
      console.log(`\n  Browser console errors (${consoleErrors.length}):`);
      consoleErrors.slice(0, 10).forEach(e => console.log(`    - ${e}`));
      if (consoleErrors.length > 5) {
        logIssue('Browser console errors', 'MEDIUM', `${consoleErrors.length} errors: ${consoleErrors[0]}`);
      }
    }

    report.final = {
      total_messages: finalMsgList.length,
      unique_senders: uniqueSenders,
      final_stage: finalStage,
      console_errors: consoleErrors.length
    };

  } catch (err) {
    console.error('\nFATAL TEST ERROR:', err.message);
    await screenshot(page, '99-fatal-error').catch(() => {});
    report.fatal_error = err.message;
    logIssue('Fatal test error', 'CRITICAL', err.message);
  } finally {
    await browser.close();
  }

  // =========================================================
  // Check backend logs for key indicators
  // =========================================================
  console.log('\n--- Backend Log Analysis ---');

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));
  const passed = report.checks.filter(c => c.passed).length;
  const failed = report.checks.filter(c => !c.passed).length;
  console.log(`Checks: ${passed} passed, ${failed} failed`);
  console.log(`Issues: ${report.issues.length} total`);

  const critical = report.issues.filter(i => i.severity === 'CRITICAL');
  const high = report.issues.filter(i => i.severity === 'HIGH');
  const medium = report.issues.filter(i => i.severity === 'MEDIUM');

  if (critical.length > 0) {
    console.log(`\nCRITICAL Issues (${critical.length}):`);
    critical.forEach(i => console.log(`  - ${i.name}: ${i.detail}`));
  }
  if (high.length > 0) {
    console.log(`\nHIGH Issues (${high.length}):`);
    high.forEach(i => console.log(`  - ${i.name}: ${i.detail}`));
  }
  if (medium.length > 0) {
    console.log(`\nMEDIUM Issues (${medium.length}):`);
    medium.forEach(i => console.log(`  - ${i.name}: ${i.detail}`));
  }

  // Save report
  const reportPath = path.join(__dirname, 'iter2-supervisor-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport saved: ${reportPath}`);

  return report;
}

runTest().then(r => {
  const failedCritical = r.issues.filter(i => i.severity === 'CRITICAL' || i.severity === 'HIGH');
  process.exit(failedCritical.length > 0 ? 1 : 0);
}).catch(err => {
  console.error(err);
  process.exit(1);
});
