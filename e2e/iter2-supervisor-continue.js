/**
 * Iteration 2 E2E Test: Continue from Define phase
 * Discover is already verified: crew agents DO respond (crew_1 + crew_4 confirmed)
 * This script advances Define → Develop → Deliver and verifies each phase
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
  if (!passed) report.issues.push({ name, severity: 'HIGH', detail });
}

function logIssue(name, severity, detail) {
  console.log(`[ISSUE][${severity}] ${name}: ${detail}`);
  report.issues.push({ name, severity, detail });
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `iter2-sup-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  Screenshot: ${filepath}`);
  return filepath;
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    headers: { 'Authorization': `Bearer ${TOKEN}` }
  });
  if (!res.ok) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

function waitMs(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Advance phase with robust modal handling.
 * Uses force clicks and keyboard to handle backdrop overlay.
 */
async function advancePhase(page, phaseName) {
  // Dismiss any open modal first
  await page.keyboard.press('Escape').catch(() => {});
  await waitMs(800);

  const advanceBtn = page.locator('button:has-text("推進到")');
  const count = await advanceBtn.count();
  console.log(`  [${phaseName}] advance button count: ${count}`);

  if (count === 0) {
    logCheck(`Advance to ${phaseName}`, false, 'No advance button found');
    return false;
  }

  // Force click to bypass any transparent overlay
  await advanceBtn.first().click({ force: true });
  await waitMs(1500);
  await screenshot(page, `advance-${phaseName}-modal`);

  // Confirm in the dialog
  const confirmBtn = page.locator('button:has-text("確認推進"), button:has-text("確認"), button:has-text("繼續")');
  const confirmCount = await confirmBtn.count();
  if (confirmCount > 0) {
    await confirmBtn.first().click({ force: true });
    await waitMs(2000);
    await screenshot(page, `advance-${phaseName}-confirmed`);
  } else {
    await page.keyboard.press('Enter');
    await waitMs(2000);
  }

  // Close any remaining modal
  await page.keyboard.press('Escape').catch(() => {});
  await waitMs(500);

  logCheck(`Advance to ${phaseName}`, true, 'advance + confirm clicked');
  return true;
}

async function runTest() {
  console.log('='.repeat(60));
  console.log('MindCrew Iter2: Continue from Define → Develop → Deliver');
  console.log('='.repeat(60));
  console.log(`Project: ${PROJECT_ID}`);
  console.log(`Started: ${new Date().toISOString()}`);

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  try {
    // Login
    console.log('\n--- Login ---');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.fill('input[type="email"], input[name="email"]', 'teacher@test.com');
    await page.fill('input[type="password"], input[name="password"]', 'teacher123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(projects|dashboard|lobby)/, { timeout: 15000 });
    logCheck('Login', true);

    // Navigate to workspace
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`, { waitUntil: 'networkidle' });
    await waitMs(3000);
    await screenshot(page, 'cont-00-workspace');
    logCheck('Workspace loaded', page.url().includes('/workspace'), page.url());

    // Check current stage
    const currentStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Current stage: ${JSON.stringify(currentStage)}`);

    // ── Define Phase ───────────────────────────────────────
    if (currentStage?.current_stage === 'discover') {
      console.log('\n--- Still in Discover: Advancing to Define ---');
      await advancePhase(page, 'Define');
    } else {
      console.log(`\n--- Already in ${currentStage?.current_stage} ---`);
    }

    // Wait for Define activity
    console.log('\n--- Define Phase (60s) ---');
    await waitMs(30000);
    await screenshot(page, 'cont-01-define-30s');
    await waitMs(30000);
    await screenshot(page, 'cont-02-define-60s');

    const defineStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Define stage: ${JSON.stringify(defineStage)}`);
    const inDefine = defineStage?.current_micro_phase?.startsWith('2.') || defineStage?.current_stage === 'define';
    logCheck('Define micro_phase starts with "2."', inDefine, `micro_phase: ${defineStage?.current_micro_phase}`);

    const defineMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`);
    const defineList = defineMsgs?.messages || [];
    const defineSenders = {};
    for (const m of defineList) {
      const s = m.sender_id || 'unknown';
      defineSenders[s] = (defineSenders[s] || 0) + 1;
    }
    console.log('  Define senders:', JSON.stringify(defineSenders));

    report.phases.define = {
      micro_phase: defineStage?.current_micro_phase,
      total_messages: defineList.length,
      senders: defineSenders
    };

    // ── Advance to Develop ─────────────────────────────────
    console.log('\n--- Advancing to Develop ---');
    await advancePhase(page, 'Develop');

    // Wait for Develop activity
    console.log('--- Develop Phase (60s) ---');
    await waitMs(30000);
    await screenshot(page, 'cont-03-develop-30s');
    await waitMs(30000);
    await screenshot(page, 'cont-04-develop-60s');

    const developStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Develop stage: ${JSON.stringify(developStage)}`);
    const inDevelop = developStage?.current_micro_phase?.startsWith('3.') || developStage?.current_stage === 'develop';
    logCheck('Develop micro_phase starts with "3."', inDevelop, `micro_phase: ${developStage?.current_micro_phase}`);

    report.phases.develop = { micro_phase: developStage?.current_micro_phase };

    // ── Advance to Deliver ─────────────────────────────────
    console.log('\n--- Advancing to Deliver ---');
    await advancePhase(page, 'Deliver');

    // Wait for Deliver activity
    console.log('--- Deliver Phase (60s) ---');
    await waitMs(30000);
    await screenshot(page, 'cont-05-deliver-30s');
    await waitMs(30000);
    await screenshot(page, 'cont-06-deliver-60s');

    const deliverStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Deliver stage: ${JSON.stringify(deliverStage)}`);
    const inDeliver = deliverStage?.current_micro_phase?.startsWith('4.') || deliverStage?.current_stage === 'deliver';
    logCheck('Deliver micro_phase starts with "4."', inDeliver, `micro_phase: ${deliverStage?.current_micro_phase}`);

    // Check no "推進到" in final stage
    await page.keyboard.press('Escape').catch(() => {});
    await waitMs(500);
    const finalAdvanceCount = await page.locator('button:has-text("推進到")').count();
    logCheck('No "推進到" button in final stage (Deliver)', finalAdvanceCount === 0,
      `Found ${finalAdvanceCount} buttons`);

    await screenshot(page, 'cont-07-final-deliver');

    report.phases.deliver = {
      micro_phase: deliverStage?.current_micro_phase,
      no_advance_button: finalAdvanceCount === 0
    };

    // ── Final summary ──────────────────────────────────────
    console.log('\n--- Final API Summary ---');
    const finalMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=500`);
    const finalList = finalMsgs?.messages || [];
    const uniqueSenders = {};
    for (const m of finalList) {
      const s = m.sender_id || 'unknown';
      if (!uniqueSenders[s]) uniqueSenders[s] = { count: 0, name: m.sender_name || s };
      uniqueSenders[s].count++;
    }
    console.log('  Final senders:', JSON.stringify(uniqueSenders, null, 2));
    logCheck('3+ unique senders across full journey', Object.keys(uniqueSenders).length >= 3,
      `${Object.keys(uniqueSenders).length} senders: [${Object.keys(uniqueSenders).join(', ')}]`);

    if (consoleErrors.length > 5) {
      logIssue('Browser console errors', 'MEDIUM', `${consoleErrors.length} errors: ${consoleErrors[0]}`);
    }

    report.final = {
      total_messages: finalList.length,
      unique_senders: uniqueSenders,
      console_errors: consoleErrors.length
    };

  } catch (err) {
    console.error('\nFATAL ERROR:', err.message);
    await screenshot(page, 'cont-99-fatal-error').catch(() => {});
    report.fatal_error = err.message;
    logIssue('Fatal test error', 'CRITICAL', err.message);
  } finally {
    await browser.close();
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('CONTINUATION TEST SUMMARY');
  console.log('='.repeat(60));
  const passed = report.checks.filter(c => c.passed).length;
  const failed = report.checks.filter(c => !c.passed).length;
  console.log(`Checks: ${passed} passed, ${failed} failed`);
  console.log(`Issues: ${report.issues.length} total`);

  for (const sev of ['CRITICAL', 'HIGH', 'MEDIUM']) {
    const issues = report.issues.filter(i => i.severity === sev);
    if (issues.length > 0) {
      console.log(`\n${sev} (${issues.length}):`);
      issues.forEach(i => console.log(`  - ${i.name}: ${i.detail}`));
    }
  }

  const reportPath = path.join(__dirname, 'iter2-supervisor-continue-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport: ${reportPath}`);
  return report;
}

runTest().then(r => {
  const blocking = r.issues.filter(i => i.severity === 'CRITICAL' || i.severity === 'HIGH');
  process.exit(blocking.length > 0 ? 1 : 0);
}).catch(err => {
  console.error(err);
  process.exit(1);
});
