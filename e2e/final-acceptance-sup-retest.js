/**
 * FINAL ACCEPTANCE - SUPERVISOR RE-TEST (with correct API endpoints)
 * Using /advance-stage endpoint instead of /advance
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

let TOKEN = '';

async function getToken() {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD })
  });
  const data = await resp.json();
  TOKEN = data.access_token;
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

async function getStage(projectId) {
  return apiGet(`/api/projects/${projectId}/stage`);
}

function screenshot(page, name) {
  return page.screenshot({ path: path.join(SCREENSHOT_DIR, `accept-${name}.png`), fullPage: true });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function main() {
  console.log('=== SUPERVISOR RE-TEST (correct API endpoints) ===');
  await getToken();

  // Create fresh project
  const proj = await apiPost('/api/projects', {
    name: 'Final-Sup2-購物車',
    description: '超市購物車重新設計。限制：寬度≤60cm、嵌套堆疊、手把95-105cm、推行力<5kg、成本≤NT$3000、回收材質≥80%',
    ai_contribution: 'high'
  });
  const pid = proj.id;
  console.log(`Created project: ${pid}`);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    // Login
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/projects', { timeout: 10000 });
    console.log('Logged in');

    // Go to lobby, take supervisor seat
    await page.goto(`${BASE_URL}/projects/${pid}/lobby`);
    await page.waitForTimeout(2000);
    await screenshot(page, 'sup2-01-lobby');

    const seatBtns = await page.locator('button').filter({ hasText: '入座' }).all();
    console.log(`Found ${seatBtns.length} seat buttons`);
    await seatBtns[0].click();
    await page.waitForTimeout(2000);
    await screenshot(page, 'sup2-02-seated');

    // Enter workspace
    const enterBtn = page.locator('button, a').filter({ hasText: /進入工作區|開始|Enter/ }).first();
    if (await enterBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await enterBtn.click();
      await page.waitForTimeout(2000);
    } else {
      await page.goto(`${BASE_URL}/projects/${pid}/workspace`);
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'sup2-03-workspace-discover');
    console.log('In DISCOVER phase workspace');

    // Wait 60s in DISCOVER
    console.log('Waiting 60s in DISCOVER...');
    await sleep(30000);
    let msgs = await getMessages(pid);
    console.log(`  After 30s: ${msgs.length} messages`);

    await sleep(30000);
    msgs = await getMessages(pid);
    const discoverSenders = new Set(msgs.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));
    console.log(`  After 60s: ${msgs.length} messages, ${discoverSenders.size} senders: ${[...discoverSenders].join(', ')}`);
    await screenshot(page, 'sup2-04-discover-60s');

    // Check template patterns
    const templatePhrases = ['我是', '作為一個', '在這個階段', '作為AI', 'Hello', 'Hi there'];
    const violations = msgs.filter(m =>
      m.content && templatePhrases.some(p => m.content.startsWith(p))
    );
    console.log(`  Template violations: ${violations.length}`);

    // ADVANCE to DEFINE via correct endpoint
    console.log('Advancing discover -> define via advance-stage...');
    const defineResp = await apiPost(`/api/projects/${pid}/advance-stage`, {
      from: 'discover', to: 'define', reason: 'supervisor acceptance test'
    });
    console.log(`  Response: ${JSON.stringify(defineResp)}`);
    await page.waitForTimeout(3000);

    const defineStage = await getStage(pid);
    console.log(`  Stage: ${defineStage.current_stage}, micro: ${defineStage.current_micro_phase}`);
    await screenshot(page, 'sup2-05-define-phase');

    // Wait 30s in DEFINE
    console.log('Waiting 30s in DEFINE...');
    await sleep(30000);
    await screenshot(page, 'sup2-06-define-30s');

    // ADVANCE to DEVELOP
    console.log('Advancing define -> develop...');
    const developResp = await apiPost(`/api/projects/${pid}/advance-stage`, {
      from: 'define', to: 'develop', reason: 'supervisor acceptance test'
    });
    console.log(`  Response: ${JSON.stringify(developResp)}`);
    await page.waitForTimeout(3000);

    const developStage = await getStage(pid);
    console.log(`  Stage: ${developStage.current_stage}, micro: ${developStage.current_micro_phase}`);
    await screenshot(page, 'sup2-07-develop-phase');

    // Wait 30s in DEVELOP
    console.log('Waiting 30s in DEVELOP...');
    await sleep(30000);
    await screenshot(page, 'sup2-08-develop-30s');

    // ADVANCE to DELIVER
    console.log('Advancing develop -> deliver...');
    const deliverResp = await apiPost(`/api/projects/${pid}/advance-stage`, {
      from: 'develop', to: 'deliver', reason: 'supervisor acceptance test'
    });
    console.log(`  Response: ${JSON.stringify(deliverResp)}`);
    await page.waitForTimeout(3000);

    const deliverStage = await getStage(pid);
    console.log(`  Stage: ${deliverStage.current_stage}, micro: ${deliverStage.current_micro_phase}`);

    // Reload page to get updated UI
    await page.reload();
    await page.waitForTimeout(3000);
    await screenshot(page, 'sup2-09-deliver-phase');

    // Check advance button in DELIVER (should NOT be visible)
    const advanceBtn = page.locator('button').filter({ hasText: /推進到/i }).first();
    const hasAdvance = await advanceBtn.isVisible({ timeout: 3000 }).catch(() => false);
    console.log(`  Advance button visible in DELIVER: ${hasAdvance}`);
    await screenshot(page, 'sup2-10-deliver-no-advance-check');

    // Final counts
    const finalMsgs = await getMessages(pid);
    const finalSenders = new Set(finalMsgs.map(m => m.sender_id || m.role || m.agent_id).filter(Boolean));
    console.log(`  Final: ${finalMsgs.length} messages, ${finalSenders.size} senders: ${[...finalSenders].join(', ')}`);

    // RESULTS
    console.log('\n=== SUPERVISOR RE-TEST RESULTS ===');
    const r1 = discoverSenders.size >= 3;
    const r2 = violations.length === 0;
    const r3 = defineStage.current_micro_phase?.startsWith('2') &&
                developStage.current_micro_phase?.startsWith('3') &&
                deliverStage.current_micro_phase?.startsWith('4');
    const r4 = !hasAdvance;

    console.log(`  [${r1 ? 'PASS' : 'FAIL'}] SUP: ≥3 unique AI senders (${discoverSenders.size})`);
    console.log(`  [${r2 ? 'PASS' : 'FAIL'}] SUP: Zero template patterns (${violations.length} violations)`);
    console.log(`  [${r3 ? 'PASS' : 'FAIL'}] SUP: micro_phase resets (define=${defineStage.current_micro_phase}, develop=${developStage.current_micro_phase}, deliver=${deliverStage.current_micro_phase})`);
    console.log(`  [${r4 ? 'PASS' : 'FAIL'}] SUP: No advance button in Deliver`);

    const allPass = r1 && r2 && r3 && r4;
    console.log(`\n  SUPERVISOR VERDICT: ${allPass ? 'PASS' : 'FAIL'}`);

    return { r1, r2, r3, r4, allPass };

  } catch (err) {
    console.error('Error:', err.message);
    await screenshot(page, 'sup2-ERROR');
    return null;
  } finally {
    await page.close();
    await browser.close();
  }
}

main().catch(err => { console.error(err); process.exit(1); });
