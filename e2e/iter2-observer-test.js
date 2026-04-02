/**
 * Iteration 2 Observer Mode E2E Test
 * Tests: observer chat disabled fix, crew agent mention detection fix, micro_phase reset fix
 *
 * Pre-created project via API:
 *   ID: 7df503a4-0fb2-4cd5-8e8a-7493b3c8c54c
 *   Name: Iter2-Observer-購物車設計觀察
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const PROJECT_ID = '7df503a4-0fb2-4cd5-8e8a-7493b3c8c54c';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

const issues = [];
const checkResults = [];
let screenshotCounter = 0;
let accessToken = null;

function recordIssue(id, severity, description, expected, actual, screenshotFile) {
  issues.push({ id, severity, description, expected, actual, screenshotFile });
  const prefix = severity === 'CRITICAL' ? '[!!!CRITICAL!!!]' : `[${severity}]`;
  console.log(`\n${prefix} Issue ${id}: ${description}`);
  console.log(`  Expected: ${expected}`);
  console.log(`  Actual:   ${actual}`);
  if (screenshotFile) console.log(`  Screenshot: ${screenshotFile}`);
}

function recordCheck(name, passed, detail) {
  checkResults.push({ name, passed, detail });
  const icon = passed ? 'PASS' : 'FAIL';
  console.log(`  [${icon}] ${name}: ${detail}`);
}

async function takeScreenshot(page, name) {
  screenshotCounter++;
  const filename = `iter2-obs-${String(screenshotCounter).padStart(2, '0')}-${name}.png`;
  const filepath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  console.log(`  [screenshot] ${filename}`);
  return filename;
}

async function apiRequest(method, urlPath, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(`${BACKEND_URL}${urlPath}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  try {
    return { status: response.status, data: JSON.parse(text) };
  } catch {
    return { status: response.status, data: text };
  }
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getMessages(token, projectId) {
  const res = await apiRequest('GET', `/api/projects/${projectId}/messages?limit=200`, null, token);
  if (res.status === 200 && Array.isArray(res.data)) return res.data;
  if (res.status === 200 && res.data.messages) return res.data.messages;
  return [];
}

async function getStageInfo(token, projectId) {
  const res = await apiRequest('GET', `/api/projects/${projectId}/stage`, null, token);
  return res.status === 200 ? res.data : null;
}

function analyzeMessages(messages) {
  const senderCounts = {};
  const templatePatterns = [];

  for (const msg of messages) {
    const sender = msg.sender_id || msg.agent_id || msg.role || 'unknown';
    senderCounts[sender] = (senderCounts[sender] || 0) + 1;

    const content = msg.content || msg.message || '';
    // Check for unresolved template patterns like @{crew_N} or {crew_N}
    if (/\{crew_\d+\}/.test(content) || /@\{crew_\d+\}/.test(content)) {
      templatePatterns.push({ sender, content: content.substring(0, 120) });
    }
  }

  return { senderCounts, templatePatterns };
}

async function runTest() {
  console.log('=== Iteration 2 Observer Mode E2E Test ===');
  console.log(`Project ID: ${PROJECT_ID}`);
  console.log(`Timestamp: ${new Date().toISOString()}\n`);

  // --- Step 0: API login to get token ---
  console.log('[Step 0] API login...');
  const loginRes = await apiRequest('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD });
  if (loginRes.status !== 200 || !loginRes.data.access_token) {
    console.error('FATAL: API login failed', loginRes);
    process.exit(1);
  }
  accessToken = loginRes.data.access_token;
  console.log(`  Token acquired. User: ${loginRes.data.user.display_name}`);

  // --- Step 1: Verify initial stage state via API ---
  console.log('\n[Step 1] Verify initial stage state...');
  const stageInfo = await getStageInfo(accessToken, PROJECT_ID);
  if (stageInfo) {
    recordCheck(
      'Initial stage = discover',
      stageInfo.current_stage === 'discover',
      `current_stage=${stageInfo.current_stage}`
    );
    recordCheck(
      'Initial micro_phase = 1.1',
      stageInfo.current_micro_phase === '1.1',
      `current_micro_phase=${stageInfo.current_micro_phase}`
    );
    console.log(`  Stage info: ${JSON.stringify(stageInfo)}`);
  } else {
    recordIssue('API-001', 'CRITICAL', 'Cannot fetch stage info', 'HTTP 200', 'Request failed');
  }

  // --- Step 2: Browser — login and navigate to lobby ---
  console.log('\n[Step 2] Browser — login and navigate to lobby...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    await page.goto(`${FRONTEND_URL}/login`);
    await page.waitForLoadState('networkidle');
    const ssLogin = await takeScreenshot(page, 'login-page');

    // Fill login form
    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    await emailInput.fill(EMAIL);
    await passwordInput.fill(PASSWORD);
    await page.keyboard.press('Enter');
    await page.waitForLoadState('networkidle');
    await sleep(1500);
    const ssAfterLogin = await takeScreenshot(page, 'after-login');
    console.log(`  Current URL after login: ${page.url()}`);

    // --- Step 3: Navigate to project lobby ---
    console.log('\n[Step 3] Navigate to project lobby...');
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    const ssLobby = await takeScreenshot(page, 'lobby');
    console.log(`  Lobby URL: ${page.url()}`);

    // --- Step 4: Find and click observer button ---
    console.log('\n[Step 4] Click "以觀察者身份進入" button...');
    const observerBtnSelectors = [
      'button:has-text("以觀察者身份進入")',
      'button:has-text("觀察者")',
      '[data-testid="observer-btn"]',
      'button:has-text("Observer")',
    ];
    let observerBtn = null;
    for (const sel of observerBtnSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.isVisible().catch(() => false)) {
        observerBtn = btn;
        console.log(`  Found observer button with selector: ${sel}`);
        break;
      }
    }

    if (!observerBtn) {
      const allButtons = await page.locator('button').allTextContents();
      console.log(`  Available buttons: ${JSON.stringify(allButtons)}`);
      recordIssue('OBS-001', 'CRITICAL', 'Observer button not found on lobby page',
        '"以觀察者身份進入" button visible', 'Button not found',
        await takeScreenshot(page, 'no-observer-btn'));
    } else {
      await observerBtn.click();
      await page.waitForLoadState('networkidle');
      await sleep(2000);
      const ssObserverEntered = await takeScreenshot(page, 'observer-entered');
      console.log(`  URL after observer click: ${page.url()}`);
    }

    // --- Step 5: Verify observer restrictions (CRITICAL) ---
    console.log('\n[Step 5] Verify observer restrictions (CRITICAL)...');
    await sleep(1500);
    const ssWorkspace = await takeScreenshot(page, 'workspace-initial');

    // Check chat input disabled (BUG-001 fix verification)
    const chatInputSelectors = [
      'textarea[placeholder*="訊息" i]',
      'textarea[placeholder*="message" i]',
      'input[placeholder*="訊息" i]',
      '[data-testid="chat-input"]',
      '.chat-input textarea',
      '.chat-input input',
    ];

    let chatInputFound = false;
    let chatInputDisabled = false;
    let chatInputScreenshot = null;

    for (const sel of chatInputSelectors) {
      const el = page.locator(sel).first();
      if (await el.isVisible().catch(() => false)) {
        chatInputFound = true;
        chatInputDisabled = await el.isDisabled().catch(() => false);
        console.log(`  Chat input found (${sel}): disabled=${chatInputDisabled}`);
        chatInputScreenshot = await takeScreenshot(page, 'chat-input-state');
        break;
      }
    }

    // Also check if chat section is entirely hidden
    const chatSectionHidden = await page.locator('.chat-panel, [data-testid="chat-panel"]')
      .first().isHidden().catch(() => true);

    if (!chatInputFound) {
      // Chat input might be hidden entirely (that's also acceptable)
      recordCheck(
        'Observer chat input hidden/disabled (BUG-001 fix)',
        chatSectionHidden,
        chatSectionHidden ? 'Chat panel is hidden for observer' : 'Chat input not found in DOM'
      );
      if (!chatSectionHidden) {
        recordIssue('OBS-002', 'HIGH', 'Chat input not found but chat panel also not confirmed hidden',
          'Chat disabled or hidden for observer', 'Element state unclear');
      }
    } else {
      recordCheck(
        'Observer chat input is disabled (BUG-001 fix)',
        chatInputDisabled,
        chatInputDisabled ? 'INPUT IS DISABLED - BUG-001 fixed' : 'INPUT IS ENABLED - BUG-001 NOT FIXED'
      );
      if (!chatInputDisabled) {
        recordIssue('OBS-BUG001', 'CRITICAL', 'Observer can still type in chat input (BUG-001 not fixed)',
          'Chat input disabled for observer', 'Chat input is enabled/clickable', chatInputScreenshot);
      }
    }

    // Check "推進到" button NOT visible for observer
    const advanceBtnSelectors = [
      'button:has-text("推進到")',
      'button:has-text("Advance")',
      '[data-testid="advance-stage-btn"]',
    ];
    let advanceBtnVisible = false;
    for (const sel of advanceBtnSelectors) {
      if (await page.locator(sel).first().isVisible().catch(() => false)) {
        advanceBtnVisible = true;
        console.log(`  WARNING: Advance button visible with selector: ${sel}`);
        break;
      }
    }
    recordCheck(
      'Advance stage button hidden for observer',
      !advanceBtnVisible,
      advanceBtnVisible ? 'BUTTON IS VISIBLE (should be hidden)' : 'Button correctly hidden'
    );
    if (advanceBtnVisible) {
      recordIssue('OBS-003', 'MEDIUM', '"推進到" button visible for observer',
        'Button should be hidden', 'Button is visible',
        await takeScreenshot(page, 'advance-btn-visible'));
    }

    // --- Step 6: Watch Discover Phase for 90 seconds ---
    console.log('\n[Step 6] Watch Discover Phase (90 seconds)...');
    console.log('  t=0s: Starting observation...');

    const t0 = Date.now();
    const msgsBefore = await getMessages(accessToken, PROJECT_ID);
    console.log(`  Messages at start: ${msgsBefore.length}`);

    // Screenshot at 30s
    await sleep(30000);
    const ss30s = await takeScreenshot(page, 'discover-30s');
    const msgs30 = await getMessages(accessToken, PROJECT_ID);
    console.log(`  t=30s: ${msgs30.length} messages`);

    // Screenshot at 60s
    await sleep(30000);
    const ss60s = await takeScreenshot(page, 'discover-60s');
    const msgs60 = await getMessages(accessToken, PROJECT_ID);
    console.log(`  t=60s: ${msgs60.length} messages`);

    // Screenshot at 90s
    await sleep(30000);
    const ss90s = await takeScreenshot(page, 'discover-90s');
    const msgs90 = await getMessages(accessToken, PROJECT_ID);
    console.log(`  t=90s: ${msgs90.length} messages`);

    const totalElapsed = Math.round((Date.now() - t0) / 1000);
    console.log(`  Total elapsed: ${totalElapsed}s`);

    // Analyze messages for crew activity
    const analysis = analyzeMessages(msgs90);
    console.log('\n  Message sender breakdown:');
    for (const [sender, count] of Object.entries(analysis.senderCounts)) {
      console.log(`    ${sender}: ${count} messages`);
    }

    const uniqueSenders = Object.keys(analysis.senderCounts).length;
    recordCheck(
      'Multiple agents active (>=3 unique senders)',
      uniqueSenders >= 3,
      `${uniqueSenders} unique senders: ${Object.keys(analysis.senderCounts).join(', ')}`
    );

    const hasCrewActivity = Object.keys(analysis.senderCounts).some(s =>
      s.includes('crew') || s.includes('agent_crew')
    );
    recordCheck(
      'Crew agents are sending messages',
      hasCrewActivity,
      hasCrewActivity ? 'Crew agents active' : 'No crew agent messages detected'
    );
    if (!hasCrewActivity) {
      recordIssue('CREW-001', 'HIGH', 'No crew agent messages detected in 90s',
        'Crew agents (crew_1..4) should be chatting', 'Only supervisor messages found',
        ss90s);
    }

    // Check template patterns
    if (analysis.templatePatterns.length > 0) {
      console.log(`\n  WARNING: Template patterns found in ${analysis.templatePatterns.length} messages:`);
      for (const tp of analysis.templatePatterns.slice(0, 5)) {
        console.log(`    [${tp.sender}] ${tp.content}`);
      }
      recordIssue('TMPL-001', 'HIGH', 'Unresolved @{crew_N} template patterns in messages',
        'No template patterns', `${analysis.templatePatterns.length} messages with patterns`);
    } else {
      recordCheck('No template patterns in messages', true, 'No @{crew_N} patterns found');
    }

    // Check for canvas notes
    const canvasNotesRes = await apiRequest('GET', `/api/projects/${PROJECT_ID}/canvas`, null, accessToken);
    const hasCanvas = canvasNotesRes.status === 200;
    const noteCount = hasCanvas && canvasNotesRes.data.notes ? canvasNotesRes.data.notes.length : 0;
    console.log(`\n  Canvas state: status=${canvasNotesRes.status}, notes=${noteCount}`);
    recordCheck(
      'Canvas has sticky notes',
      noteCount > 0,
      noteCount > 0 ? `${noteCount} notes on canvas` : 'No notes on canvas (check Yjs/WebSocket)'
    );
    await takeScreenshot(page, 'canvas-state');

    // Check micro_phase progression
    const stageAfter90 = await getStageInfo(accessToken, PROJECT_ID);
    if (stageAfter90) {
      console.log(`\n  Stage after 90s: ${JSON.stringify(stageAfter90)}`);
      recordCheck(
        'micro_phase progressed from 1.1',
        stageAfter90.current_micro_phase !== '1.1',
        `current_micro_phase=${stageAfter90.current_micro_phase}`
      );
    }

    // --- Step 7: Attempt API stage advance (observer restriction check) ---
    console.log('\n[Step 7] Attempt stage advance via API...');
    const advanceRes = await apiRequest('POST', `/api/projects/${PROJECT_ID}/advance-stage`,
      { from: 'discover', to: 'define' }, accessToken
    );
    console.log(`  Advance API response: status=${advanceRes.status}, data=${JSON.stringify(advanceRes.data)}`);

    if (advanceRes.status === 403) {
      recordCheck('Observer cannot advance stage via API (403)', true, 'Got 403 as expected');
    } else if (advanceRes.status === 200) {
      // Success — check micro_phase reset (the reported bug fix)
      const stageAfterAdvance = await getStageInfo(accessToken, PROJECT_ID);
      if (stageAfterAdvance) {
        console.log(`  Stage after advance: ${JSON.stringify(stageAfterAdvance)}`);
        const expectedMicroPhase = '2.1';
        const microPhaseResetCorrect = stageAfterAdvance.current_micro_phase === expectedMicroPhase;
        recordCheck(
          `micro_phase resets to 2.1 after advance to define (stage_advance reset fix)`,
          microPhaseResetCorrect,
          `current_micro_phase=${stageAfterAdvance.current_micro_phase}, expected=${expectedMicroPhase}`
        );
        if (!microPhaseResetCorrect) {
          recordIssue('MICRO-001', 'HIGH', 'micro_phase not reset after stage advance',
            'micro_phase should reset to 2.1 when advancing to define',
            `Got: ${stageAfterAdvance.current_micro_phase}`);
        }
        await takeScreenshot(page, 'after-advance-define');
      }
    } else {
      recordCheck('Advance API response', false, `Unexpected status ${advanceRes.status}`);
    }

    // --- Step 8: Final state screenshot ---
    console.log('\n[Step 8] Final state...');
    await sleep(2000);
    const ssFinal = await takeScreenshot(page, 'final-state');

    const finalMsgs = await getMessages(accessToken, PROJECT_ID);
    const finalAnalysis = analyzeMessages(finalMsgs);
    console.log(`  Final message count: ${finalMsgs.length}`);
    console.log(`  Final unique senders: ${Object.keys(finalAnalysis.senderCounts).length}`);
    for (const [sender, count] of Object.entries(finalAnalysis.senderCounts)) {
      console.log(`    ${sender}: ${count} messages`);
    }

  } catch (err) {
    console.error('\nFATAL TEST ERROR:', err.message);
    await takeScreenshot(page, 'fatal-error').catch(() => {});
    recordIssue('FATAL-001', 'CRITICAL', `Test crashed: ${err.message}`,
      'Test completes without error', err.message);
  } finally {
    await browser.close();
  }

  // --- Report ---
  console.log('\n=== TEST REPORT ===\n');
  console.log('CHECKS:');
  for (const c of checkResults) {
    console.log(`  [${c.passed ? 'PASS' : 'FAIL'}] ${c.name}: ${c.detail}`);
  }

  const passed = checkResults.filter(c => c.passed).length;
  const failed = checkResults.filter(c => !c.passed).length;
  console.log(`\n  Total checks: ${checkResults.length}  Passed: ${passed}  Failed: ${failed}`);

  if (issues.length === 0) {
    console.log('\nISSUES: None found!');
  } else {
    console.log(`\nISSUES (${issues.length}):`);
    for (const issue of issues) {
      const prefix = issue.severity === 'CRITICAL' ? '[!!!CRITICAL!!!]' : `[${issue.severity}]`;
      console.log(`\n  ${prefix} ${issue.id}: ${issue.description}`);
      console.log(`    Expected: ${issue.expected}`);
      console.log(`    Actual:   ${issue.actual}`);
    }
  }

  const criticalCount = issues.filter(i => i.severity === 'CRITICAL').length;
  const highCount = issues.filter(i => i.severity === 'HIGH').length;
  console.log(`\nSEVERITY SUMMARY: ${criticalCount} CRITICAL, ${highCount} HIGH, ${issues.length - criticalCount - highCount} others`);

  // Save JSON report
  const report = {
    timestamp: new Date().toISOString(),
    project_id: PROJECT_ID,
    iteration: 2,
    test_type: 'observer-mode',
    checks: checkResults,
    issues,
    summary: { total: checkResults.length, passed, failed, critical: criticalCount, high: highCount }
  };
  const reportPath = path.join(__dirname, 'iter2-observer-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport saved: ${reportPath}`);

  process.exit(issues.some(i => i.severity === 'CRITICAL') ? 1 : 0);
}

runTest().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
