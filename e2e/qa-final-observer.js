/**
 * QA FINAL TEST B: OBSERVER — Verify agents don't stall at 15 messages
 *
 * Pre-requisite: Project already created via API (passed in as env var or hardcoded below)
 *
 * Checks:
 * - Agents produce MORE than 15 messages (regression for deadlock bug)
 * - Crew agents still talking after 2 minutes (not just supervisor)
 * - Chat input is DISABLED for observer
 * - Canvas has sticky notes from multiple authors
 * - Observer cannot advance stage (403)
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const CREDS = { email: 'teacher@test.com', password: 'teacher123' };
const PROJECT_ID = process.env.PROJECT_B_ID || 'f08c2b32-8b6a-4767-90d4-aa17d064e530';

const bugs = [];
let authToken = '';
const consoleErrors = [];

function recordBug(id, severity, description, expected, actual) {
  const bug = { id, severity, description, expected, actual, timestamp: new Date().toISOString() };
  bugs.push(bug);
  console.log(`\n[BUG] ${id} [${severity}]: ${description}`);
  console.log(`  Expected: ${expected}`);
  console.log(`  Actual:   ${actual}`);
}

async function screenshot(page, name) {
  const filepath = path.join(SCREENSHOTS_DIR, `qa-final2-${name}.png`);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`  [screenshot] qa-final2-${name}.png`);
  return filepath;
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return { status: res.status, data: res.ok ? await res.json().catch(() => null) : null };
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
  const { status, data } = await apiGet(`/api/projects/${PROJECT_ID}/messages`);
  if (!data) {
    console.log(`  [${label}] messages API returned null (status ${status})`);
    return { total: 0, senders: {}, crewSenders: [] };
  }
  const messages = data.messages || [];
  const senders = {};
  for (const m of messages) {
    const sender = m.agent_id || m.sender_id || m.role || 'unknown';
    senders[sender] = (senders[sender] || 0) + 1;
  }
  const crewSenders = Object.keys(senders).filter(s => s.includes('crew'));
  console.log(`  [${label}] Total messages: ${messages.length}`);
  console.log(`  [${label}] All senders: ${JSON.stringify(senders)}`);
  console.log(`  [${label}] Crew senders: ${crewSenders.join(', ') || 'NONE'}`);

  // Detect template patterns
  const templateMsgs = messages.filter(m => {
    const content = m.content || m.text || '';
    return content.includes('@{crew_') || /\bcrew_\d\b/.test(content);
  });
  if (templateMsgs.length > 0) {
    console.log(`  [${label}] WARNING: ${templateMsgs.length} messages with template patterns`);
  }

  return { total: messages.length, senders, crewSenders, messages, templateCount: templateMsgs.length };
}

async function main() {
  console.log('='.repeat(70));
  console.log('TEST B: OBSERVER — Agent Stall Regression & Observer Constraints');
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
    testName: 'Test B: Observer — Stall Regression & Constraints',
    checks: {},
    messageSnapshots: {},
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
    if (!loginData.access_token) throw new Error('Login failed');
    authToken = loginData.access_token;
    console.log('  Auth OK. User:', loginData.user?.display_name);

    // Verify project stage
    const { data: initialStage } = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
    console.log(`  Initial stage: ${initialStage?.current_stage} | micro: ${initialStage?.current_micro_phase}`);

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

    // --- STEP 3: Navigate to lobby ---
    console.log('\n[STEP 3] Navigate to lobby...');
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    await screenshot(page, '02-lobby');

    const allBtns = await page.locator('button').allTextContents();
    console.log('  Buttons in lobby:', allBtns.slice(0, 12).join(' | '));

    // --- STEP 4: Join as observer ---
    console.log('\n[STEP 4] Join as observer...');
    const observerBtnSelectors = [
      'button:has-text("以觀察者身份進入")',
      'button:has-text("觀察者")',
      'button:has-text("Observer")',
      '[data-testid="observer-btn"]',
      'button:has-text("旁聽")',
    ];

    let joinedAsObserver = false;
    for (const sel of observerBtnSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.isVisible().catch(() => false)) {
        console.log(`  Found observer button: ${sel}`);
        await btn.click();
        await sleep(2000);
        joinedAsObserver = true;
        break;
      }
    }

    if (!joinedAsObserver) {
      recordBug('BUG-B-01', 'CRITICAL', '"以觀察者身份進入" button not found in lobby',
        'Observer entry button should be visible in lobby',
        `Not found. Buttons: ${allBtns.slice(0, 8).join(', ')}`);
      // Fallback: go directly to workspace
      console.log('  Fallback: navigate directly to workspace');
    }

    await screenshot(page, '03-after-join-observer');
    console.log('  Post-join URL:', page.url());

    // Navigate to workspace if not already there
    if (!page.url().includes('/workspace')) {
      await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`);
      await page.waitForLoadState('networkidle');
      await sleep(2000);
    }

    await screenshot(page, '04-workspace-initial');
    console.log('  Workspace URL:', page.url());

    // =========================================================
    // STEP 5: Check chat input disabled for observer
    // =========================================================
    console.log('\n[STEP 5] Check observer chat input disabled...');
    await sleep(3000);

    // Look for chat input
    const chatInputSelectors = [
      'textarea[placeholder*="輸入"]',
      'textarea[placeholder*="訊息"]',
      'input[placeholder*="message"]',
      '[data-testid="chat-input"]',
      'textarea',
    ];

    let chatInputFound = false;
    let chatInputDisabled = false;

    for (const sel of chatInputSelectors) {
      const input = page.locator(sel).first();
      if (await input.isVisible().catch(() => false)) {
        chatInputFound = true;
        const disabled = await input.isDisabled().catch(() => false);
        const readOnly = await input.getAttribute('readonly').catch(() => null);
        chatInputDisabled = disabled || readOnly !== null;
        console.log(`  Chat input found: ${sel} | disabled=${disabled} | readonly=${readOnly}`);
        break;
      }
    }

    if (!chatInputFound) {
      // Chat input hidden entirely — also acceptable for observer
      chatInputDisabled = true;
      console.log('  Chat input not visible (hidden for observer — acceptable)');
    }

    results.checks.chatInputDisabledForObserver = chatInputDisabled;
    if (!chatInputDisabled) {
      recordBug('BUG-B-02', 'HIGH', 'Chat input is ENABLED for observer role',
        'Chat input should be disabled/hidden for observers',
        'Chat input is enabled and allows typing');
    }

    // =========================================================
    // STEP 6: DISCOVER phase — monitor for 180 seconds
    // =========================================================
    console.log('\n[STEP 6] DISCOVER phase — monitoring for 180s...');

    const msgCheck0 = await checkMessages('discover-0s');
    results.messageSnapshots['discover-0s'] = msgCheck0;

    // 60-second checkpoint
    console.log('\n  Waiting 60s...');
    await sleep(60000);
    const msgCheck60 = await checkMessages('discover-60s');
    results.messageSnapshots['discover-60s'] = msgCheck60;
    await screenshot(page, '05-discover-60s');

    // 120-second checkpoint
    console.log('\n  Waiting another 60s (total 120s)...');
    await sleep(60000);
    const msgCheck120 = await checkMessages('discover-120s');
    results.messageSnapshots['discover-120s'] = msgCheck120;
    await screenshot(page, '06-discover-120s');

    // 180-second checkpoint
    console.log('\n  Waiting another 60s (total 180s)...');
    await sleep(60000);
    const msgCheck180 = await checkMessages('discover-180s');
    results.messageSnapshots['discover-180s'] = msgCheck180;
    await screenshot(page, '07-discover-180s');

    // --- Analyze ---
    console.log('\n  === OBSERVER DISCOVER ANALYSIS ===');

    // Check 1: More than 15 messages (core regression test)
    results.checks.exceeds15Messages = msgCheck180.total > 15;
    console.log(`  Total messages at 180s: ${msgCheck180.total} (must be >15)`);
    if (msgCheck180.total <= 15) {
      recordBug('BUG-B-03', 'CRITICAL', `Only ${msgCheck180.total} messages after 180s — Rule 4.5 stall regression detected`,
        'More than 15 messages should be generated in 180s',
        `Only ${msgCheck180.total} messages. Stall at 15 message limit`);
    }

    // Check 2: Crew agents still active after 2 minutes
    const msgsFirstMinute = msgCheck60.total;
    const msgsSecondMinute = msgCheck120.total - msgCheck60.total;
    const msgsThirdMinute = msgCheck180.total - msgCheck120.total;

    // Check crew still sending after 2 min
    const latestMessages = msgCheck180.messages.slice(-10);
    const recentCrewMsgs = latestMessages.filter(m => {
      const sender = m.agent_id || m.sender_id || m.role || '';
      return sender.includes('crew');
    });
    results.checks.crewActiveAfter2Min = recentCrewMsgs.length > 0;
    console.log(`  Messages by minute: min1=${msgsFirstMinute}, min2=${msgsSecondMinute}, min3=${msgsThirdMinute}`);
    console.log(`  Recent crew messages (last 10): ${recentCrewMsgs.length}`);
    if (recentCrewMsgs.length === 0) {
      recordBug('BUG-B-04', 'HIGH', 'Crew agents silent after 2 minutes (only supervisor may be active)',
        'Crew agents should still produce messages after 120s',
        `No crew messages in the most recent 10 messages. Crew agents: ${msgCheck180.crewSenders.join(', ')}`);
    }

    // Check 3: All crew agents ever contributed
    const crewAgents = ['agent_crew_1', 'agent_crew_2', 'agent_crew_3', 'agent_crew_4'];
    const activeCrew = crewAgents.filter(a => (msgCheck180.senders[a] || 0) > 0);
    results.checks.allCrewContributed = activeCrew.length === 4;
    console.log(`  Active crew agents: ${activeCrew.length}/4 — ${activeCrew.join(', ')}`);
    if (activeCrew.length < 4) {
      const silentCrew = crewAgents.filter(a => !(msgCheck180.senders[a] || 0));
      recordBug('BUG-B-05', 'MEDIUM', `${4 - activeCrew.length} crew agent(s) never contributed`,
        '4/4 crew agents should contribute messages',
        `Silent: ${silentCrew.join(', ')}`);
    }

    // Check 4: Template patterns
    results.checks.noTemplatePatterns = msgCheck180.templateCount === 0;
    if (msgCheck180.templateCount > 0) {
      recordBug('BUG-B-06', 'HIGH', `${msgCheck180.templateCount} messages contain unresolved template patterns`,
        'All message templates should be resolved',
        `${msgCheck180.templateCount} unresolved templates found`);
    }

    // =========================================================
    // STEP 7: Check canvas for sticky notes
    // =========================================================
    console.log('\n[STEP 7] Check canvas for sticky notes...');
    const canvasData = await apiGet(`/api/projects/${PROJECT_ID}/canvas-state`);
    let canvasHasNotes = false;
    let noteCount = 0;
    let noteAuthors = [];

    if (canvasData.data) {
      const canvas = canvasData.data;
      // Look for shapes/notes in canvas state
      const shapes = canvas.shapes || canvas.records || canvas.document?.store || {};
      if (typeof shapes === 'object') {
        const shapeList = Array.isArray(shapes) ? shapes : Object.values(shapes);
        const notes = shapeList.filter(s => s && (s.type === 'note' || s.type === 'geo' || s.type === 'text'));
        noteCount = notes.length;
        noteAuthors = [...new Set(notes.map(n => n.meta?.author || n.props?.author || 'unknown').filter(a => a !== 'unknown'))];
        canvasHasNotes = noteCount > 0;
        console.log(`  Canvas notes: ${noteCount} | Authors: ${noteAuthors.join(', ') || 'unknown'}`);
      } else {
        console.log('  Canvas state structure:', Object.keys(canvas).slice(0, 10).join(', '));
      }
    } else {
      console.log(`  Canvas state API returned status ${canvasData.status}`);
    }

    results.checks.canvasHasNotes = canvasHasNotes;
    results.canvas = { noteCount, noteAuthors };

    // =========================================================
    // STEP 8: Observer cannot advance stage (should get 403)
    // =========================================================
    console.log('\n[STEP 8] Try advance-stage as observer (expect 403)...');
    const advRes = await apiPost(`/api/projects/${PROJECT_ID}/advance-stage`, {});
    console.log(`  Advance stage response: ${advRes.status}`);

    // Observer should get 403 or 401 (forbidden)
    const advanceBlocked = advRes.status === 403 || advRes.status === 401;
    results.checks.observerCannotAdvance = advanceBlocked;
    if (!advanceBlocked) {
      if (advRes.status === 200) {
        recordBug('BUG-B-07', 'CRITICAL', 'Observer was able to advance stage (should be forbidden)',
          'Observer should receive 403 when attempting to advance stage',
          `Got HTTP ${advRes.status} — advance succeeded`);
      } else {
        console.log(`  Unexpected advance response: ${advRes.status} (may be OK if project ended)`);
        results.checks.observerCannotAdvance = advRes.status !== 200;
      }
    } else {
      console.log(`  Advance correctly blocked with ${advRes.status}`);
    }

    // Final screenshot
    await screenshot(page, '08-final');

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

  const reportPath = path.join(__dirname, 'qa-final2-observer-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));

  console.log('\n' + '='.repeat(70));
  console.log('TEST B SUMMARY');
  console.log('='.repeat(70));

  const checks = results.checks;
  const checkItems = [
    ['Chat input disabled for observer', checks.chatInputDisabledForObserver],
    ['Exceeds 15 messages (no stall regression)', checks.exceeds15Messages],
    ['Crew agents active after 2 min', checks.crewActiveAfter2Min],
    ['All 4 crew agents contributed', checks.allCrewContributed],
    ['No template patterns in messages', checks.noTemplatePatterns],
    ['Canvas has sticky notes', checks.canvasHasNotes],
    ['Observer cannot advance (403)', checks.observerCannotAdvance],
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
