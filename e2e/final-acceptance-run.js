/**
 * FINAL ACCEPTANCE TEST
 * Tests: Supervisor (4-phase), Observer (no stall), Crew (chat only)
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

// Project IDs from creation
const PROJECTS = {
  supervisor: { id: '4f9236de-d6cc-4fc3-af4e-06401554d199', name: 'Final-Sup-購物車' },
  observer:   { id: '017f55c8-610f-4249-9c8c-bdd6a7fa728c', name: 'Final-Obs-購物車' },
  crew:       { id: '3a5fb59e-6933-41a6-aa83-3992ecacb21b', name: 'Final-Crew-購物車' }
};

let TOKEN = '';
const results = {
  supervisor: {},
  observer: {},
  crew: {},
  checklist: {
    'SUP: ≥3 unique AI senders': null,
    'SUP: Zero template patterns': null,
    'SUP: micro_phase resets correctly (2.1, 3.1, 4.1)': null,
    'SUP: No advance button in Deliver': null,
    'OBS: messages > 15 (no stall)': null,
    'OBS: ≥3 unique senders': null,
    'OBS: chat disabled': null,
    'OBS: no advance button': null,
    'CREW: can send message': null,
    'CREW: no advance button': null,
    'CREW: AI responds to human': null,
  }
};

async function getToken() {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD })
  });
  const data = await resp.json();
  TOKEN = data.access_token;
  console.log('Token obtained:', TOKEN ? 'YES' : 'NO');
}

async function apiGet(path) {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${TOKEN}` }
  });
  return resp.json();
}

async function apiPost(path, body) {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify(body)
  });
  return resp.json();
}

async function getMessages(projectId) {
  const data = await apiGet(`/api/projects/${projectId}/messages`);
  return Array.isArray(data) ? data : (data.messages || []);
}

async function getCurrentStage(projectId) {
  const data = await apiGet(`/api/projects/${projectId}`);
  return data;
}

function screenshot(page, name) {
  return page.screenshot({ path: path.join(SCREENSHOT_DIR, `accept-${name}.png`), fullPage: true });
}

function checkTemplatePatterns(messages) {
  const templatePhrases = [
    '我是', '作為一個', '在這個階段', '我們需要', 'Hello', 'Hi there',
    '步驟一', '步驟二', '首先我們', '接下來', '作為AI'
  ];
  const violations = [];
  for (const msg of messages) {
    if (!msg.content) continue;
    for (const phrase of templatePhrases) {
      if (msg.content.startsWith(phrase)) {
        violations.push({ sender: msg.sender_id || msg.role, phrase, content: msg.content.substring(0, 80) });
      }
    }
  }
  return violations;
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ============================================================
// TEST 1: SUPERVISOR — Full 4 Phase Journey
// ============================================================
async function testSupervisor(browser) {
  console.log('\n=== TEST 1: SUPERVISOR ===');
  const pid = PROJECTS.supervisor.id;
  const page = await browser.newPage();

  try {
    // Login
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects', { timeout: 10000 });
    await screenshot(page, 'sup-01-logged-in');
    console.log('Logged in');

    // Go to lobby
    await page.goto(`${BASE_URL}/projects/${pid}/lobby`);
    await page.waitForTimeout(2000);
    await screenshot(page, 'sup-02-lobby');

    // Take supervisor seat (first 入座 button)
    const seatBtns = await page.locator('button').filter({ hasText: '入座' }).all();
    console.log(`Found ${seatBtns.length} seat buttons`);
    if (seatBtns.length > 0) {
      await seatBtns[0].click();
      await page.waitForTimeout(2000);
      await screenshot(page, 'sup-03-seated');
      console.log('Took supervisor seat');
    }

    // Navigate to workspace
    const enterBtn = page.locator('button, a').filter({ hasText: /進入工作區|開始|Enter/ }).first();
    if (await enterBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await enterBtn.click();
      await page.waitForTimeout(2000);
    } else {
      await page.goto(`${BASE_URL}/projects/${pid}/workspace`);
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'sup-04-workspace-discover');
    console.log('In workspace (DISCOVER phase)');

    // Wait 60s in DISCOVER, observe agents
    console.log('Waiting 60s in DISCOVER phase...');
    await sleep(30000);

    // Check mid-way
    let msgs = await getMessages(pid);
    console.log(`  After 30s: ${msgs.length} messages`);
    await screenshot(page, 'sup-05-discover-30s');

    await sleep(30000);

    msgs = await getMessages(pid);
    const discoverSenders = new Set(msgs.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));
    console.log(`  After 60s: ${msgs.length} messages, senders: ${[...discoverSenders].join(', ')}`);
    await screenshot(page, 'sup-06-discover-60s');

    results.supervisor.discoverMessages = msgs.length;
    results.supervisor.discoverSenders = [...discoverSenders];

    // Check template patterns
    const templateViolations = checkTemplatePatterns(msgs);
    results.supervisor.templateViolations = templateViolations;
    console.log(`  Template violations: ${templateViolations.length}`);

    // Advance to DEFINE
    console.log('Advancing to DEFINE...');
    const advanceBefore = await apiPost(`/api/projects/${pid}/advance`, {});
    console.log(`  Advance response: ${JSON.stringify(advanceBefore).substring(0, 100)}`);
    await page.waitForTimeout(2000);

    let stageData = await getCurrentStage(pid);
    results.supervisor.afterDefineStage = stageData.current_stage;
    results.supervisor.afterDefineMicroPhase = stageData.micro_phase;
    console.log(`  Stage after advance: ${stageData.current_stage}, micro_phase: ${stageData.micro_phase}`);
    await screenshot(page, 'sup-07-define-phase');

    // Wait 30s in DEFINE
    console.log('Waiting 30s in DEFINE...');
    await sleep(30000);
    await screenshot(page, 'sup-08-define-30s');

    // Advance to DEVELOP
    console.log('Advancing to DEVELOP...');
    await apiPost(`/api/projects/${pid}/advance`, {});
    await page.waitForTimeout(2000);

    stageData = await getCurrentStage(pid);
    results.supervisor.afterDevelopStage = stageData.current_stage;
    results.supervisor.afterDevelopMicroPhase = stageData.micro_phase;
    console.log(`  Stage after advance: ${stageData.current_stage}, micro_phase: ${stageData.micro_phase}`);
    await screenshot(page, 'sup-09-develop-phase');

    // Wait 30s in DEVELOP
    console.log('Waiting 30s in DEVELOP...');
    await sleep(30000);
    await screenshot(page, 'sup-10-develop-30s');

    // Advance to DELIVER
    console.log('Advancing to DELIVER...');
    await apiPost(`/api/projects/${pid}/advance`, {});
    await page.waitForTimeout(2000);

    stageData = await getCurrentStage(pid);
    results.supervisor.afterDeliverStage = stageData.current_stage;
    results.supervisor.afterDeliverMicroPhase = stageData.micro_phase;
    console.log(`  Stage after advance: ${stageData.current_stage}, micro_phase: ${stageData.micro_phase}`);
    await screenshot(page, 'sup-11-deliver-phase');

    // Check for advance button in DELIVER (should NOT exist)
    await page.reload();
    await page.waitForTimeout(2000);
    const deliverAdvanceBtn = await page.locator('button').filter({ hasText: /推進到|下一階段|advance/i }).first();
    const hasAdvanceInDeliver = await deliverAdvanceBtn.isVisible({ timeout: 3000 }).catch(() => false);
    results.supervisor.hasAdvanceInDeliver = hasAdvanceInDeliver;
    console.log(`  Advance button visible in DELIVER: ${hasAdvanceInDeliver}`);
    await screenshot(page, 'sup-12-deliver-no-advance');

    // Final message count
    const finalMsgs = await getMessages(pid);
    const finalSenders = new Set(finalMsgs.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));
    results.supervisor.finalMessages = finalMsgs.length;
    results.supervisor.finalSenders = [...finalSenders];
    console.log(`  Final: ${finalMsgs.length} messages, ${finalSenders.size} unique senders`);

    // Evaluate checklist
    results.checklist['SUP: ≥3 unique AI senders'] = discoverSenders.size >= 3 ? 'PASS' : 'FAIL';
    results.checklist['SUP: Zero template patterns'] = templateViolations.length === 0 ? 'PASS' : 'FAIL';

    const defineMicro = results.supervisor.afterDefineMicroPhase;
    const developMicro = results.supervisor.afterDevelopMicroPhase;
    const deliverMicro = results.supervisor.afterDeliverMicroPhase;
    const microOk = defineMicro && defineMicro.startsWith('2') &&
                    developMicro && developMicro.startsWith('3') &&
                    deliverMicro && deliverMicro.startsWith('4');
    results.checklist['SUP: micro_phase resets correctly (2.1, 3.1, 4.1)'] = microOk ? 'PASS' : 'FAIL';
    results.checklist['SUP: No advance button in Deliver'] = !hasAdvanceInDeliver ? 'PASS' : 'FAIL';

  } catch (err) {
    console.error('Supervisor test error:', err.message);
    results.supervisor.error = err.message;
    await screenshot(page, 'sup-ERROR');
  } finally {
    await page.close();
  }
}

// ============================================================
// TEST 2: OBSERVER — 15-msg stall check
// ============================================================
async function testObserver(browser) {
  console.log('\n=== TEST 2: OBSERVER ===');
  const pid = PROJECTS.observer.id;
  const page = await browser.newPage();

  try {
    // Login
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects', { timeout: 10000 });

    // Go to lobby
    await page.goto(`${BASE_URL}/projects/${pid}/lobby`);
    await page.waitForTimeout(2000);
    await screenshot(page, 'obs-01-lobby');

    // Click observer entry
    const observerBtn = page.locator('button, a').filter({ hasText: /觀察者|Observer/i }).first();
    if (await observerBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await observerBtn.click();
      await page.waitForTimeout(2000);
      console.log('Clicked observer button');
    } else {
      console.log('Observer button not found, looking for alternatives...');
      const allBtns = await page.locator('button').allTextContents();
      console.log('Available buttons:', allBtns);
    }
    await screenshot(page, 'obs-02-observer-entered');

    // Navigate to workspace
    const enterBtn = page.locator('button, a').filter({ hasText: /進入工作區|開始|Enter/ }).first();
    if (await enterBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await enterBtn.click();
      await page.waitForTimeout(2000);
    } else {
      await page.goto(`${BASE_URL}/projects/${pid}/workspace`);
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'obs-03-workspace');
    console.log('Observer in workspace, waiting 120s...');

    // Check messages at intervals
    for (let t = 30; t <= 120; t += 30) {
      await sleep(30000);
      const msgs = await getMessages(pid);
      console.log(`  After ${t}s: ${msgs.length} messages`);
      await screenshot(page, `obs-0${t/30+3}-at-${t}s`);

      if (t === 120) {
        const senders = new Set(msgs.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));
        results.observer.finalMessages = msgs.length;
        results.observer.finalSenders = [...senders];
        console.log(`  Final: ${msgs.length} msgs, ${senders.size} senders: ${[...senders].join(', ')}`);
      }
    }

    // Check chat input disabled
    const chatInput = page.locator('textarea, input[placeholder*="輸入"], input[type="text"]').first();
    const chatInputDisabled = await chatInput.isDisabled({ timeout: 3000 }).catch(() => true);
    const chatInputReadonly = await chatInput.getAttribute('disabled').catch(() => null);
    results.observer.chatInputDisabled = chatInputDisabled;
    console.log(`  Chat input disabled: ${chatInputDisabled}`);
    await screenshot(page, 'obs-08-chat-disabled-check');

    // Check no advance button
    const advanceBtn = page.locator('button').filter({ hasText: /推進到|下一階段/i }).first();
    const hasAdvance = await advanceBtn.isVisible({ timeout: 3000 }).catch(() => false);
    results.observer.hasAdvanceButton = hasAdvance;
    console.log(`  Has advance button: ${hasAdvance}`);

    // Evaluate checklist
    const finalMsgCount = results.observer.finalMessages || 0;
    const finalSenderCount = (results.observer.finalSenders || []).length;
    results.checklist['OBS: messages > 15 (no stall)'] = finalMsgCount > 15 ? 'PASS' : 'FAIL';
    results.checklist['OBS: ≥3 unique senders'] = finalSenderCount >= 3 ? 'PASS' : 'FAIL';
    results.checklist['OBS: chat disabled'] = chatInputDisabled ? 'PASS' : 'FAIL';
    results.checklist['OBS: no advance button'] = !hasAdvance ? 'PASS' : 'FAIL';

  } catch (err) {
    console.error('Observer test error:', err.message);
    results.observer.error = err.message;
    await screenshot(page, 'obs-ERROR');
  } finally {
    await page.close();
  }
}

// ============================================================
// TEST 3: CREW — Can chat, can't advance
// ============================================================
async function testCrew(browser) {
  console.log('\n=== TEST 3: CREW ===');
  const pid = PROJECTS.crew.id;
  const page = await browser.newPage();

  try {
    // Login
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects', { timeout: 10000 });

    // Go to lobby
    await page.goto(`${BASE_URL}/projects/${pid}/lobby`);
    await page.waitForTimeout(2000);
    await screenshot(page, 'crew-01-lobby');

    // Take second seat (crew_1) - find all 入座 buttons, click second one
    const seatBtns = await page.locator('button').filter({ hasText: '入座' }).all();
    console.log(`Found ${seatBtns.length} seat buttons`);
    if (seatBtns.length >= 2) {
      await seatBtns[1].click();
      await page.waitForTimeout(2000);
      console.log('Took crew_1 seat (second button)');
    } else if (seatBtns.length === 1) {
      // If only one, there might be role-specific buttons
      console.log('Only 1 seat button, checking all buttons...');
      const allBtns = await page.locator('button').allTextContents();
      console.log('All buttons:', allBtns.slice(0, 20));
      await seatBtns[0].click();
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'crew-02-seated');

    // Navigate to workspace
    const enterBtn = page.locator('button, a').filter({ hasText: /進入工作區|開始|Enter/ }).first();
    if (await enterBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await enterBtn.click();
      await page.waitForTimeout(2000);
    } else {
      await page.goto(`${BASE_URL}/projects/${pid}/workspace`);
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'crew-03-workspace');
    console.log('Crew in workspace');

    // Wait 30s for agents to start
    console.log('Waiting 30s for agents...');
    await sleep(30000);
    await screenshot(page, 'crew-04-after-30s');

    // Get message count before sending
    const msgsBefore = await getMessages(pid);
    const countBefore = msgsBefore.length;
    console.log(`  Messages before sending: ${countBefore}`);

    // Type and send message
    const testMsg = '我覺得購物車的輪子設計很重要';
    const chatInput = page.locator('textarea, input[placeholder*="輸入"], input[type="text"]').first();

    if (await chatInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await chatInput.fill(testMsg);
      await screenshot(page, 'crew-05-typed');

      // Press Enter or click send
      await chatInput.press('Enter');
      await page.waitForTimeout(3000);
      await screenshot(page, 'crew-06-sent');
      console.log('Message sent');
    } else {
      console.log('Chat input not visible, checking alternatives...');
      await screenshot(page, 'crew-05-no-input');
    }

    // Verify message appeared in API
    await sleep(5000);
    const msgsAfter = await getMessages(pid);
    const userMsg = msgsAfter.find(m => m.content && m.content.includes('輪子設計'));
    results.crew.messageSent = !!userMsg;
    results.crew.messagesAfterSend = msgsAfter.length;
    console.log(`  Messages after: ${msgsAfter.length}, user msg found: ${!!userMsg}`);

    // Check no advance button for crew
    const advanceBtn = page.locator('button').filter({ hasText: /推進到|下一階段/i }).first();
    const hasAdvance = await advanceBtn.isVisible({ timeout: 3000 }).catch(() => false);
    results.crew.hasAdvanceButton = hasAdvance;
    console.log(`  Has advance button: ${hasAdvance}`);

    // Wait 30s more to see if AI responds
    console.log('Waiting 30s for AI response to human message...');
    await sleep(30000);
    await screenshot(page, 'crew-07-ai-response');

    const msgsWithResponse = await getMessages(pid);
    const senders = new Set(msgsWithResponse.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));

    // Check if any AI message came after user's message
    const userMsgIndex = msgsWithResponse.findIndex(m => m.content && m.content.includes('輪子設計'));
    const aiResponseAfter = userMsgIndex >= 0 &&
      msgsWithResponse.slice(userMsgIndex + 1).some(m => {
        const sender = m.sender_id || m.role || m.agent_id || '';
        return sender.includes('agent') || sender.includes('AI') || sender.includes('ai');
      });

    results.crew.aiRespondedAfterHuman = aiResponseAfter;
    results.crew.finalSenders = [...senders];
    console.log(`  AI responded after human: ${aiResponseAfter}`);
    console.log(`  Final senders: ${[...senders].join(', ')}`);
    await screenshot(page, 'crew-08-final');

    // Evaluate checklist
    results.checklist['CREW: can send message'] = results.crew.messageSent ? 'PASS' : 'FAIL';
    results.checklist['CREW: no advance button'] = !hasAdvance ? 'PASS' : 'FAIL';
    results.checklist['CREW: AI responds to human'] = aiResponseAfter ? 'PASS' : 'FAIL';

  } catch (err) {
    console.error('Crew test error:', err.message);
    results.crew.error = err.message;
    await screenshot(page, 'crew-ERROR');
  } finally {
    await page.close();
  }
}

// ============================================================
// MAIN
// ============================================================
async function main() {
  console.log('=== FINAL ACCEPTANCE TEST START ===');
  console.log(`Time: ${new Date().toISOString()}`);

  await getToken();

  const browser = await chromium.launch({ headless: true });

  try {
    // Run tests sequentially to avoid auth conflicts
    await testSupervisor(browser);
    await testObserver(browser);
    await testCrew(browser);
  } finally {
    await browser.close();
  }

  // Print final report
  console.log('\n=== FINAL ACCEPTANCE REPORT ===');
  console.log('\nSUPERVISOR RESULTS:');
  console.log(`  DISCOVER messages: ${results.supervisor.discoverMessages}`);
  console.log(`  DISCOVER senders: ${(results.supervisor.discoverSenders || []).join(', ')}`);
  console.log(`  Template violations: ${(results.supervisor.templateViolations || []).length}`);
  console.log(`  After DEFINE: stage=${results.supervisor.afterDefineStage}, micro=${results.supervisor.afterDefineMicroPhase}`);
  console.log(`  After DEVELOP: stage=${results.supervisor.afterDevelopStage}, micro=${results.supervisor.afterDevelopMicroPhase}`);
  console.log(`  After DELIVER: stage=${results.supervisor.afterDeliverStage}, micro=${results.supervisor.afterDeliverMicroPhase}`);
  console.log(`  Advance btn in DELIVER: ${results.supervisor.hasAdvanceInDeliver}`);

  console.log('\nOBSERVER RESULTS:');
  console.log(`  Final messages: ${results.observer.finalMessages}`);
  console.log(`  Final senders: ${(results.observer.finalSenders || []).join(', ')}`);
  console.log(`  Chat disabled: ${results.observer.chatInputDisabled}`);
  console.log(`  Has advance btn: ${results.observer.hasAdvanceButton}`);

  console.log('\nCREW RESULTS:');
  console.log(`  Message sent: ${results.crew.messageSent}`);
  console.log(`  Has advance btn: ${results.crew.hasAdvanceButton}`);
  console.log(`  AI responded: ${results.crew.aiRespondedAfterHuman}`);

  console.log('\n=== CHECKLIST ===');
  let passCount = 0, failCount = 0;
  for (const [key, value] of Object.entries(results.checklist)) {
    const status = value || 'UNKNOWN';
    const icon = status === 'PASS' ? '[PASS]' : status === 'FAIL' ? '[FAIL]' : '[???]';
    console.log(`  ${icon} ${key}`);
    if (status === 'PASS') passCount++;
    else failCount++;
  }

  console.log(`\n  Total: ${passCount} PASS, ${failCount} FAIL`);
  const overall = failCount === 0 ? 'ACCEPTED' : 'REJECTED';
  console.log(`\n  FINAL VERDICT: ${overall}`);

  // Save report
  const report = {
    timestamp: new Date().toISOString(),
    projects: PROJECTS,
    results,
    verdict: overall,
    passCount,
    failCount
  };
  fs.writeFileSync(
    path.join(__dirname, 'final-acceptance-report.json'),
    JSON.stringify(report, null, 2)
  );
  console.log('\nReport saved to e2e/final-acceptance-report.json');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
