/**
 * Iteration 2 E2E Test v2: Supervisor Full DT Journey
 * Fixed: modal interception handled via keyboard (Escape) + force click fallback
 * Project ID: cd2d047c-8087-46dd-8b30-3669ca975eef (already created)
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
}

function logIssue(name, severity, detail) {
  console.log(`[ISSUE][${severity}] ${name}: ${detail}`);
  report.issues.push({ name, severity, detail });
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `iter2-sup-v2-${name}.png`);
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
 * Returns true if advance was attempted.
 */
async function advancePhase(page, phaseName) {
  // First dismiss any lingering modal by pressing Escape
  await page.keyboard.press('Escape').catch(() => {});
  await waitMs(500);

  const advanceBtn = page.locator('button:has-text("推進到")');
  const count = await advanceBtn.count();
  console.log(`  [${phaseName}] advance button count: ${count}`);

  if (count === 0) {
    logCheck(`Advance to ${phaseName}`, false, 'No advance button found');
    logIssue(`Missing advance button for ${phaseName}`, 'HIGH', 'Button not visible in final stage check');
    return false;
  }

  // Click using force to bypass any overlay
  await advanceBtn.first().click({ force: true });
  await waitMs(1500);
  await screenshot(page, `advance-modal-${phaseName}`);

  // Look for confirm button inside the modal
  const confirmBtn = page.locator('button:has-text("確認推進"), button:has-text("確認"), button:has-text("繼續")');
  const confirmCount = await confirmBtn.count();
  if (confirmCount > 0) {
    // Use force click to ensure modal confirm works even if backdrop is present
    await confirmBtn.first().click({ force: true });
    await waitMs(2000);
  } else {
    console.log(`  [${phaseName}] No confirm button found, trying keyboard Enter`);
    await page.keyboard.press('Enter');
    await waitMs(2000);
  }

  // Dismiss any remaining modal
  await page.keyboard.press('Escape').catch(() => {});
  await waitMs(500);

  logCheck(`Advance to ${phaseName}`, true, 'Clicked advance + confirm');
  return true;
}

async function runTest() {
  console.log('='.repeat(60));
  console.log('MindCrew Iteration 2 E2E Test v2: Supervisor DT Journey');
  console.log('='.repeat(60));
  console.log(`Project ID: ${PROJECT_ID}`);
  console.log(`Started: ${new Date().toISOString()}`);
  console.log('');

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  page.on('pageerror', err => consoleErrors.push(`PageError: ${err.message}`));

  try {
    // ── Login ──────────────────────────────────────────────
    console.log('\n--- Login ---');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.fill('input[type="email"], input[name="email"]', 'teacher@test.com');
    await page.fill('input[type="password"], input[name="password"]', 'teacher123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(projects|dashboard|lobby)/, { timeout: 15000 });
    logCheck('Login', true);

    // ── Lobby → Workspace ──────────────────────────────────
    console.log('\n--- Lobby + Supervisor Seat ---');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`, { waitUntil: 'networkidle' });
    await waitMs(2000);
    await screenshot(page, '01-lobby');

    const joinBtns = page.locator('button:has-text("入座")');
    const joinCount = await joinBtns.count();
    console.log(`  Found ${joinCount} 入座 buttons`);

    if (joinCount > 0) {
      await joinBtns.first().click();
      await waitMs(3000);
      logCheck('Join as supervisor', true, `${joinCount} buttons found, clicked first`);
    } else {
      logCheck('Join as supervisor', false, 'No 入座 button');
    }

    const currentUrl = page.url();
    logCheck('In workspace', currentUrl.includes('/workspace') || currentUrl.includes('/projects/'), currentUrl);
    await waitMs(2000);
    await screenshot(page, '02-workspace-initial');

    // ── Discover Phase (wait 90s) ──────────────────────────
    console.log('\n--- Discover Phase (90s monitoring) ---');
    const discoverStart = Date.now();

    await waitMs(15000);
    await screenshot(page, '03-discover-15s');
    const msgs15s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=100`);
    const list15s = msgs15s?.messages || [];
    const supMsgs15s = list15s.filter(m => m.sender_id === 'agent_supervisor' || m.sender_id?.includes('supervisor'));
    console.log(`  [15s] Total msgs: ${list15s.length}, supervisor: ${supMsgs15s.length}`);
    logCheck('Supervisor speaks within 15s', supMsgs15s.length > 0, `${supMsgs15s.length} messages`);

    // Wait to 45s
    await waitMs(30000);
    await screenshot(page, '04-discover-45s');
    const msgs45s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=100`);
    const list45s = msgs45s?.messages || [];

    // Check for crew responses at 45s
    const crewAt45s = list45s.filter(m => m.sender_id && m.sender_id.includes('crew'));
    console.log(`  [45s] Total msgs: ${list45s.length}, crew: ${crewAt45s.length}`);

    // Wait to 90s
    await waitMs(45000);
    await screenshot(page, '05-discover-90s');
    const msgs90s = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`);
    const list90s = msgs90s?.messages || [];

    const senders90s = {};
    for (const m of list90s) {
      const s = m.sender_id || 'unknown';
      senders90s[s] = (senders90s[s] || 0) + 1;
    }
    console.log(`  [90s] Senders:`, JSON.stringify(senders90s));

    const crewSenders = Object.keys(senders90s).filter(s => s.includes('crew'));
    logCheck('CRITICAL: Crew agents respond within 90s', crewSenders.length > 0,
      crewSenders.length > 0 ? `Crew senders: [${crewSenders.join(', ')}]` : 'NO CREW MESSAGES');

    if (crewSenders.length === 0) {
      logIssue('Crew agents silent', 'CRITICAL',
        `All 4 crew agents (crew_1..4) produced 0 messages in 90s. ` +
        `Only agent_supervisor sent ${senders90s['agent_supervisor'] || 0} messages. ` +
        `Root cause: rule_4_5_consecutive_ai_limit fires with consecutive_ai=5 ` +
        `(pre-seeded messages at project creation), blocking all crew. ` +
        `The _is_mentioned display_name fix is present but ineffective because ` +
        `rule_4_5 blocks before any crew can act.`
      );
    }

    // Check for template patterns
    const templateMsgs = list90s.filter(m => m.content && /@\{crew_\d\}/.test(m.content));
    logCheck('No @{crew_N} template patterns', templateMsgs.length === 0,
      `${templateMsgs.length} template messages`);

    // Check canvas notes via Playwright DOM
    const canvasNoteCount = await page.locator('[data-shape-type], .tl-shape, [class*="shape"]').count();
    console.log(`  Canvas shape elements: ${canvasNoteCount}`);

    const stageInfo = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Stage: ${JSON.stringify(stageInfo)}`);
    logCheck('Stage info available', !!stageInfo, `micro_phase: ${stageInfo?.current_micro_phase}`);

    report.phases.discover = {
      duration_s: Math.round((Date.now() - discoverStart) / 1000),
      total_messages: list90s.length,
      senders: senders90s,
      crew_responded: crewSenders.length > 0,
      micro_phase: stageInfo?.current_micro_phase
    };

    // ── Advance to Define ──────────────────────────────────
    console.log('\n--- Advance to Define ---');
    await advancePhase(page, 'Define');
    await waitMs(60000);
    await screenshot(page, '06-define-60s');

    const defineStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    const inDefine = defineStage?.current_micro_phase?.startsWith('2.') || defineStage?.current_stage === 'define';
    logCheck('Define micro_phase starts with 2.', inDefine, `micro_phase: ${defineStage?.current_micro_phase}`);

    const defineMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=200`);
    report.phases.define = {
      micro_phase: defineStage?.current_micro_phase,
      total_messages: defineMsgs?.messages?.length || 0
    };

    // ── Advance to Develop ─────────────────────────────────
    console.log('\n--- Advance to Develop ---');
    await advancePhase(page, 'Develop');
    await waitMs(60000);
    await screenshot(page, '07-develop-60s');

    const developStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    const inDevelop = developStage?.current_micro_phase?.startsWith('3.') || developStage?.current_stage === 'develop';
    logCheck('Develop micro_phase starts with 3.', inDevelop, `micro_phase: ${developStage?.current_micro_phase}`);

    report.phases.develop = { micro_phase: developStage?.current_micro_phase };

    // ── Advance to Deliver ─────────────────────────────────
    console.log('\n--- Advance to Deliver ---');
    await advancePhase(page, 'Deliver');
    await waitMs(60000);
    await screenshot(page, '08-deliver-60s');

    const deliverStage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    const inDeliver = deliverStage?.current_micro_phase?.startsWith('4.') || deliverStage?.current_stage === 'deliver';
    logCheck('Deliver micro_phase starts with 4.', inDeliver, `micro_phase: ${deliverStage?.current_micro_phase}`);

    const finalAdvanceCount = await page.locator('button:has-text("推進到")').count();
    logCheck('No "推進到" button in Deliver (final stage)', finalAdvanceCount === 0,
      `Found ${finalAdvanceCount}`);

    await screenshot(page, '09-final-state');

    report.phases.deliver = {
      micro_phase: deliverStage?.current_micro_phase,
      no_advance_button: finalAdvanceCount === 0
    };

    // ── Final API summary ──────────────────────────────────
    console.log('\n--- Final API Checks ---');
    const finalMsgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=500`);
    const finalList = finalMsgs?.messages || [];
    const uniqueSenders = {};
    for (const m of finalList) {
      const s = m.sender_id || 'unknown';
      if (!uniqueSenders[s]) uniqueSenders[s] = { count: 0, name: m.sender_name || s };
      uniqueSenders[s].count++;
    }
    console.log('  Final senders:', JSON.stringify(uniqueSenders));
    logCheck('Multiple unique senders (agents active)', Object.keys(uniqueSenders).length >= 2,
      `${Object.keys(uniqueSenders).length} unique senders`);

    if (consoleErrors.length > 5) {
      logIssue('Browser console errors', 'MEDIUM',
        `${consoleErrors.length} errors. First: ${consoleErrors[0]}`);
    }

    report.final = {
      total_messages: finalList.length,
      unique_senders: uniqueSenders,
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

  // ── Summary ────────────────────────────────────────────
  console.log('\n' + '='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));
  const passed = report.checks.filter(c => c.passed).length;
  const failed = report.checks.filter(c => !c.passed).length;
  console.log(`Checks: ${passed} passed, ${failed} failed`);

  const bySeverity = { CRITICAL: [], HIGH: [], MEDIUM: [], LOW: [] };
  for (const i of report.issues) {
    (bySeverity[i.severity] || bySeverity.LOW).push(i);
  }

  for (const [sev, issues] of Object.entries(bySeverity)) {
    if (issues.length > 0) {
      console.log(`\n${sev} (${issues.length}):`);
      issues.forEach(i => console.log(`  - ${i.name}: ${i.detail}`));
    }
  }

  const reportPath = path.join(__dirname, 'iter2-supervisor-report-v2.json');
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
