/**
 * QA FINAL TEST A: SUPERVISOR — Full 4-Phase with extended observation
 *
 * Pre-requisite: Project already created via API (passed in as env var or hardcoded below)
 *
 * Checks:
 * - All 5 agents contributing throughout DISCOVER
 * - Agent count exceeds 15 messages (old Rule 4.5 stall regression)
 * - Evaluator auto-advances micro-phase (1.1 → 1.2 or 1.3)
 * - All 4 stages reachable: DISCOVER → DEFINE → DEVELOP → DELIVER
 * - Screenshots at 30s, 60s, 120s intervals
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const CREDS = { email: 'teacher@test.com', password: 'teacher123' };
const PROJECT_ID = process.env.PROJECT_A_ID || 'e07ece3c-f090-4596-9cda-50bc112dcc6f';

const bugs = [];
let authToken = '';
const consoleErrors = [];

function recordBug(id, severity, description, expected, actual, screenshot = null) {
  const bug = { id, severity, description, expected, actual, screenshot, timestamp: new Date().toISOString() };
  bugs.push(bug);
  console.log(`\n[BUG] ${id} [${severity}]: ${description}`);
  console.log(`  Expected: ${expected}`);
  console.log(`  Actual:   ${actual}`);
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `qa-final1-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  [screenshot] qa-final1-${name}.png`);
  return filepath;
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) return null;
  return res.json();
}

async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { status: res.status, data: res.ok ? await res.json().catch(() => null) : null };
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function checkMessages(label) {
  const data = await apiGet(`/api/projects/${PROJECT_ID}/messages`);
  if (!data) {
    console.log(`  [${label}] messages API returned null`);
    return { total: 0, senders: {}, messages: [] };
  }
  const messages = data.messages || [];
  const senders = {};
  for (const m of messages) {
    const sender = m.agent_id || m.sender_id || m.role || 'unknown';
    senders[sender] = (senders[sender] || 0) + 1;
  }
  console.log(`  [${label}] Total messages: ${messages.length}`);
  console.log(`  [${label}] Senders: ${JSON.stringify(senders)}`);
  // Check for template patterns
  const templateMsgs = messages.filter(m => {
    const content = m.content || m.text || '';
    return content.includes('@{crew_') || /\bcrew_\d\b/.test(content);
  });
  if (templateMsgs.length > 0) {
    console.log(`  [${label}] WARNING: ${templateMsgs.length} messages with template patterns found`);
  }
  return { total: messages.length, senders, messages, templateCount: templateMsgs.length };
}

async function checkStage(label) {
  const data = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
  if (!data) {
    console.log(`  [${label}] stage API returned null`);
    return null;
  }
  console.log(`  [${label}] Stage: ${data.current_stage} | Micro: ${data.current_micro_phase}`);
  return data;
}

async function main() {
  console.log('='.repeat(70));
  console.log('TEST A: SUPERVISOR — Full 4-Phase Journey');
  console.log(`Project ID: ${PROJECT_ID}`);
  console.log('='.repeat(70));

  if (!fs.existsSync(SCREENSHOTS_DIR)) fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  const results = {
    testName: 'Test A: Supervisor Full Journey',
    checks: {},
    messageSnapshots: {},
    stageSnapshots: {},
    bugs: [],
  };

  try {
    // --- STEP 1: API auth ---
    console.log('\n[STEP 1] API authentication...');
    const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(CREDS),
    });
    const loginData = await loginRes.json();
    if (!loginData.access_token) throw new Error('Login failed: ' + JSON.stringify(loginData));
    authToken = loginData.access_token;
    console.log('  Auth OK. User:', loginData.user?.display_name);

    // Verify project exists and is in discover
    const initialStage = await checkStage('initial');
    if (!initialStage) throw new Error('Cannot fetch project stage');
    results.stageSnapshots.initial = initialStage;

    // --- STEP 2: Browser login ---
    console.log('\n[STEP 2] Browser login...');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await screenshot(page, '01-login');

    await page.locator('input[type="email"]').fill(CREDS.email);
    await page.locator('input[type="password"]').fill(CREDS.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });
    await page.waitForLoadState('networkidle');
    console.log('  Browser login OK. URL:', page.url());
    await screenshot(page, '02-after-login');

    // --- STEP 3: Navigate to lobby ---
    console.log('\n[STEP 3] Navigate to project lobby...');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    await screenshot(page, '03-lobby');
    console.log('  Lobby URL:', page.url());

    // Check seats are visible
    const seatCount = await page.locator('[data-testid*="seat"]').count();
    const allBtns = await page.locator('button').allTextContents();
    console.log('  Seat elements with data-testid:', seatCount);
    console.log('  All buttons:', allBtns.slice(0, 10).join(' | '));

    // --- STEP 4: Join as supervisor ---
    console.log('\n[STEP 4] Join as supervisor...');
    // Try to find supervisor seat button
    const supervisorBtnSelectors = [
      'button:has-text("入座")',
      'button:has-text("加入")',
      '[data-testid="seat-supervisor"]',
      'button:has-text("組長")',
    ];

    let joined = false;
    for (const sel of supervisorBtnSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.isVisible().catch(() => false)) {
        console.log(`  Found join button: ${sel}`);
        await btn.click();
        await sleep(2000);
        joined = true;
        break;
      }
    }

    if (!joined) {
      // Try clicking first available seat
      const firstSeat = page.locator('button').filter({ hasText: /入座|加入|Join/ }).first();
      if (await firstSeat.isVisible().catch(() => false)) {
        await firstSeat.click();
        await sleep(2000);
        joined = true;
        console.log('  Joined via first available seat button');
      } else {
        recordBug('BUG-A-01', 'CRITICAL', 'No join/seat button found in lobby',
          'Supervisor seat button should be visible in lobby',
          `No join button found. Buttons: ${allBtns.slice(0, 8).join(', ')}`);
      }
    }

    await screenshot(page, '04-after-join');
    console.log('  Post-join URL:', page.url());

    // Check if we auto-navigated to workspace
    const inWorkspace = page.url().includes('/workspace');
    if (inWorkspace) {
      console.log('  Auto-navigated to workspace');
    } else {
      // Try to manually navigate
      await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`);
      await page.waitForLoadState('networkidle');
      await sleep(2000);
    }

    await screenshot(page, '05-workspace-initial');
    console.log('  Workspace URL:', page.url());

    // =========================================================
    // STEP 5: DISCOVER PHASE — Monitor for 120 seconds
    // =========================================================
    console.log('\n[STEP 5] DISCOVER phase — monitoring for 120s...');
    const discoverStart = Date.now();

    // Check initial message state
    const msgCheck0 = await checkMessages('discover-0s');
    results.messageSnapshots['discover-0s'] = msgCheck0;
    const stageCheck0 = await checkStage('discover-0s');
    results.stageSnapshots['discover-0s'] = stageCheck0;

    // 30-second checkpoint
    console.log('\n  Waiting 30s...');
    await sleep(30000);
    const msgCheck30 = await checkMessages('discover-30s');
    results.messageSnapshots['discover-30s'] = msgCheck30;
    const stageCheck30 = await checkStage('discover-30s');
    results.stageSnapshots['discover-30s'] = stageCheck30;
    await screenshot(page, '06-discover-30s');

    // 60-second checkpoint
    console.log('\n  Waiting another 30s (total 60s)...');
    await sleep(30000);
    const msgCheck60 = await checkMessages('discover-60s');
    results.messageSnapshots['discover-60s'] = msgCheck60;
    const stageCheck60 = await checkStage('discover-60s');
    results.stageSnapshots['discover-60s'] = stageCheck60;
    await screenshot(page, '07-discover-60s');

    // 120-second checkpoint
    console.log('\n  Waiting another 60s (total 120s)...');
    await sleep(60000);
    const msgCheck120 = await checkMessages('discover-120s');
    results.messageSnapshots['discover-120s'] = msgCheck120;
    const stageCheck120 = await checkStage('discover-120s');
    results.stageSnapshots['discover-120s'] = stageCheck120;
    await screenshot(page, '08-discover-120s');

    // --- Analyze DISCOVER results ---
    console.log('\n  === DISCOVER ANALYSIS ===');

    // Check 1: All 5 agents contributing
    const senders120 = msgCheck120.senders;
    const expectedAgents = ['agent_supervisor', 'agent_crew_1', 'agent_crew_2', 'agent_crew_3', 'agent_crew_4'];
    const activeAgents = expectedAgents.filter(a => (senders120[a] || 0) > 0);
    results.checks.allAgentsActive = activeAgents.length === 5;
    console.log(`  Active agents (${activeAgents.length}/5): ${activeAgents.join(', ')}`);
    if (activeAgents.length < 5) {
      const silent = expectedAgents.filter(a => !(senders120[a] || 0));
      recordBug('BUG-A-02', 'HIGH', `Only ${activeAgents.length}/5 agents contributed in DISCOVER`,
        'All 5 agents should contribute messages',
        `Silent agents: ${silent.join(', ')}`);
    }

    // Check 2: More than 15 messages (regression test for Rule 4.5 stall)
    results.checks.exceeds15Messages = msgCheck120.total > 15;
    console.log(`  Total messages at 120s: ${msgCheck120.total} (>15 expected)`);
    if (msgCheck120.total <= 15) {
      recordBug('BUG-A-03', 'CRITICAL', `Only ${msgCheck120.total} messages after 120s — possible Rule 4.5 stall`,
        'More than 15 messages should be generated in 120s',
        `Only ${msgCheck120.total} messages. Possible deadlock regression`);
    }

    // Check 3: Agents still active at 120s (not just early messages)
    const msgsBefore60 = msgCheck60.total;
    const msgsAfter60 = msgCheck120.total - msgsBefore60;
    results.checks.agentsActiveAfter60s = msgsAfter60 > 0;
    console.log(`  Messages 0-60s: ${msgsBefore60} | Messages 60-120s: ${msgsAfter60}`);
    if (msgsAfter60 === 0) {
      recordBug('BUG-A-04', 'HIGH', 'No new messages generated between 60s and 120s — agents stalled',
        'Agents should continue generating messages throughout DISCOVER',
        'No new messages in the 60-120s window');
    }

    // Check 4: Template pattern detection
    if (msgCheck120.templateCount > 0) {
      recordBug('BUG-A-05', 'HIGH', `${msgCheck120.templateCount} messages contain template patterns (@{crew_N} or bare crew_N)`,
        'All template placeholders should be resolved in messages',
        `${msgCheck120.templateCount} unresolved templates found`);
    }
    results.checks.noTemplatePatterns = msgCheck120.templateCount === 0;

    // --- Wait up to 3 min total for evaluator auto-advance ---
    console.log('\n  Waiting for evaluator auto-advance (up to 60 more seconds)...');
    let autoAdvanced = false;
    for (let i = 0; i < 6; i++) {
      await sleep(10000);
      const stageNow = await checkStage(`auto-advance-check-${i}`);
      if (stageNow && stageNow.current_micro_phase !== '1.1') {
        autoAdvanced = true;
        console.log(`  AUTO-ADVANCE detected! Micro phase: ${stageNow.current_micro_phase}`);
        break;
      }
    }
    results.checks.evaluatorAutoAdvanced = autoAdvanced;
    if (!autoAdvanced) {
      console.log('  No auto-advance in 180s — will manually advance to DEFINE');
      // Manually advance
      const advRes = await apiPost(`/api/projects/${PROJECT_ID}/advance-stage`, {});
      console.log(`  Manual advance response: ${advRes.status}`);
    }

    // =========================================================
    // STEP 6: DEFINE PHASE — 90 seconds
    // =========================================================
    console.log('\n[STEP 6] DEFINE phase — monitoring for 90s...');
    await sleep(5000);
    const stageDefine = await checkStage('define-start');
    results.stageSnapshots['define-start'] = stageDefine;
    await screenshot(page, '09-define-start');

    await sleep(45000);
    const msgDefine45 = await checkMessages('define-45s');
    results.messageSnapshots['define-45s'] = msgDefine45;

    await sleep(45000);
    const msgDefine90 = await checkMessages('define-90s');
    const stageDefine90 = await checkStage('define-90s');
    results.messageSnapshots['define-90s'] = msgDefine90;
    results.stageSnapshots['define-90s'] = stageDefine90;
    await screenshot(page, '10-define-90s');

    results.checks.definePhaseActive = msgDefine90.total > msgCheck120.total;
    console.log(`  New messages in DEFINE: ${msgDefine90.total - msgCheck120.total}`);

    // Advance to DEVELOP
    console.log('  Advancing to DEVELOP...');
    const advDev = await apiPost(`/api/projects/${PROJECT_ID}/advance-stage`, {});
    console.log(`  Advance to DEVELOP: ${advDev.status}`);

    // =========================================================
    // STEP 7: DEVELOP PHASE — 90 seconds
    // =========================================================
    console.log('\n[STEP 7] DEVELOP phase — monitoring for 90s...');
    await sleep(5000);
    const stageDevelop = await checkStage('develop-start');
    results.stageSnapshots['develop-start'] = stageDevelop;
    await screenshot(page, '11-develop-start');

    await sleep(90000);
    const msgDevelop90 = await checkMessages('develop-90s');
    const stageDevelop90 = await checkStage('develop-90s');
    results.messageSnapshots['develop-90s'] = msgDevelop90;
    results.stageSnapshots['develop-90s'] = stageDevelop90;
    await screenshot(page, '12-develop-90s');

    results.checks.developPhaseActive = msgDevelop90.total > msgDefine90.total;
    console.log(`  New messages in DEVELOP: ${msgDevelop90.total - msgDefine90.total}`);

    // Advance to DELIVER
    console.log('  Advancing to DELIVER...');
    const advDel = await apiPost(`/api/projects/${PROJECT_ID}/advance-stage`, {});
    console.log(`  Advance to DELIVER: ${advDel.status}`);

    // =========================================================
    // STEP 8: DELIVER PHASE — 60 seconds
    // =========================================================
    console.log('\n[STEP 8] DELIVER phase — monitoring for 60s...');
    await sleep(5000);
    const stageDeliver = await checkStage('deliver-start');
    results.stageSnapshots['deliver-start'] = stageDeliver;
    await screenshot(page, '13-deliver-start');

    // Check no advance button visible (final stage)
    const advanceBtnDeliver = page.locator('button').filter({ hasText: /下一階段|推進|Advance/ });
    const advanceBtnVisible = await advanceBtnDeliver.isVisible().catch(() => false);
    results.checks.noAdvanceButtonInDeliver = !advanceBtnVisible;
    if (advanceBtnVisible) {
      recordBug('BUG-A-06', 'MEDIUM', 'Advance button visible in DELIVER (final stage)',
        'No advance button in DELIVER stage',
        'Advance button still visible');
    }

    await sleep(60000);
    const msgDeliver60 = await checkMessages('deliver-60s');
    const stageDeliver60 = await checkStage('deliver-60s');
    results.messageSnapshots['deliver-60s'] = msgDeliver60;
    results.stageSnapshots['deliver-60s'] = stageDeliver60;
    await screenshot(page, '14-deliver-60s');

    results.checks.deliverPhaseActive = msgDeliver60.total > msgDevelop90.total;
    console.log(`  New messages in DELIVER: ${msgDeliver60.total - msgDevelop90.total}`);

    // --- FINAL API CHECKS ---
    console.log('\n[STEP 9] Final API checks...');
    const finalMessages = await checkMessages('final');
    const finalStage = await checkStage('final');
    const microHistory = await apiGet(`/api/projects/${PROJECT_ID}/micro-phase-history`);
    const history = await apiGet(`/api/projects/${PROJECT_ID}/history`);

    results.final = {
      totalMessages: finalMessages.total,
      uniqueSenders: Object.keys(finalMessages.senders).length,
      senderBreakdown: finalMessages.senders,
      stage: finalStage,
      microPhaseHistory: microHistory,
      stageHistory: history,
    };

    console.log('  Final total messages:', finalMessages.total);
    console.log('  Unique senders:', Object.keys(finalMessages.senders).length);
    console.log('  Final stage:', finalStage?.current_stage);
    await screenshot(page, '15-final');

  } catch (err) {
    console.error('\nFATAL ERROR:', err.message);
    results.fatalError = err.message;
    await screenshot(page, 'fatal-error');
  } finally {
    await browser.close();
  }

  // =========================================================
  // REPORT
  // =========================================================
  results.bugs = bugs;
  results.consoleErrors = consoleErrors.slice(0, 10);

  const reportPath = path.join(__dirname, 'qa-final1-supervisor-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));

  console.log('\n' + '='.repeat(70));
  console.log('TEST A SUMMARY');
  console.log('='.repeat(70));

  const checks = results.checks;
  const checkItems = [
    ['All 5 agents contributing', checks.allAgentsActive],
    ['Exceeds 15 messages (no stall)', checks.exceeds15Messages],
    ['Agents active after 60s', checks.agentsActiveAfter60s],
    ['No template patterns', checks.noTemplatePatterns],
    ['Evaluator auto-advanced micro-phase', checks.evaluatorAutoAdvanced],
    ['DEFINE phase active', checks.definePhaseActive],
    ['DEVELOP phase active', checks.developPhaseActive],
    ['DELIVER phase active', checks.deliverPhaseActive],
    ['No advance button in DELIVER', checks.noAdvanceButtonInDeliver],
  ];

  let passed = 0;
  for (const [name, result] of checkItems) {
    const icon = result === true ? 'PASS' : result === false ? 'FAIL' : 'SKIP';
    console.log(`  [${icon}] ${name}`);
    if (result === true) passed++;
  }

  console.log(`\nPassed: ${passed}/${checkItems.filter(c => c[1] !== undefined).length}`);
  console.log(`Bugs found: ${bugs.length}`);
  if (bugs.length > 0) {
    console.log('\nBugs:');
    for (const b of bugs) {
      console.log(`  ${b.id} [${b.severity}]: ${b.description}`);
    }
  }
  console.log(`\nReport: ${reportPath}`);

  return results;
}

main().catch(err => {
  console.error('Uncaught error:', err);
  process.exit(1);
});
