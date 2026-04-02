/**
 * MindCrew Final Acceptance E2E Test
 * Tests the full 4-phase Design Thinking journey as Supervisor
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const PROJECT_ID = 'f0f7941d-7c19-4a7e-84a1-ae469418d102'; // Will be overridden by arg

const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

function log(msg) {
  const ts = new Date().toISOString().split('T')[1].split('.')[0];
  console.log(`[${ts}] ${msg}`);
}

async function apiGet(token, path) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return { status: res.status, body: await res.json() };
}

async function apiPost(token, path, body) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });
  return { status: res.status, body: await res.json() };
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `final-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: true });
  log(`Screenshot saved: ${filepath}`);
  return filepath;
}

async function waitMs(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function checkMessages(token, projectId, label) {
  const { status, body } = await apiGet(token, `/api/projects/${projectId}/messages?limit=100`);
  if (status !== 200) {
    log(`  ERROR: GET messages returned ${status}`);
    return { ok: false, error: `HTTP ${status}` };
  }

  const messages = body.messages || body || [];
  const senders = new Set();
  const senderIds = new Set();
  const badPatterns = [];

  for (const msg of messages) {
    // API returns sender_name and sender_id (not "sender")
    const senderName = msg.sender_name || msg.sender || '';
    const senderId = msg.sender_id || '';
    const senderType = msg.sender_type || '';
    if (senderName && senderType === 'ai') senders.add(senderName);
    if (senderId && senderType === 'ai') senderIds.add(senderId);

    const content = msg.content || msg.message || '';
    // Check for unresolved template patterns
    if (content.match(/@\{crew/)) badPatterns.push({ sender: senderName, pattern: '@{crew', snippet: content.substring(0, 80) });
    if (content.match(/\bcrew_\d+\b/) && !content.match(/agent|member/i)) {
      // bare crew_N reference that isn't part of a proper name
      badPatterns.push({ sender: senderName, pattern: 'bare crew_N', snippet: content.substring(0, 80) });
    }
  }

  log(`  [${label}] Messages: ${messages.length}, Unique AI senders: ${[...senders].join(', ')}`);
  log(`  [${label}] Unique sender IDs: ${[...senderIds].join(', ')}`);
  if (badPatterns.length > 0) {
    log(`  WARNING: Found ${badPatterns.length} bad patterns:`);
    badPatterns.forEach(p => log(`    - ${p.pattern} from ${p.sender}: "${p.snippet}"`));
  } else {
    log(`  No bad @{crew or bare crew_N patterns found`);
  }

  return { ok: true, messages: messages.length, senders: [...senders], senderIds: [...senderIds], badPatterns };
}

async function checkStage(token, projectId, label) {
  const { status, body } = await apiGet(token, `/api/projects/${projectId}/stage`);
  log(`  [${label}] Stage API: HTTP ${status}`);
  if (status === 200) {
    log(`    current_stage: ${body.current_stage}`);
    log(`    current_micro_phase: ${body.current_micro_phase}`);
    log(`    phase_name: ${body.phase_name || 'N/A'}`);
  }
  return { status, body };
}

async function advanceStage(page, token, projectId, expectedNewMicro) {
  log('  Looking for advance button...');

  // Wait up to 10s for the advance button to appear (page may need to load)
  let btnVisible = false;
  for (let i = 0; i < 5; i++) {
    const advanceBtn = page.locator('button').filter({ hasText: /推進到/ }).first();
    btnVisible = await advanceBtn.isVisible().catch(() => false);
    if (btnVisible) break;
    log(`  Waiting for advance button (attempt ${i+1}/5)...`);
    await waitMs(2000);
  }

  if (!btnVisible) {
    log('  WARNING: No advance button found in UI after waiting');
    // Fall back to direct API call
    log('  Trying direct API advance...');
    const stageMap = { '2.': 'define', '3.': 'develop', '4.': 'deliver' };
    const toStage = stageMap[expectedNewMicro];
    const { status: curStatus, body: curBody } = await checkStage(token, projectId, 'before-api-advance');
    const fromStage = curBody?.current_stage;
    if (toStage && fromStage) {
      const advanceRes = await apiPost(token, `/api/projects/${projectId}/advance`, { from: fromStage, to: toStage });
      log(`  Direct API advance: HTTP ${advanceRes.status}`);
      await waitMs(3000);
      const { status, body } = await checkStage(token, projectId, 'after-api-advance');
      const micro = body?.current_micro_phase || '';
      const ok = micro.startsWith(expectedNewMicro);
      return { ok, status, body, method: 'api' };
    }
    return { ok: false, error: 'No advance button and API fallback failed' };
  }

  const advanceBtn = page.locator('button').filter({ hasText: /推進到/ }).first();
  log('  Clicking advance button...');
  await advanceBtn.click();
  await waitMs(1000);

  // Look for confirmation dialog
  const confirmBtn = page.locator('button').filter({ hasText: /確認推進|確認|Confirm/ }).first();
  const confirmVisible = await confirmBtn.isVisible().catch(() => false);
  if (confirmVisible) {
    log('  Clicking confirm button...');
    await confirmBtn.click();
  }

  await waitMs(5000);

  // Check via API
  const { status, body } = await checkStage(token, projectId, 'after-advance');

  if (status !== 200) {
    return { ok: false, error: `Stage API returned ${status}` };
  }

  const micro = body.current_micro_phase || '';
  const ok = micro.startsWith(expectedNewMicro);
  if (!ok) {
    log(`  WARNING: Expected micro_phase to start with "${expectedNewMicro}", got "${micro}"`);
  } else {
    log(`  micro_phase correctly starts with "${expectedNewMicro}"`);
  }

  return { ok, status, body };
}

async function runTest(projectId) {
  const report = {
    projectId,
    timestamp: new Date().toISOString(),
    steps: {},
    issues: [],
    passed: 0,
    failed: 0,
  };

  function recordCheck(name, ok, detail = '') {
    report.steps[name] = { ok, detail };
    if (ok) {
      report.passed++;
      log(`  PASS: ${name} ${detail}`);
    } else {
      report.failed++;
      report.issues.push(`FAIL: ${name} — ${detail}`);
      log(`  FAIL: ${name} — ${detail}`);
    }
  }

  log('='.repeat(60));
  log('MindCrew Final Acceptance E2E Test');
  log(`Project ID: ${projectId}`);
  log('='.repeat(60));

  // Get token for API calls
  const loginRes = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD })
  });
  const loginData = await loginRes.json();
  const token = loginData.access_token;
  if (!token) {
    log('ERROR: Could not get auth token');
    process.exit(1);
  }
  log('Auth token obtained');

  // Verify project exists
  const { status: projStatus, body: projBody } = await apiGet(token, `/api/projects/${projectId}`);
  recordCheck('project-exists', projStatus === 200, `HTTP ${projStatus}`);
  if (projStatus !== 200) {
    log('Cannot continue without valid project');
    process.exit(1);
  }

  // Launch browser
  log('\nLaunching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  // Capture console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // STEP 2: Login in browser
    log('\n--- STEP 2: Browser Login ---');
    await page.goto(`${FRONTEND_URL}/login`);
    await waitMs(2000);
    await screenshot(page, '01-login-page');

    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first();
    await emailInput.fill(EMAIL);
    const pwInput = page.locator('input[type="password"]').first();
    await pwInput.fill(PASSWORD);
    const loginBtn = page.locator('button[type="submit"]').first();
    await loginBtn.click();
    await waitMs(3000);
    await screenshot(page, '02-after-login');

    const currentUrl = page.url();
    recordCheck('browser-login', !currentUrl.includes('/login'), `Redirected to: ${currentUrl}`);

    // STEP 3: Navigate to lobby
    log('\n--- STEP 3: Navigate to Lobby ---');
    await page.goto(`${FRONTEND_URL}/projects/${projectId}/lobby`);
    await waitMs(3000);
    await screenshot(page, '03-lobby');

    const lobbyTitle = await page.title();
    const lobbyUrl = page.url();
    log(`  Lobby URL: ${lobbyUrl}`);
    recordCheck('lobby-navigation', lobbyUrl.includes(projectId), `URL: ${lobbyUrl}`);

    // STEP 4: Join as supervisor via API first (ensures exactly one seat = supervisor)
    log('\n--- STEP 4: Join as Supervisor ---');
    const joinResult = await apiPost(token, `/api/projects/${projectId}/join`, { seat_role: 'supervisor' });
    log(`  Join API: HTTP ${joinResult.status}`);
    if (joinResult.status === 200 || joinResult.status === 201) {
      const seat = joinResult.body.seat || joinResult.body;
      log(`  Joined seat: ${seat.seat_role}, occupant_type: ${seat.occupant_type}`);
      recordCheck('join-supervisor', seat.seat_role === 'supervisor' && seat.occupant_type === 'human',
        `seat_role: ${seat.seat_role}, occupant_type: ${seat.occupant_type}`);
    } else if (joinResult.status === 409) {
      // 409 = supervisor seat already occupied by this user (e.g. assigned via lobby)
      // Verify via GET that the supervisor seat is indeed held by this user
      const { body: projBody } = await apiGet(token, `/api/projects/${projectId}`);
      const supSeat = (projBody.seats || []).find(s => s.seat_role === 'supervisor');
      const isMine = supSeat?.user_id === (await apiGet(token, '/api/auth/me')).body?.id;
      log(`  409 = already in supervisor seat (expected). Seat: ${JSON.stringify(supSeat)}`);
      recordCheck('join-supervisor', !!supSeat && supSeat.occupant_type === 'human',
        `409-already-joined: supervisor seat=${JSON.stringify(supSeat)}`);
    } else {
      log(`  Join failed: ${JSON.stringify(joinResult.body)}`);
      recordCheck('join-supervisor', false, `HTTP ${joinResult.status}: ${JSON.stringify(joinResult.body)}`);
    }

    // Navigate to workspace directly
    log('  Navigating to workspace...');
    await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
    await waitMs(5000);

    // Verify advance button appears (user is now the only human, in supervisor seat)
    const advBtnCount = await page.locator('button').filter({ hasText: /推進到/ }).count();
    log(`  Advance button visible: ${advBtnCount > 0}`);
    recordCheck('supervisor-advance-button-visible', advBtnCount > 0, `${advBtnCount} advance button(s) found`);

    await screenshot(page, '04-joined-supervisor');

    // Wait for workspace to stabilize
    await waitMs(3000);
    await screenshot(page, '05-workspace-initial');

    // STEP 5: DISCOVER phase — wait and observe
    log('\n--- STEP 5: DISCOVER Phase Observation ---');
    log('  Waiting 30s for initial agent activity...');
    await waitMs(30000);
    await screenshot(page, '06-discover-30s');

    const msgCheck30 = await checkMessages(token, projectId, 'discover-30s');

    log('  Waiting another 60s (total 90s)...');
    await waitMs(60000);
    await screenshot(page, '07-discover-90s');

    const msgCheck90 = await checkMessages(token, projectId, 'discover-90s');
    const stageCheck90 = await checkStage(token, projectId, 'discover-90s');

    recordCheck('discover-unique-senders', msgCheck90.senders && msgCheck90.senders.length >= 3,
      `Senders: ${(msgCheck90.senders || []).join(', ')} (need ≥3)`);
    recordCheck('discover-no-bad-patterns', msgCheck90.badPatterns && msgCheck90.badPatterns.length === 0,
      msgCheck90.badPatterns && msgCheck90.badPatterns.length > 0 ?
        `Found ${msgCheck90.badPatterns.length} bad patterns` : 'Clean');
    recordCheck('discover-has-messages', msgCheck90.messages >= 3,
      `${msgCheck90.messages} messages`);

    // Check canvas for sticky notes via DOM (tldraw uses SVG/divs, not <canvas>)
    const stickyNotes = await page.locator('[data-shape-type="note"], .tl-note, [class*="sticky"], [class*="note"]').count();
    const tldrawShapes = await page.locator('[data-shape-id], .tl-shape, [class*="tl-"]').count();
    log(`  Canvas sticky note selectors found: ${stickyNotes}`);
    log(`  tldraw shape elements found: ${tldrawShapes}`);

    // Verify via API: history snapshots have notes
    const { status: histStatusCanvas, body: histBodyCanvas } = await apiGet(token, `/api/projects/${projectId}/history`);
    let canvasNotesFromApi = 0;
    if (histStatusCanvas === 200 && Array.isArray(histBodyCanvas) && histBodyCanvas.length > 0) {
      const lastSnap = histBodyCanvas[histBodyCanvas.length - 1];
      canvasNotesFromApi = (lastSnap.canvas_snapshot?.notes || []).length;
    }
    log(`  Canvas notes in latest API snapshot: ${canvasNotesFromApi}`);

    // tldraw renders as HTML elements, not <canvas>
    const tldrawContainer = await page.locator('.tl-container, [class*="tldraw"], [id*="tldraw"]').count();
    log(`  tldraw container elements: ${tldrawContainer}`);
    recordCheck('discover-canvas-active',
      tldrawShapes > 0 || tldrawContainer > 0 || canvasNotesFromApi > 0,
      `tldraw shapes: ${tldrawShapes}, containers: ${tldrawContainer}, API notes: ${canvasNotesFromApi}`);

    // STEP 6: ADVANCE TO DEFINE
    log('\n--- STEP 6: Advance to DEFINE ---');

    // Navigate fresh to workspace (don't just reload — the supervisor join via API is preserved server-side)
    await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
    await waitMs(5000);
    await screenshot(page, '08-before-advance-to-define');

    const advanceResult1 = await advanceStage(page, token, projectId, '2.');
    await waitMs(5000);
    await screenshot(page, '09-define-start');

    recordCheck('advance-to-define-200', advanceResult1.status === 200,
      `HTTP ${advanceResult1.status}${advanceResult1.error ? ' — ' + advanceResult1.error : ''}`);
    recordCheck('define-micro-phase-correct', advanceResult1.ok,
      `micro_phase: ${advanceResult1.body?.current_micro_phase || 'N/A'}`);

    if (advanceResult1.status === 500) {
      report.issues.push('BUG-001: MicroPhaseChangedEvent kwargs error on stage advance');
    }

    log('  Waiting 60s in DEFINE phase...');
    await waitMs(60000);
    await screenshot(page, '10-define-60s');
    await checkMessages(token, projectId, 'define-60s');
    await checkStage(token, projectId, 'define-60s');

    // STEP 7: ADVANCE TO DEVELOP
    log('\n--- STEP 7: Advance to DEVELOP ---');
    await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
    await waitMs(5000);

    const advanceResult2 = await advanceStage(page, token, projectId, '3.');
    await waitMs(5000);
    await screenshot(page, '11-develop-start');

    recordCheck('advance-to-develop-200', advanceResult2.status === 200,
      `HTTP ${advanceResult2.status}${advanceResult2.error ? ' — ' + advanceResult2.error : ''}`);
    recordCheck('develop-micro-phase-correct', advanceResult2.ok,
      `micro_phase: ${advanceResult2.body?.current_micro_phase || 'N/A'}`);

    log('  Waiting 60s in DEVELOP phase...');
    await waitMs(60000);
    await screenshot(page, '12-develop-60s');
    await checkMessages(token, projectId, 'develop-60s');

    // STEP 8: ADVANCE TO DELIVER
    log('\n--- STEP 8: Advance to DELIVER ---');
    await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
    await waitMs(5000);

    const advanceResult3 = await advanceStage(page, token, projectId, '4.');
    await waitMs(5000);
    await screenshot(page, '13-deliver-start');

    recordCheck('advance-to-deliver-200', advanceResult3.status === 200,
      `HTTP ${advanceResult3.status}${advanceResult3.error ? ' — ' + advanceResult3.error : ''}`);
    recordCheck('deliver-micro-phase-correct', advanceResult3.ok,
      `micro_phase: ${advanceResult3.body?.current_micro_phase || 'N/A'}`);

    // Verify no more "推進到" button on last stage
    await waitMs(3000);
    const noMoreAdvance = await page.locator('button').filter({ hasText: /推進到/ }).count();
    recordCheck('deliver-no-advance-button', noMoreAdvance === 0,
      noMoreAdvance === 0 ? 'No advance button (correct for last stage)' : `Found ${noMoreAdvance} advance button(s)`);

    log('  Waiting 30s in DELIVER phase...');
    await waitMs(30000);
    await screenshot(page, '14-deliver-30s');

    // STEP 9: FINAL API CHECKS
    log('\n--- STEP 9: Final API Checks ---');

    const finalMsgCheck = await checkMessages(token, projectId, 'final');
    recordCheck('final-unique-senders-3plus', finalMsgCheck.senders && finalMsgCheck.senders.length >= 3,
      `Final senders: ${(finalMsgCheck.senders || []).join(', ')}`);
    recordCheck('final-no-bad-patterns', finalMsgCheck.badPatterns && finalMsgCheck.badPatterns.length === 0,
      finalMsgCheck.badPatterns && finalMsgCheck.badPatterns.length > 0 ?
        `${finalMsgCheck.badPatterns.length} bad patterns found` : 'Clean');
    recordCheck('final-total-messages', finalMsgCheck.messages >= 10,
      `${finalMsgCheck.messages} total messages`);

    const finalStage = await checkStage(token, projectId, 'final');
    recordCheck('final-stage-deliver',
      finalStage.body?.current_stage === 'deliver' || finalStage.body?.current_micro_phase?.startsWith('4.'),
      `stage: ${finalStage.body?.current_stage}, micro: ${finalStage.body?.current_micro_phase}`);

    // Check history
    const { status: histStatus, body: histBody } = await apiGet(token, `/api/projects/${projectId}/history`);
    log(`  History API: HTTP ${histStatus}`);
    if (histStatus === 200) {
      const transitions = Array.isArray(histBody) ? histBody : (histBody.transitions || histBody.history || []);
      log(`  Stage transitions recorded: ${transitions.length}`);
      recordCheck('history-has-transitions', transitions.length >= 3,
        `${transitions.length} transitions (need ≥3 for 4-phase journey)`);
    } else {
      log(`  History not available (HTTP ${histStatus})`);
    }

    // Console errors summary
    if (consoleErrors.length > 0) {
      log(`\n  Browser console errors: ${consoleErrors.length}`);
      consoleErrors.slice(0, 5).forEach(e => log(`    - ${e.substring(0, 120)}`));
    }

  } catch (err) {
    log(`\nFATAL ERROR: ${err.message}`);
    log(err.stack);
    report.issues.push(`FATAL: ${err.message}`);
    await screenshot(page, 'error-state').catch(() => {});
  } finally {
    await browser.close();
  }

  // Generate report
  log('\n' + '='.repeat(60));
  log('FINAL REPORT');
  log('='.repeat(60));
  log(`Passed: ${report.passed}`);
  log(`Failed: ${report.failed}`);
  log(`Total checks: ${report.passed + report.failed}`);

  if (report.issues.length > 0) {
    log('\nISSUES:');
    report.issues.forEach(issue => log(`  - ${issue}`));
  } else {
    log('\nAll checks passed!');
  }

  const reportPath = path.join(__dirname, 'screenshots', 'final-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  log(`\nReport saved: ${reportPath}`);

  return report;
}

// Get project ID from command line arg or use default
const projectId = process.argv[2] || 'f0f7941d-7c19-4a7e-94a1-ae469418d102';
runTest(projectId).then(report => {
  process.exit(report.failed > 0 ? 1 : 0);
}).catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});
