/**
 * Iteration 3 E2E Test Run 2: Supervisor Full DT Journey
 * Uses fresh project: d53d724f-60ff-4b18-b40a-9fbc7cff32c5
 * Key changes from Run1:
 * - Join as supervisor via API before navigating to workspace
 * - Advance stage via API with correct endpoint and from/to params
 * - Proper route URLs (/projects/:id/workspace)
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const http = require('http');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const TOKEN = '***REMOVED_JWT***';
const PROJECT_ID = 'd53d724f-60ff-4b18-b40a-9fbc7cff32c5';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

const STAGE_ORDER = ['discover', 'define', 'develop', 'deliver'];
const STAGE_MICRO_PREFIX = { discover: '1.', define: '2.', develop: '3.', deliver: '4.' };

const report = {
  projectId: PROJECT_ID,
  timestamp: new Date().toISOString(),
  phases: {},
  bugs: [],
  summary: {},
  notes: []
};

function log(msg) {
  const ts = new Date().toISOString().substring(11, 19);
  console.log(`[${ts}] ${msg}`);
}

function note(msg) {
  report.notes.push({ time: new Date().toISOString(), msg });
  log(`NOTE: ${msg}`);
}

function reportBug(severity, description, details = {}) {
  const bug = { severity, description, details, time: new Date().toISOString() };
  report.bugs.push(bug);
  log(`BUG [${severity}] ${description}`);
}

function reportPass(check, detail = '') {
  log(`PASS: ${check}${detail ? ' — ' + detail : ''}`);
}

async function apiCall(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(API_URL + path);
    const bodyStr = body ? JSON.stringify(body) : null;
    const options = {
      hostname: url.hostname,
      port: parseInt(url.port) || 8000,
      path: url.pathname + url.search,
      method,
      headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json',
        ...(bodyStr ? { 'Content-Length': Buffer.byteLength(bodyStr) } : {})
      }
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on('error', reject);
    if (bodyStr) req.write(bodyStr);
    req.end();
  });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function takeScreenshot(page, name) {
  const filepath = path.join(SCREENSHOT_DIR, `iter3-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: true });
  log(`Screenshot: iter3-${name}.png`);
  return filepath;
}

async function getMessages(limit = 100) {
  const res = await apiCall('GET', `/api/projects/${PROJECT_ID}/messages?limit=${limit}`);
  const messages = res.body.messages || res.body || [];
  const senders = new Set();
  const templatePatterns = [];
  const rawTemplates = [];

  for (const msg of messages) {
    if (msg.sender_name) senders.add(msg.sender_name);
    if (msg.content && msg.content.match(/@\{crew_\d+\}/)) {
      templatePatterns.push({ sender: msg.sender_name, content: msg.content.substring(0, 100) });
    }
    // Check for unresolved "Crew_N" references (plain text not in @{})
    if (msg.content && msg.content.match(/\bCrew_\d+\b/)) {
      rawTemplates.push({ sender: msg.sender_name, content: msg.content.substring(0, 100) });
    }
  }

  return {
    messages,
    senders: [...senders],
    templatePatterns,
    rawTemplates,
    count: messages.length
  };
}

async function getStageInfo() {
  const res = await apiCall('GET', `/api/projects/${PROJECT_ID}/stage`);
  return res.body;
}

async function advanceStageAPI(fromStage, toStage) {
  const res = await apiCall('POST', `/api/projects/${PROJECT_ID}/advance-stage`, {
    from: fromStage,
    to: toStage
  });
  return res;
}

(async () => {
  log('=== Iteration 3 E2E Test Run 2: Full DT Journey ===');
  log(`Project ID: ${PROJECT_ID}`);
  log(`Screenshot dir: ${SCREENSHOT_DIR}`);

  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });

  const page = await context.newPage();

  const consoleErrors = [];
  const consoleWarnings = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') consoleWarnings.push(msg.text());
  });

  try {
    // =========================================================
    // STEP 1: Join as supervisor via API (before browser login)
    // =========================================================
    log('--- STEP 1: Join project as supervisor via API ---');
    const joinRes = await apiCall('POST', `/api/projects/${PROJECT_ID}/join`, { seat_role: 'supervisor' });
    log(`Join API response: ${joinRes.status} — ${JSON.stringify(joinRes.body)}`);

    if (joinRes.status === 200) {
      reportPass('Human supervisor joined project via API');
    } else {
      reportBug('HIGH', 'Failed to join as supervisor via API', { status: joinRes.status, body: joinRes.body });
    }

    // =========================================================
    // STEP 2: Login in browser
    // =========================================================
    log('--- STEP 2: Browser login ---');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, 'r2-01-login');

    await page.fill('input[type="email"]', 'teacher@test.com');
    await page.fill('input[type="password"]', 'teacher123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects**', { timeout: 15000 });
    reportPass('Browser login successful');
    await takeScreenshot(page, 'r2-02-projects-list');

    // =========================================================
    // STEP 3: Navigate directly to workspace
    // =========================================================
    log('--- STEP 3: Navigate to workspace ---');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`);
    await page.waitForLoadState('networkidle');
    await sleep(3000);
    await takeScreenshot(page, 'r2-03-workspace-loaded');

    // Verify we're not redirected back to lobby (which happens if not seated)
    const currentURL = page.url();
    if (currentURL.includes('/workspace')) {
      reportPass('Stayed in workspace (supervisor seat confirmed)', currentURL);
    } else {
      reportBug('HIGH', 'Redirected away from workspace - supervisor seat not recognized by frontend', {
        url: currentURL
      });
    }

    // Check for seat indicator in UI
    const supervisorIndicator = page.locator('text=引導者, text=Supervisor, [data-role="supervisor"]').first();
    const seenSupervisor = await supervisorIndicator.isVisible({ timeout: 3000 }).catch(() => false);
    if (seenSupervisor) {
      reportPass('Supervisor role indicator visible in workspace');
    } else {
      note('Supervisor role indicator not found with tested selectors (may use different UI element)');
    }

    // =========================================================
    // STEP 4: DISCOVER PHASE
    // =========================================================
    log('--- STEP 4: DISCOVER PHASE (monitoring 90s) ---');
    const discoverStart = Date.now();
    report.phases.discover = { start: new Date().toISOString() };

    // Check messages at 10s
    log('Checking supervisor first-speak at 10s...');
    await sleep(10000);

    let msgs10s = await getMessages(10);
    log(`[10s] Messages: ${msgs10s.count}, senders: ${msgs10s.senders.join(', ')}`);

    const supervisorSpoke = msgs10s.senders.some(s => s.includes('引導者') || s.includes('Supervisor'));
    if (supervisorSpoke) {
      reportPass('Supervisor sent first message within 10s');
      report.phases.discover.supervisorFirst = true;
    } else if (msgs10s.count === 0) {
      reportBug('HIGH', 'No messages at all within 10s — supervisor did not trigger discussion', {
        senders: msgs10s.senders
      });
    } else {
      reportBug('MEDIUM', 'Supervisor did not speak first within 10s', {
        senders: msgs10s.senders,
        count: msgs10s.count
      });
    }

    await takeScreenshot(page, 'r2-04-discover-10s');

    // Check for raw template leaks (Crew_N not interpolated)
    if (msgs10s.rawTemplates.length > 0) {
      reportBug('HIGH', 'Unresolved "Crew_N" template references in messages', {
        examples: msgs10s.rawTemplates
      });
    }
    if (msgs10s.templatePatterns.length > 0) {
      reportBug('HIGH', '@{crew_N} template patterns not interpolated', {
        examples: msgs10s.templatePatterns
      });
    }

    // Wait until 30s
    await sleep(20000);
    let msgs30s = await getMessages(20);
    log(`[30s] Messages: ${msgs30s.count}, senders: ${msgs30s.senders.join(', ')}`);
    await takeScreenshot(page, 'r2-05-discover-30s');

    // Wait until 60s — check crew agents
    await sleep(30000);
    let msgs60s = await getMessages(50);
    log(`[60s] Messages: ${msgs60s.count}, senders: ${msgs60s.senders.join(', ')}`);

    const crewAgents = ['同理心', '結構化', '創意', '可行性'];
    const crewResponded60s = crewAgents.filter(agent =>
      msgs60s.senders.some(s => s.includes(agent))
    );

    if (crewResponded60s.length === 4) {
      reportPass('All 4 crew agents responded within 60s');
      report.phases.discover.allCrewResponded = true;
    } else if (crewResponded60s.length > 0) {
      reportBug('MEDIUM', `Only ${crewResponded60s.length}/4 crew agents responded by 60s`, {
        responded: crewResponded60s,
        missing: crewAgents.filter(a => !crewResponded60s.includes(a))
      });
    } else {
      reportBug('CRITICAL', 'Zero crew agents responded within 60s — #1 fix regression', {
        allSenders: msgs60s.senders
      });
    }

    // Wait until 90s
    await sleep(30000);
    let msgs90s = await getMessages(100);
    log(`[90s] Messages: ${msgs90s.count}, senders: ${msgs90s.senders.join(', ')}`);
    await takeScreenshot(page, 'r2-06-discover-90s');

    // Final crew check at 90s (may_pass for slow agents)
    const crewResponded90s = crewAgents.filter(agent =>
      msgs90s.senders.some(s => s.includes(agent))
    );
    log(`Crew responded by 90s: ${crewResponded90s.join(', ')}`);

    const finalTemplateCheck = msgs90s.templatePatterns.length + msgs90s.rawTemplates.length;
    if (finalTemplateCheck === 0) {
      reportPass('No template interpolation bugs in discover messages');
    } else {
      reportBug('HIGH', `Template bugs still present at 90s: ${finalTemplateCheck} instances`, {
        atTemplates: msgs90s.templatePatterns,
        rawTemplates: msgs90s.rawTemplates
      });
    }

    // Check canvas (flexible - may use tldraw custom element)
    const canvasSelectors = [
      '[data-testid="canvas"]',
      '.tl-canvas',
      'canvas',
      '.tldraw',
      '[class*="tldraw"]'
    ];
    let canvasFound = false;
    for (const sel of canvasSelectors) {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 1000 }).catch(() => false)) {
        canvasFound = true;
        reportPass(`Canvas found via selector: ${sel}`);
        break;
      }
    }
    if (!canvasFound) {
      note('Canvas not found via standard selectors — tldraw may use shadow DOM or custom elements');
    }

    report.phases.discover = {
      ...report.phases.discover,
      end: new Date().toISOString(),
      duration: Date.now() - discoverStart,
      finalMessageCount: msgs90s.count,
      uniqueSenders: msgs90s.senders,
      crewResponded: crewResponded90s
    };

    // =========================================================
    // STEP 5: ADVANCE TO DEFINE
    // =========================================================
    log('--- STEP 5: ADVANCE TO DEFINE ---');

    // Check if UI advance button is now enabled for supervisor
    const advanceSelector = 'button:has-text("進入下一階段")';
    const advanceBtn = page.locator(advanceSelector).first();
    const advanceBtnEnabled = await advanceBtn.isEnabled({ timeout: 5000 }).catch(() => false);
    log(`Advance button enabled: ${advanceBtnEnabled}`);

    if (advanceBtnEnabled) {
      reportPass('Advance button is enabled for supervisor');
      await advanceBtn.click();
      await sleep(1000);
      // Handle confirm modal
      const confirmBtn = page.locator('button:has-text("確認"), button:has-text("Confirm"), button:has-text("確定"), button:has-text("是的")').first();
      if (await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await confirmBtn.click();
        reportPass('Confirm modal clicked');
      }
      await sleep(3000);
    } else {
      note('Advance button disabled/not found in UI — using API');
      // Get current stage to ensure we have right "from"
      const stageInfo = await getStageInfo();
      const currentStage = stageInfo.current_stage;
      const toStage = STAGE_ORDER[STAGE_ORDER.indexOf(currentStage) + 1];
      if (toStage) {
        const advRes = await advanceStageAPI(currentStage, toStage);
        log(`API advance-stage ${currentStage}→${toStage}: status ${advRes.status}`);
        if (advRes.status === 200 || advRes.status === 204) {
          reportPass(`Advanced stage via API: ${currentStage} → ${toStage}`);
        } else {
          reportBug('HIGH', `API stage advance failed: ${JSON.stringify(advRes.body)}`, {
            from: currentStage, to: toStage, status: advRes.status
          });
        }
      }
      await sleep(3000);
    }

    await takeScreenshot(page, 'r2-07-define-start');

    const defineStageInfo = await getStageInfo();
    log(`Define stage API: ${JSON.stringify(defineStageInfo)}`);

    if (defineStageInfo.current_stage === 'define') {
      reportPass('Successfully advanced to Define phase');
    } else {
      reportBug('HIGH', `Failed to reach Define phase, current: ${defineStageInfo.current_stage}`);
    }

    const defineMicroPhase = defineStageInfo.current_micro_phase || '';
    if (defineMicroPhase.startsWith('2.')) {
      reportPass(`micro_phase correctly starts with "2." (${defineMicroPhase})`);
    } else if (defineMicroPhase) {
      reportBug('MEDIUM', `micro_phase after Define advance should start "2.", got: "${defineMicroPhase}"`);
    }

    // Wait and observe Define phase
    log('Waiting 60s in Define phase...');
    await sleep(30000);
    await takeScreenshot(page, 'r2-08-define-30s');
    await sleep(30000);

    let defineMsgs = await getMessages(100);
    log(`Define messages: ${defineMsgs.count}, senders: ${defineMsgs.senders.join(', ')}`);
    await takeScreenshot(page, 'r2-09-define-60s');

    report.phases.define = {
      stage: defineStageInfo.current_stage,
      microPhase: defineMicroPhase,
      messageCount: defineMsgs.count,
      uniqueSenders: defineMsgs.senders
    };

    // =========================================================
    // STEP 6: ADVANCE TO DEVELOP
    // =========================================================
    log('--- STEP 6: ADVANCE TO DEVELOP ---');

    const advanceBtn2 = page.locator(advanceSelector).first();
    const advanceBtn2Enabled = await advanceBtn2.isEnabled({ timeout: 3000 }).catch(() => false);

    if (advanceBtn2Enabled) {
      await advanceBtn2.click();
      await sleep(1000);
      const confirmBtn2 = page.locator('button:has-text("確認"), button:has-text("確定"), button:has-text("是的")').first();
      if (await confirmBtn2.isVisible({ timeout: 3000 }).catch(() => false)) await confirmBtn2.click();
      await sleep(3000);
    } else {
      const stageInfo2 = await getStageInfo();
      const cs2 = stageInfo2.current_stage;
      const ts2 = STAGE_ORDER[STAGE_ORDER.indexOf(cs2) + 1];
      if (ts2) {
        const advRes2 = await advanceStageAPI(cs2, ts2);
        log(`API advance-stage ${cs2}→${ts2}: status ${advRes2.status}`);
        if (advRes2.status !== 200 && advRes2.status !== 204) {
          reportBug('HIGH', `API stage advance to Develop failed`, { status: advRes2.status, body: advRes2.body });
        }
      }
      await sleep(3000);
    }

    await takeScreenshot(page, 'r2-10-develop-start');

    const developInfo = await getStageInfo();
    log(`Develop stage API: ${JSON.stringify(developInfo)}`);

    if (developInfo.current_stage === 'develop') {
      reportPass('Successfully advanced to Develop phase');
    } else {
      reportBug('HIGH', `Failed to reach Develop phase, current: ${developInfo.current_stage}`);
    }

    const developMicro = developInfo.current_micro_phase || '';
    if (developMicro.startsWith('3.')) {
      reportPass(`micro_phase correctly starts with "3." (${developMicro})`);
    } else if (developMicro) {
      reportBug('MEDIUM', `micro_phase after Develop should start "3.", got: "${developMicro}"`);
    }

    log('Waiting 60s in Develop phase...');
    await sleep(30000);
    await takeScreenshot(page, 'r2-11-develop-30s');
    await sleep(30000);

    let developMsgs = await getMessages(100);
    log(`Develop messages: ${developMsgs.count}, senders: ${developMsgs.senders.join(', ')}`);
    await takeScreenshot(page, 'r2-12-develop-60s');

    report.phases.develop = {
      stage: developInfo.current_stage,
      microPhase: developMicro,
      messageCount: developMsgs.count,
      uniqueSenders: developMsgs.senders
    };

    // =========================================================
    // STEP 7: ADVANCE TO DELIVER
    // =========================================================
    log('--- STEP 7: ADVANCE TO DELIVER ---');

    const advanceBtn3 = page.locator(advanceSelector).first();
    const advanceBtn3Enabled = await advanceBtn3.isEnabled({ timeout: 3000 }).catch(() => false);

    if (advanceBtn3Enabled) {
      await advanceBtn3.click();
      await sleep(1000);
      const confirmBtn3 = page.locator('button:has-text("確認"), button:has-text("確定"), button:has-text("是的")').first();
      if (await confirmBtn3.isVisible({ timeout: 3000 }).catch(() => false)) await confirmBtn3.click();
      await sleep(3000);
    } else {
      const stageInfo3 = await getStageInfo();
      const cs3 = stageInfo3.current_stage;
      const ts3 = STAGE_ORDER[STAGE_ORDER.indexOf(cs3) + 1];
      if (ts3) {
        const advRes3 = await advanceStageAPI(cs3, ts3);
        log(`API advance-stage ${cs3}→${ts3}: status ${advRes3.status}`);
        if (advRes3.status !== 200 && advRes3.status !== 204) {
          reportBug('HIGH', `API stage advance to Deliver failed`, { status: advRes3.status, body: advRes3.body });
        }
      }
      await sleep(3000);
    }

    await takeScreenshot(page, 'r2-13-deliver-start');

    const deliverInfo = await getStageInfo();
    log(`Deliver stage API: ${JSON.stringify(deliverInfo)}`);

    if (deliverInfo.current_stage === 'deliver') {
      reportPass('Successfully advanced to Deliver phase');
    } else {
      reportBug('HIGH', `Failed to reach Deliver phase, current: ${deliverInfo.current_stage}`);
    }

    const deliverMicro = deliverInfo.current_micro_phase || '';
    if (deliverMicro.startsWith('4.')) {
      reportPass(`micro_phase correctly starts with "4." (${deliverMicro})`);
    } else if (deliverMicro) {
      reportBug('MEDIUM', `micro_phase after Deliver should start "4.", got: "${deliverMicro}"`);
    }

    // Verify NO advance button in Deliver (final phase)
    await sleep(2000);
    const finalAdvanceBtn = page.locator(advanceSelector).first();
    const finalAdvanceVisible = await finalAdvanceBtn.isVisible({ timeout: 2000 }).catch(() => false);
    if (finalAdvanceVisible) {
      reportBug('MEDIUM', 'Advance button still visible in final Deliver phase');
    } else {
      reportPass('No advance button in Deliver phase (correct — final stage)');
    }

    log('Waiting 30s in Deliver phase...');
    await sleep(30000);

    let deliverMsgs = await getMessages(100);
    log(`Deliver messages: ${deliverMsgs.count}, senders: ${deliverMsgs.senders.join(', ')}`);
    await takeScreenshot(page, 'r2-14-deliver-30s');

    report.phases.deliver = {
      stage: deliverInfo.current_stage,
      microPhase: deliverMicro,
      messageCount: deliverMsgs.count,
      uniqueSenders: deliverMsgs.senders
    };

    // =========================================================
    // STEP 8: FINAL VERIFICATION
    // =========================================================
    log('--- STEP 8: FINAL API VERIFICATION ---');

    const finalMsgs = await getMessages(200);
    const uniqueCount = finalMsgs.senders.length;

    log(`Total messages: ${finalMsgs.count}`);
    log(`Unique senders (${uniqueCount}): ${finalMsgs.senders.join(', ')}`);

    if (uniqueCount >= 3) {
      reportPass(`${uniqueCount} unique AI agent senders (goal: ≥3)`);
    } else {
      reportBug('HIGH', `Only ${uniqueCount} unique senders — goal is ≥3`, {
        senders: finalMsgs.senders
      });
    }

    if (finalMsgs.templatePatterns.length + finalMsgs.rawTemplates.length === 0) {
      reportPass('Zero template interpolation bugs in all messages');
    } else {
      reportBug('HIGH', `Template bugs in final messages: @{} patterns: ${finalMsgs.templatePatterns.length}, Crew_N raw: ${finalMsgs.rawTemplates.length}`);
    }

    // Project history
    const historyRes = await apiCall('GET', `/api/projects/${PROJECT_ID}/history`);
    if (historyRes.status === 200) {
      log(`History: ${JSON.stringify(historyRes.body).substring(0, 200)}`);
    }

    // Console error summary
    if (consoleErrors.length > 0) {
      log(`Browser console errors: ${consoleErrors.length}`);
      consoleErrors.slice(0, 5).forEach(e => log(`  ERR: ${e.substring(0, 120)}`));
      reportBug('LOW', `${consoleErrors.length} browser console errors`, {
        errors: consoleErrors.slice(0, 5)
      });
    } else {
      reportPass('Zero browser console errors');
    }

    await takeScreenshot(page, 'r2-15-final-state');

    report.summary = {
      totalMessages: finalMsgs.count,
      uniqueSenders: finalMsgs.senders,
      uniqueSenderCount: uniqueCount,
      templateBugs: finalMsgs.templatePatterns.length + finalMsgs.rawTemplates.length,
      totalBugsFound: report.bugs.length,
      bugsBySeverity: {
        CRITICAL: report.bugs.filter(b => b.severity === 'CRITICAL').length,
        HIGH: report.bugs.filter(b => b.severity === 'HIGH').length,
        MEDIUM: report.bugs.filter(b => b.severity === 'MEDIUM').length,
        LOW: report.bugs.filter(b => b.severity === 'LOW').length
      }
    };

  } catch (err) {
    log(`FATAL: ${err.message}`);
    reportBug('CRITICAL', `Test execution crashed: ${err.message}`, { stack: err.stack });
    await takeScreenshot(page, 'r2-99-crash').catch(() => {});
  } finally {
    const reportPath = path.join(__dirname, 'iter3-run2-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    log('');
    log('============================');
    log('=   ITERATION 3 REPORT    =');
    log('============================');
    log(`Project: ${PROJECT_ID}`);
    log(`Total messages: ${report.summary.totalMessages || 0}`);
    log(`Unique senders: ${(report.summary.uniqueSenders || []).join(', ')}`);
    log(`Template bugs: ${report.summary.templateBugs || 0}`);
    log('---');
    log(`BUGS (${report.bugs.length} total):`);
    report.bugs.forEach((b, i) => {
      log(`  ${i + 1}. [${b.severity}] ${b.description}`);
    });
    log('---');
    log(`Bug breakdown: ${JSON.stringify(report.summary.bugsBySeverity || {})}`);
    log(`Report: ${reportPath}`);

    await context.close();
    await browser.close();
  }
})();
