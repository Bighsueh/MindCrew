/**
 * Iteration 3 E2E Test: Supervisor Full DT Journey
 * Tests all 4 phases: Discover → Define → Develop → Deliver
 * Project ID: 9910cba9-f9a7-455e-a43b-d8315f41f421
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const TOKEN = '***REMOVED_JWT***';
const PROJECT_ID = '9910cba9-f9a7-455e-a43b-d8315f41f421';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

const report = {
  projectId: PROJECT_ID,
  timestamp: new Date().toISOString(),
  phases: {},
  bugs: [],
  summary: {}
};

function log(msg) {
  const ts = new Date().toISOString().substring(11, 19);
  console.log(`[${ts}] ${msg}`);
}

function reportBug(severity, description, details = {}) {
  const bug = { severity, description, details, time: new Date().toISOString() };
  report.bugs.push(bug);
  log(`BUG [${severity}] ${description}`);
}

async function apiGet(path) {
  const https = require('http');
  return new Promise((resolve, reject) => {
    const url = new URL(API_URL + path);
    const options = {
      hostname: url.hostname,
      port: url.port || 8000,
      path: url.pathname + url.search,
      method: 'GET',
      headers: { 'Authorization': `Bearer ${TOKEN}` }
    };
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { resolve({ raw: data }); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function takeScreenshot(page, name) {
  const filepath = path.join(SCREENSHOT_DIR, `iter3-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: true });
  log(`Screenshot saved: ${filepath}`);
  return filepath;
}

async function checkMessagesViaAPI() {
  const data = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=100`);
  const messages = data.messages || data || [];
  const senders = new Set();
  const templatePatterns = [];

  for (const msg of messages) {
    if (msg.sender_name) senders.add(msg.sender_name);
    if (msg.content && msg.content.includes('@{crew_')) {
      templatePatterns.push({ sender: msg.sender_name, content: msg.content.substring(0, 100) });
    }
  }

  return { messages, senders: [...senders], templatePatterns, count: messages.length };
}

async function getStageInfo() {
  return await apiGet(`/api/projects/${PROJECT_ID}/stage`);
}

async function checkBackendLogs() {
  // Check recent messages to infer agent activity
  const data = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=20`);
  const messages = data.messages || data || [];
  return messages.slice(-10).map(m => ({
    sender: m.sender_name,
    role: m.sender_role,
    preview: (m.content || '').substring(0, 80)
  }));
}

(async () => {
  log('=== Iteration 3 E2E Test: Supervisor Full DT Journey ===');
  log(`Project ID: ${PROJECT_ID}`);

  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: SCREENSHOT_DIR }
  });

  const page = await context.newPage();

  // Capture console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // =========================================================
    // STEP 1: LOGIN
    // =========================================================
    log('--- STEP 1: Login ---');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, '01-login-page');

    await page.fill('input[type="email"]', 'teacher@test.com');
    await page.fill('input[type="password"]', 'teacher123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects**', { timeout: 15000 });
    log('Login successful');
    await takeScreenshot(page, '02-projects-page');

    // =========================================================
    // STEP 2: Navigate to Project Lobby then Workspace
    // =========================================================
    log('--- STEP 2: Navigate to Project ---');

    // Navigate to the project lobby first
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    await takeScreenshot(page, '03-project-lobby');

    // Navigate to workspace
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`);
    await page.waitForLoadState('networkidle');
    await sleep(3000);
    await takeScreenshot(page, '04-workspace-initial');

    // =========================================================
    // STEP 3: Join as Supervisor
    // =========================================================
    log('--- STEP 3: Join as Supervisor ---');
    const joinButtons = page.locator('button:has-text("入座"), button:has-text("Join"), button:has-text("加入")');
    const joinCount = await joinButtons.count();
    log(`Found ${joinCount} join buttons`);

    if (joinCount > 0) {
      await joinButtons.first().click();
      log('Clicked first join button (supervisor seat)');
      await sleep(2000);
      await takeScreenshot(page, '05-after-join');
    } else {
      log('No join buttons found - may already be joined or UI differs');
      await takeScreenshot(page, '05-no-join-buttons');
    }

    // =========================================================
    // STEP 4: DISCOVER PHASE - Wait and monitor
    // =========================================================
    log('--- STEP 4: DISCOVER PHASE ---');
    const discoverStart = Date.now();

    // Check for supervisor speaking within 10s
    log('Waiting 10s to check if supervisor speaks first...');
    await sleep(10000);

    let msgCheck1 = await checkMessagesViaAPI();
    log(`Messages at 10s: ${msgCheck1.count}, senders: ${msgCheck1.senders.join(', ')}`);

    const supervisorSpoke = msgCheck1.senders.some(s => s.includes('引導者') || s.includes('supervisor') || s.includes('Supervisor'));
    if (!supervisorSpoke && msgCheck1.count === 0) {
      reportBug('HIGH', 'No supervisor message within 10s of project start', {
        senders: msgCheck1.senders,
        messageCount: msgCheck1.count
      });
    } else if (supervisorSpoke) {
      log('PASS: Supervisor spoke within 10s');
      report.phases.discover = report.phases.discover || {};
      report.phases.discover.supervisorFirst = true;
    }

    await takeScreenshot(page, '05-discover-10s');

    // Wait until 30s mark
    log('Waiting until 30s mark...');
    await sleep(20000);
    await takeScreenshot(page, '06-discover-30s');

    let msgCheck2 = await checkMessagesViaAPI();
    log(`Messages at 30s: ${msgCheck2.count}, senders: ${msgCheck2.senders.join(', ')}`);

    // Wait until 60s mark - check for crew agents
    log('Waiting until 60s mark to check crew agent responses...');
    await sleep(30000);

    let msgCheck3 = await checkMessagesViaAPI();
    log(`Messages at 60s: ${msgCheck3.count}, senders: ${msgCheck3.senders.join(', ')}`);

    const crewAgents = ['同理心', '結構化', '創意', '可行性'];
    const crewResponded = crewAgents.filter(agent =>
      msgCheck3.senders.some(s => s.includes(agent))
    );

    log(`Crew agents responded: ${crewResponded.join(', ')} (expected: ${crewAgents.join(', ')})`);

    if (crewResponded.length === 0) {
      reportBug('CRITICAL', 'No crew agents responded within 60s - #1 regression bug', {
        senders: msgCheck3.senders,
        messageCount: msgCheck3.count
      });
    } else if (crewResponded.length < 4) {
      reportBug('MEDIUM', `Only ${crewResponded.length}/4 crew agents responded within 60s`, {
        responded: crewResponded,
        missing: crewAgents.filter(a => !crewResponded.includes(a))
      });
    } else {
      log('PASS: All 4 crew agents responded within 60s');
      report.phases.discover = report.phases.discover || {};
      report.phases.discover.crewResponse = true;
    }

    // Wait until 90s mark
    log('Waiting until 90s mark...');
    await sleep(30000);

    let msgCheck4 = await checkMessagesViaAPI();
    log(`Messages at 90s: ${msgCheck4.count}, senders: ${msgCheck4.senders.join(', ')}`);
    await takeScreenshot(page, '07-discover-90s');

    // Check for template interpolation bugs
    if (msgCheck4.templatePatterns.length > 0) {
      reportBug('HIGH', 'Template @{crew_N} patterns not interpolated in messages', {
        patterns: msgCheck4.templatePatterns
      });
    } else {
      log('PASS: No @{crew_N} template patterns in messages');
    }

    // Check for sticky notes on canvas
    const canvasElement = page.locator('[data-testid="canvas"], .tl-canvas, canvas').first();
    const canvasVisible = await canvasElement.isVisible({ timeout: 3000 }).catch(() => false);
    if (canvasVisible) {
      log('PASS: Canvas is visible');
    } else {
      reportBug('LOW', 'Canvas element not found via standard selectors');
    }

    // Log recent agent activity from API
    const recentLogs = await checkBackendLogs();
    log('Recent agent messages:');
    recentLogs.forEach(m => log(`  [${m.role || 'unknown'}] ${m.sender}: ${m.preview}`));

    report.phases.discover = {
      ...report.phases.discover,
      duration: Date.now() - discoverStart,
      finalMessageCount: msgCheck4.count,
      uniqueSenders: msgCheck4.senders,
      templatePatternsBugs: msgCheck4.templatePatterns.length
    };

    // =========================================================
    // STEP 5: ADVANCE TO DEFINE PHASE
    // =========================================================
    log('--- STEP 5: ADVANCE TO DEFINE PHASE ---');

    const stageBeforeAdvance = await getStageInfo();
    log(`Current stage before advance: ${JSON.stringify(stageBeforeAdvance)}`);

    // Look for advance button
    const advanceButton = page.locator(
      'button:has-text("進入下一階段"), button:has-text("Advance"), button:has-text("Define"), button:has-text("定義"), [data-testid="advance-stage"]'
    ).first();

    const advanceBtnVisible = await advanceButton.isVisible({ timeout: 5000 }).catch(() => false);

    if (advanceBtnVisible) {
      log('Clicking advance to Define button...');
      await advanceButton.click();
      await sleep(1000);

      // Handle confirmation dialog if present
      const confirmBtn = page.locator('button:has-text("確認"), button:has-text("Confirm"), button:has-text("是")').first();
      const confirmVisible = await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false);
      if (confirmVisible) {
        await confirmBtn.click();
        log('Confirmed advance');
      }

      await sleep(3000);
    } else {
      log('Advance button not visible - trying API advance');
      // Try API-based stage advance
      const advanceRes = await fetch(`${API_URL}/api/projects/${PROJECT_ID}/stage/advance`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }
      }).catch(() => null);

      if (advanceRes) {
        const advanceData = await advanceRes.json().catch(() => ({}));
        log(`API advance result: ${JSON.stringify(advanceData)}`);
      }
      await sleep(3000);
    }

    await takeScreenshot(page, '08-define-phase-start');

    // Check micro_phase via API
    const stageAfterAdvance = await getStageInfo();
    log(`Stage after advance to Define: ${JSON.stringify(stageAfterAdvance)}`);

    const currentStage = stageAfterAdvance.current_stage || stageAfterAdvance.stage || '';
    const microPhase = stageAfterAdvance.micro_phase || stageAfterAdvance.current_micro_phase || '';

    if (currentStage === 'define' || currentStage.includes('define')) {
      log('PASS: Successfully advanced to Define phase');
    } else {
      reportBug('HIGH', 'Failed to advance to Define phase', {
        currentStage,
        microPhase,
        stageData: stageAfterAdvance
      });
    }

    if (microPhase && !microPhase.startsWith('2.')) {
      reportBug('MEDIUM', `micro_phase should start with "2." after Define advance, got: ${microPhase}`, {
        microPhase
      });
    } else if (microPhase.startsWith('2.')) {
      log(`PASS: micro_phase correctly starts with "2." (${microPhase})`);
    }

    // Wait 60s in Define phase
    log('Waiting 60s in Define phase...');
    await sleep(30000);
    await takeScreenshot(page, '09-define-30s');
    await sleep(30000);
    await takeScreenshot(page, '10-define-60s');

    const defineMessages = await checkMessagesViaAPI();
    log(`Define phase messages: ${defineMessages.count}, senders: ${defineMessages.senders.join(', ')}`);

    report.phases.define = {
      stage: currentStage,
      microPhase,
      messageCount: defineMessages.count,
      uniqueSenders: defineMessages.senders
    };

    // =========================================================
    // STEP 6: ADVANCE TO DEVELOP PHASE
    // =========================================================
    log('--- STEP 6: ADVANCE TO DEVELOP PHASE ---');

    const advanceButton2 = page.locator(
      'button:has-text("進入下一階段"), button:has-text("Develop"), button:has-text("發展"), [data-testid="advance-stage"]'
    ).first();

    const advanceBtn2Visible = await advanceButton2.isVisible({ timeout: 5000 }).catch(() => false);

    if (advanceBtn2Visible) {
      await advanceButton2.click();
      await sleep(1000);
      const confirmBtn2 = page.locator('button:has-text("確認"), button:has-text("Confirm"), button:has-text("是")').first();
      const confirm2Visible = await confirmBtn2.isVisible({ timeout: 3000 }).catch(() => false);
      if (confirm2Visible) await confirmBtn2.click();
      await sleep(3000);
    } else {
      log('Advance button not visible for Develop - trying API');
      await fetch(`${API_URL}/api/projects/${PROJECT_ID}/stage/advance`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }
      }).catch(() => null);
      await sleep(3000);
    }

    await takeScreenshot(page, '11-develop-phase-start');

    const developStage = await getStageInfo();
    log(`Stage after advance to Develop: ${JSON.stringify(developStage)}`);

    const developStageName = developStage.current_stage || developStage.stage || '';
    const developMicroPhase = developStage.micro_phase || developStage.current_micro_phase || '';

    if (developStageName === 'develop' || developStageName.includes('develop')) {
      log('PASS: Successfully advanced to Develop phase');
    } else {
      reportBug('HIGH', 'Failed to advance to Develop phase', {
        currentStage: developStageName,
        stageData: developStage
      });
    }

    if (developMicroPhase && !developMicroPhase.startsWith('3.')) {
      reportBug('MEDIUM', `micro_phase should start with "3." after Develop advance, got: ${developMicroPhase}`);
    } else if (developMicroPhase.startsWith('3.')) {
      log(`PASS: micro_phase correctly starts with "3." (${developMicroPhase})`);
    }

    log('Waiting 60s in Develop phase...');
    await sleep(30000);
    await takeScreenshot(page, '12-develop-30s');
    await sleep(30000);
    await takeScreenshot(page, '13-develop-60s');

    const developMessages = await checkMessagesViaAPI();

    report.phases.develop = {
      stage: developStageName,
      microPhase: developMicroPhase,
      messageCount: developMessages.count,
      uniqueSenders: developMessages.senders
    };

    // =========================================================
    // STEP 7: ADVANCE TO DELIVER PHASE
    // =========================================================
    log('--- STEP 7: ADVANCE TO DELIVER PHASE ---');

    const advanceButton3 = page.locator(
      'button:has-text("進入下一階段"), button:has-text("Deliver"), button:has-text("交付"), [data-testid="advance-stage"]'
    ).first();

    const advanceBtn3Visible = await advanceButton3.isVisible({ timeout: 5000 }).catch(() => false);

    if (advanceBtn3Visible) {
      await advanceButton3.click();
      await sleep(1000);
      const confirmBtn3 = page.locator('button:has-text("確認"), button:has-text("Confirm"), button:has-text("是")').first();
      const confirm3Visible = await confirmBtn3.isVisible({ timeout: 3000 }).catch(() => false);
      if (confirm3Visible) await confirmBtn3.click();
      await sleep(3000);
    } else {
      log('Advance button not visible for Deliver - trying API');
      await fetch(`${API_URL}/api/projects/${PROJECT_ID}/stage/advance`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }
      }).catch(() => null);
      await sleep(3000);
    }

    await takeScreenshot(page, '14-deliver-phase-start');

    const deliverStage = await getStageInfo();
    log(`Stage after advance to Deliver: ${JSON.stringify(deliverStage)}`);

    const deliverStageName = deliverStage.current_stage || deliverStage.stage || '';
    const deliverMicroPhase = deliverStage.micro_phase || deliverStage.current_micro_phase || '';

    if (deliverStageName === 'deliver' || deliverStageName.includes('deliver')) {
      log('PASS: Successfully advanced to Deliver phase');
    } else {
      reportBug('HIGH', 'Failed to advance to Deliver phase', {
        currentStage: deliverStageName,
        stageData: deliverStage
      });
    }

    if (deliverMicroPhase && !deliverMicroPhase.startsWith('4.')) {
      reportBug('MEDIUM', `micro_phase should start with "4." after Deliver advance, got: ${deliverMicroPhase}`);
    } else if (deliverMicroPhase.startsWith('4.')) {
      log(`PASS: micro_phase correctly starts with "4." (${deliverMicroPhase})`);
    }

    // Check that no advance button exists in Deliver phase
    await sleep(2000);
    const noAdvanceButton = page.locator(
      'button:has-text("進入下一階段"), button:has-text("Advance"), [data-testid="advance-stage"]'
    ).first();
    const advanceStillVisible = await noAdvanceButton.isVisible({ timeout: 2000 }).catch(() => false);
    if (advanceStillVisible) {
      reportBug('MEDIUM', 'Advance button still visible in final Deliver phase - should not exist');
    } else {
      log('PASS: No advance button in Deliver phase');
    }

    log('Waiting 30s in Deliver phase...');
    await sleep(30000);
    await takeScreenshot(page, '15-deliver-30s');

    const deliverMessages = await checkMessagesViaAPI();

    report.phases.deliver = {
      stage: deliverStageName,
      microPhase: deliverMicroPhase,
      messageCount: deliverMessages.count,
      uniqueSenders: deliverMessages.senders
    };

    // =========================================================
    // STEP 8: FINAL API VERIFICATION
    // =========================================================
    log('--- STEP 8: FINAL API VERIFICATION ---');

    const finalMessages = await checkMessagesViaAPI();
    const uniqueSenderCount = finalMessages.senders.length;

    log(`Total messages: ${finalMessages.count}`);
    log(`Unique senders: ${uniqueSenderCount} — ${finalMessages.senders.join(', ')}`);

    if (uniqueSenderCount < 3) {
      reportBug('HIGH', `Only ${uniqueSenderCount} unique AI agent senders — GOAL is ≥3`, {
        senders: finalMessages.senders
      });
    } else {
      log(`PASS: ${uniqueSenderCount} unique senders (goal: ≥3)`);
    }

    if (finalMessages.templatePatterns.length > 0) {
      reportBug('HIGH', `${finalMessages.templatePatterns.length} @{crew_N} template patterns still present`, {
        examples: finalMessages.templatePatterns.slice(0, 3)
      });
    } else {
      log('PASS: No @{crew_N} template patterns in final messages');
    }

    // Check project history
    const history = await apiGet(`/api/projects/${PROJECT_ID}/history`).catch(() => null);
    if (history) {
      log(`Project history: ${JSON.stringify(history).substring(0, 200)}`);
    }

    // Console errors summary
    if (consoleErrors.length > 0) {
      log(`Console errors detected: ${consoleErrors.length}`);
      consoleErrors.slice(0, 5).forEach(e => log(`  ERROR: ${e}`));
      reportBug('LOW', `${consoleErrors.length} browser console errors`, { errors: consoleErrors.slice(0, 5) });
    }

    report.summary = {
      totalMessages: finalMessages.count,
      uniqueSenders: finalMessages.senders,
      uniqueSenderCount,
      templatePatternBugs: finalMessages.templatePatterns.length,
      totalBugs: report.bugs.length,
      bugsBySeverity: {
        CRITICAL: report.bugs.filter(b => b.severity === 'CRITICAL').length,
        HIGH: report.bugs.filter(b => b.severity === 'HIGH').length,
        MEDIUM: report.bugs.filter(b => b.severity === 'MEDIUM').length,
        LOW: report.bugs.filter(b => b.severity === 'LOW').length
      },
      consoleErrors: consoleErrors.length
    };

    await takeScreenshot(page, '16-final-state');

  } catch (err) {
    log(`FATAL ERROR: ${err.message}`);
    log(err.stack);
    reportBug('CRITICAL', `Test execution error: ${err.message}`, { stack: err.stack });
    await takeScreenshot(page, '99-fatal-error').catch(() => {});
  } finally {
    // Save report
    const reportPath = path.join(__dirname, 'iter3-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    log(`Report saved: ${reportPath}`);

    // Print summary
    log('');
    log('=== TEST SUMMARY ===');
    log(`Total messages: ${report.summary.totalMessages || 0}`);
    log(`Unique senders: ${(report.summary.uniqueSenders || []).join(', ')}`);
    log(`Template pattern bugs: ${report.summary.templatePatternBugs || 0}`);
    log(`Bugs found: ${report.bugs.length}`);
    report.bugs.forEach((b, i) => log(`  ${i+1}. [${b.severity}] ${b.description}`));

    await context.close();
    await browser.close();
  }
})();
