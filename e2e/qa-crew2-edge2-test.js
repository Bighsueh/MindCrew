/**
 * QA Test: Crew Role (Test A) + Edge Cases (Test B)
 * Project: MindCrew
 * Date: 2026-03-31
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const CREDS = { email: 'teacher@test.com', password: 'teacher123' };
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

const report = {
  testA: { name: 'Crew Member Role', steps: [], bugs: [], passed: false },
  testB: { name: 'Edge Cases', steps: [], bugs: [], passed: false },
};

function log(test, msg, status = 'info') {
  const entry = { msg, status, ts: new Date().toISOString() };
  report[test].steps.push(entry);
  const icon = status === 'pass' ? 'PASS' : status === 'fail' ? 'FAIL' : status === 'bug' ? 'BUG' : 'INFO';
  console.log(`[${icon}] [${test.toUpperCase()}] ${msg}`);
}

function bug(test, msg) {
  report[test].bugs.push(msg);
  log(test, msg, 'bug');
}

async function getToken() {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(CREDS),
  });
  const data = await res.json();
  if (!data.access_token) throw new Error('Login failed: ' + JSON.stringify(data));
  return data.access_token;
}

async function apiPost(token, path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  return { status: res.status, data: await res.json() };
}

async function apiGet(token, path) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return { status: res.status, data: await res.json() };
}

// ─── TEST A: CREW MEMBER ROLE ───────────────────────────────────────────────

async function runTestA(token, projectId) {
  console.log('\n=== TEST A: CREW MEMBER ROLE ===');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // Step 1: Login
    log('testA', 'Navigating to login page');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-01-login.png` });

    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await emailInput.fill(CREDS.email);
    await passwordInput.fill(CREDS.password);
    await submitBtn.click();
    await page.waitForURL(/\/(projects|lobby|workspace|dashboard)/, { timeout: 10000 }).catch(() => {});
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-02-after-login.png` });
    log('testA', `After login URL: ${page.url()}`, 'pass');

    // Step 2: Navigate to lobby
    log('testA', `Navigating to /projects/${projectId}/lobby`);
    await page.goto(`${BASE_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-03-lobby.png` });
    log('testA', `Lobby URL: ${page.url()}`, 'pass');

    // Step 3: Find all "入座" buttons
    const joinBtns = page.locator('button:has-text("入座")');
    const count = await joinBtns.count();
    log('testA', `Found ${count} "入座" buttons`);

    if (count < 2) {
      bug('testA', `Expected at least 2 "入座" buttons, found ${count}`);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-03b-lobby-btns.png` });
    } else {
      // Click the SECOND button (crew_1, not supervisor)
      log('testA', 'Clicking SECOND "入座" button (crew_1 seat)');
      await joinBtns.nth(1).click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-04-after-join.png` });
      log('testA', `After join URL: ${page.url()}`, 'pass');
    }

    // Step 4: Wait for workspace and check UI elements
    // Wait up to 10s for redirect to workspace
    await page.waitForURL(/workspace/, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-05-workspace.png` });
    log('testA', `Workspace URL: ${page.url()}`);

    // Check canvas visibility
    const canvas = page.locator('canvas, [class*="canvas"], [data-testid*="canvas"], .tl-canvas').first();
    const canvasVisible = await canvas.isVisible().catch(() => false);
    if (canvasVisible) {
      log('testA', 'Canvas is visible', 'pass');
    } else {
      bug('testA', 'Canvas is NOT visible in workspace');
    }

    // Check chat panel
    const chatPanel = page.locator('[class*="chat"], [data-testid*="chat"], textarea, input[placeholder*="訊息"], input[placeholder*="message"]').first();
    const chatVisible = await chatPanel.isVisible().catch(() => false);
    if (chatVisible) {
      log('testA', 'Chat panel is visible', 'pass');
    } else {
      bug('testA', 'Chat panel is NOT visible');
    }

    // Step 5: Try to send a message
    log('testA', 'Attempting to type and send a message');
    const msgText = '購物車的輪子容易卡住';
    const chatInput = page.locator('textarea, input[placeholder*="訊息"], input[placeholder*="message"], input[type="text"]').first();
    const inputVisible = await chatInput.isVisible().catch(() => false);

    if (inputVisible) {
      await chatInput.fill(msgText);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-06-typed-msg.png` });
      await chatInput.press('Enter');
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-07-after-send.png` });
      log('testA', `Message sent: "${msgText}"`, 'pass');
    } else {
      bug('testA', 'Chat input not found/visible — cannot type message');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-06b-no-input.png` });
    }

    // Step 6: Check "推進到" button is NOT visible for crew
    const advanceBtn = page.locator('button:has-text("推進到"), button:has-text("推進"), [data-testid*="advance"]');
    const advanceBtnCount = await advanceBtn.count();
    if (advanceBtnCount === 0) {
      log('testA', '"推進到" button is hidden for crew member (correct)', 'pass');
    } else {
      const isVisible = await advanceBtn.first().isVisible().catch(() => false);
      if (isVisible) {
        bug('testA', `"推進到" button is VISIBLE for crew member — should be hidden! (found ${advanceBtnCount} instances)`);
      } else {
        log('testA', '"推進到" button exists in DOM but is hidden (acceptable)', 'pass');
      }
    }

    // Step 7: Check if AI agents are chatting (look for AI messages)
    await page.waitForTimeout(5000); // Wait for AI agents
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-08-ai-agents.png` });

    const aiMessages = page.locator('[class*="message"], [class*="chat-item"], [class*="msg"]');
    const msgCount = await aiMessages.count();
    if (msgCount > 0) {
      log('testA', `Found ${msgCount} message elements (AI agents active)`, 'pass');
    } else {
      log('testA', `No message elements visible yet (AI may need more time)`, 'info');
    }

    // Check console errors
    if (consoleErrors.length > 0) {
      bug('testA', `Browser console errors: ${consoleErrors.slice(0, 3).join(' | ')}`);
    }

    // Step 8: Validate human message via API
    log('testA', 'Validating human message via API');
    await page.waitForTimeout(2000);
    const messagesResp = await apiGet(token, `/api/projects/${projectId}/messages`);
    if (messagesResp.status === 200) {
      const messages = Array.isArray(messagesResp.data) ? messagesResp.data : (messagesResp.data.messages || []);
      const humanMsg = messages.find(
        (m) => m.role === 'human' || m.sender_type === 'human' || (m.content && m.content.includes(msgText))
      );
      if (humanMsg) {
        log('testA', `Human message found in API: "${humanMsg.content || humanMsg.message}"`, 'pass');
      } else {
        const allContents = messages.slice(-5).map((m) => `[${m.role || m.sender_type}] ${m.content || m.message}`).join(' | ');
        log('testA', `Human message NOT found in last 5 messages. Recent: ${allContents}`, 'info');
        if (inputVisible) {
          bug('testA', `Human message "${msgText}" was typed and sent but not found via API`);
        }
      }
    } else {
      bug('testA', `Messages API returned status ${messagesResp.status}`);
    }

    report.testA.passed = report.testA.bugs.length === 0;
  } catch (err) {
    bug('testA', `Unexpected error: ${err.message}`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/qa-crew2-error-testA.png` });
  } finally {
    await browser.close();
  }
}

// ─── TEST B: EDGE CASES ──────────────────────────────────────────────────────

async function runTestB(token) {
  console.log('\n=== TEST B: EDGE CASES (API only) ===');

  // Step 1: Create project "QA-Edge2"
  log('testB', 'Creating project QA-Edge2');
  const createResp = await apiPost(token, '/api/projects', {
    name: 'QA-Edge2',
    description: 'Edge case testing project',
    ai_contribution: 'high',
  });

  if (createResp.status !== 200 && createResp.status !== 201) {
    bug('testB', `Failed to create project: status=${createResp.status}, body=${JSON.stringify(createResp.data)}`);
    return;
  }

  const projectId = createResp.data.id;
  log('testB', `Created project ID: ${projectId}`, 'pass');
  log('testB', `Initial stage: ${createResp.data.current_stage}`);

  // Step 2: Try SKIP advance (discover → develop — should fail)
  log('testB', 'Testing skip advance: discover → develop (should fail)');
  const skipResp = await apiPost(token, `/api/projects/${projectId}/advance-stage`, {
    from: 'discover',
    to: 'develop',
  });
  if (skipResp.status >= 400) {
    log('testB', `Skip advance correctly rejected: status=${skipResp.status}, reason=${JSON.stringify(skipResp.data)}`, 'pass');
  } else {
    bug('testB', `Skip advance should have FAILED but returned status=${skipResp.status}. Body: ${JSON.stringify(skipResp.data)}`);
  }

  // Step 3: Try BACKWARD advance (discover → discover — should fail)
  log('testB', 'Testing backward advance: discover → discover (should fail)');
  const backResp = await apiPost(token, `/api/projects/${projectId}/advance-stage`, {
    from: 'discover',
    to: 'discover',
  });
  if (backResp.status >= 400) {
    log('testB', `Backward advance correctly rejected: status=${backResp.status}, reason=${JSON.stringify(backResp.data)}`, 'pass');
  } else {
    bug('testB', `Backward advance should have FAILED but returned status=${backResp.status}. Body: ${JSON.stringify(backResp.data)}`);
  }

  // Step 4: Normal advance (discover → define — should work)
  log('testB', 'Testing normal advance: discover → define (should pass)');
  const normalResp = await apiPost(token, `/api/projects/${projectId}/advance-stage`, {
    from: 'discover',
    to: 'define',
  });
  if (normalResp.status === 200 || normalResp.status === 201) {
    log('testB', `Normal advance accepted: status=${normalResp.status}`, 'pass');
  } else {
    bug('testB', `Normal advance FAILED: status=${normalResp.status}. Body: ${JSON.stringify(normalResp.data)}`);
  }

  // Step 5: Verify stage is now "define" and micro_phase is "2.1"
  log('testB', 'Verifying stage after advance');
  await new Promise((r) => setTimeout(r, 1500)); // Brief wait for state propagation
  const stageResp = await apiGet(token, `/api/projects/${projectId}/stage`);
  if (stageResp.status === 200) {
    const stage = stageResp.data;
    const stageName = stage.current_stage || stage.stage;
    const microPhase = stage.micro_phase || stage.current_micro_phase;
    log('testB', `Stage after advance: stage=${stageName}, micro_phase=${microPhase}`);

    if (stageName === 'define') {
      log('testB', 'Stage is correctly "define"', 'pass');
    } else {
      bug('testB', `Expected stage "define" but got "${stageName}"`);
    }

    if (microPhase === '2.1' || microPhase === 2.1 || String(microPhase).startsWith('2')) {
      log('testB', `Micro phase is correctly "${microPhase}"`, 'pass');
    } else {
      bug('testB', `Expected micro_phase "2.1" but got "${microPhase}"`);
    }
  } else {
    bug('testB', `Stage GET failed: status=${stageResp.status}, body=${JSON.stringify(stageResp.data)}`);
  }

  // Also check via project detail
  const projectResp = await apiGet(token, `/api/projects/${projectId}`);
  if (projectResp.status === 200) {
    log('testB', `Project detail stage: ${projectResp.data.current_stage}`, 'info');
  }

  report.testB.passed = report.testB.bugs.length === 0;
}

// ─── MAIN ────────────────────────────────────────────────────────────────────

async function main() {
  if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  console.log('Authenticating...');
  const token = await getToken();
  console.log('Token acquired.');

  // Test A uses the pre-created project
  const PROJECT_A_ID = '9a96ce83-576c-459b-b78d-2b2224c45162';
  await runTestA(token, PROJECT_A_ID);
  await runTestB(token);

  // Write report
  const reportPath = path.join(__dirname, 'qa-crew2-edge2-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

  console.log('\n=== SUMMARY ===');
  console.log(`Test A (Crew Role):  ${report.testA.passed ? 'PASSED' : 'FAILED'} — ${report.testA.bugs.length} bug(s)`);
  console.log(`Test B (Edge Cases): ${report.testB.passed ? 'PASSED' : 'FAILED'} — ${report.testB.bugs.length} bug(s)`);

  if (report.testA.bugs.length > 0) {
    console.log('\nTest A Bugs:');
    report.testA.bugs.forEach((b, i) => console.log(`  ${i + 1}. ${b}`));
  }
  if (report.testB.bugs.length > 0) {
    console.log('\nTest B Bugs:');
    report.testB.bugs.forEach((b, i) => console.log(`  ${i + 1}. ${b}`));
  }

  console.log(`\nReport: ${reportPath}`);
  console.log('Screenshots: e2e/screenshots/qa-crew2-*.png');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
