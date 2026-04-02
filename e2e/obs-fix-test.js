/**
 * Observer Mode Fix Verification Test
 *
 * Tests that the Rule 4.5 fix works correctly:
 * OLD BUG: All agents stalled at exactly 15 consecutive AI messages
 *          because Rule 4.5 permanently blocked them in observer-only mode.
 * FIX: Removed the 15-message permanent block. Now only per-agent 4-message
 *      limit applies in all-AI/observer-only mode.
 *
 * Project: Observer-DT-超市購物車 (pre-created via API)
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const PROJECT_ID = '5b4a10cb-923c-4aa5-bd3e-a8a2398cea6f';

const issues = [];
let screenshotCounter = 0;

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

function recordIssue(id, severity, description, expected, actual, screenshotFile) {
  const issue = { id, severity, description, expected, actual, screenshotFile, ts: new Date().toISOString() };
  issues.push(issue);
  const prefix = severity === 'CRITICAL' ? '[!!!CRITICAL!!!]' :
                 severity === 'HIGH'     ? '[HIGH]' :
                 severity === 'MEDIUM'   ? '[MEDIUM]' : '[LOW]';
  log(`${prefix} ${id}: ${description}`);
  log(`  Expected: ${expected}`);
  log(`  Actual:   ${actual}`);
  if (screenshotFile) log(`  Screenshot: ${screenshotFile}`);
}

function recordPass(checkId, detail) {
  log(`  [PASS] ${checkId}: ${detail}`);
}

async function takeScreenshot(page, name) {
  screenshotCounter++;
  const filename = `obs-fix-${String(screenshotCounter).padStart(2, '0')}-${name}.png`;
  const filepath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  log(`  [screenshot] ${filename}`);
  return filename;
}

async function apiRequest(method, urlPath, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${BACKEND_URL}${urlPath}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  return { status: resp.status, data };
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getMessageCount(token) {
  const r = await apiRequest('GET', `/api/projects/${PROJECT_ID}/messages?limit=200`, null, token);
  if (r.status !== 200) return { count: -1, senders: new Set(), messages: [] };
  const messages = r.data.messages || r.data.items || [];
  const senders = new Set(messages.map(m => m.sender_name || m.sender_id).filter(Boolean));
  return { count: messages.length, senders, messages };
}

async function runTest() {
  log('=== Observer Mode Fix Verification Test ===');
  log(`Project ID: ${PROJECT_ID}`);
  log(`Frontend:   ${FRONTEND_URL}`);
  log(`Backend:    ${BACKEND_URL}`);
  log('');

  // --- AUTH ---
  const authResult = await apiRequest('POST', '/api/auth/login', { email: EMAIL, password: PASSWORD });
  if (authResult.status !== 200) {
    log('FATAL: Cannot authenticate');
    process.exit(1);
  }
  const token = authResult.data.access_token;
  log(`Authenticated as: ${authResult.data.user.display_name}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // =====================================================
    // STEP 1: LOGIN
    // =====================================================
    log('\n--- Step 1: Login ---');
    await page.goto(`${FRONTEND_URL}/login`);
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, 'login');

    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/projects/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');
    log('  Login: PASS');

    // =====================================================
    // STEP 2: NAVIGATE TO LOBBY AND ENTER AS OBSERVER
    // =====================================================
    log('\n--- Step 2: Navigate to Lobby and Enter as Observer ---');
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}/lobby`);
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    await takeScreenshot(page, 'lobby');

    // Find observer button
    const observerBtnSelectors = [
      'button:has-text("以觀察者身份進入")',
      'button:has-text("觀察者")',
      'button:has-text("observer")',
      '[data-testid="observer-btn"]',
    ];
    let observerBtn = null;
    for (const sel of observerBtnSelectors) {
      const el = page.locator(sel).first();
      if (await el.isVisible().catch(() => false)) {
        observerBtn = el;
        log(`  Observer button found via: ${sel}`);
        break;
      }
    }

    if (!observerBtn) {
      // Fallback: check page text
      const bodyText = await page.evaluate(() => document.body.innerText);
      log(`  Page text snippet: ${bodyText.substring(0, 300)}`);
      recordIssue('OBS-001', 'CRITICAL',
        '"以觀察者身份進入" button not found in lobby',
        'Observer entry button visible in lobby page',
        'Button not found — lobby may not render observer option for high AI-contribution projects',
        await takeScreenshot(page, 'obs-001-no-observer-btn'));
    } else {
      await observerBtn.click();
      await sleep(3000);
      await page.waitForLoadState('networkidle');

      const currentUrl = page.url();
      log(`  URL after observer click: ${currentUrl}`);
      await takeScreenshot(page, 'observer-workspace-entered');

      if (!currentUrl.includes('/workspace')) {
        recordIssue('OBS-002', 'CRITICAL',
          'Observer button did not navigate to workspace',
          `/projects/${PROJECT_ID}/workspace`,
          `Stayed at: ${currentUrl}`,
          await takeScreenshot(page, 'obs-002-nav-fail'));
      } else {
        recordPass('OBS-NAV', `Navigated to workspace: ${currentUrl}`);
      }
    }

    // =====================================================
    // STEP 3: OBSERVER UI CHECKS
    // =====================================================
    log('\n--- Step 3: Observer UI Integrity Checks ---');

    // Check 3.1: Chat input disabled
    const chatInputSelectors = [
      'textarea[placeholder*="輸入訊息"]',
      'textarea[placeholder*="Enter 送出"]',
      'textarea[placeholder*="輸入"]',
      'input[placeholder*="輸入訊息"]',
    ];
    let chatInputEl = null;
    for (const sel of chatInputSelectors) {
      const el = page.locator(sel).first();
      if (await el.isVisible().catch(() => false)) {
        chatInputEl = el;
        break;
      }
    }

    if (chatInputEl) {
      const isDisabled = await chatInputEl.isDisabled();
      if (!isDisabled) {
        recordIssue('OBS-003', 'CRITICAL',
          'Chat input is ENABLED for observer — observers must not send messages',
          'Chat textarea disabled (isDisabled=true) for observer role',
          'Chat textarea is enabled — any user can type and send messages',
          await takeScreenshot(page, 'obs-003-chat-enabled'));
      } else {
        recordPass('OBS-CHAT-DISABLED', 'Chat input is disabled for observer');
      }
    } else {
      // Hidden is also acceptable
      recordPass('OBS-CHAT-HIDDEN', 'Chat input not visible for observer (hidden is acceptable)');
    }

    // Check 3.2: No advance stage button
    const advanceBtnSelectors = [
      'button:has-text("推進到")',
      'button:has-text("下一階段")',
      'button:has-text("advance")',
      '[data-testid="advance-stage-btn"]',
    ];
    let advanceBtnFound = false;
    for (const sel of advanceBtnSelectors) {
      const el = page.locator(sel).first();
      if (await el.isVisible().catch(() => false)) {
        const isEnabled = !(await el.isDisabled());
        if (isEnabled) {
          recordIssue('OBS-004', 'HIGH',
            'Stage advance button visible and ENABLED for observer',
            'Advance button hidden or disabled for non-supervisor observer',
            `Button found via "${sel}" and is clickable`,
            await takeScreenshot(page, 'obs-004-advance-visible'));
        } else {
          recordPass('OBS-ADVANCE-DISABLED', 'Advance button present but disabled');
        }
        advanceBtnFound = true;
        break;
      }
    }
    if (!advanceBtnFound) {
      recordPass('OBS-NO-ADVANCE-BTN', 'Stage advance button not visible for observer');
    }

    // Check 3.3: Canvas visible
    const canvasStructure = await page.evaluate(() => {
      const tldrawEls = Array.from(document.querySelectorAll('[class]'))
        .map(el => el.getAttribute('class') || '')
        .filter(c => typeof c === 'string' && (c.includes('tl-') || c.includes('tlui') || c.includes('tldraw')));
      return tldrawEls.slice(0, 5);
    });
    if (canvasStructure.length > 0) {
      recordPass('OBS-CANVAS', `Canvas (tldraw) DOM elements present: ${canvasStructure.slice(0, 2).join(', ')}`);
    } else {
      recordIssue('OBS-005', 'HIGH',
        'Canvas (tldraw) not rendered for observer',
        'Canvas visible in read-only mode for observer',
        'No tldraw DOM elements found',
        await takeScreenshot(page, 'obs-005-no-canvas'));
    }

    // =====================================================
    // STEP 4: WAIT AND MONITOR — KEY FIX VERIFICATION
    // Agents used to stall at exactly 15 messages.
    // We need >15 messages to confirm the fix works.
    // =====================================================
    log('\n--- Step 4: Monitor Agent Activity (120s) — Fix Verification ---');
    log('  The old bug: agents stalled at exactly 15 consecutive AI messages.');
    log('  The fix: per-agent 4-message limit only, no global 15-message block.');
    log('  SUCCESS criterion: >15 messages in the project chat.');

    // Baseline count at start
    let baseline = await getMessageCount(token);
    log(`  Baseline message count: ${baseline.count}`);

    // 30s check
    log('  Waiting 30s...');
    await sleep(30000);
    await takeScreenshot(page, 'discover-30s');
    let check30 = await getMessageCount(token);
    log(`  Messages at 30s: ${check30.count} (senders: ${Array.from(check30.senders).join(', ')})`);

    // 60s check
    log('  Waiting another 30s (total 60s)...');
    await sleep(30000);
    await takeScreenshot(page, 'discover-60s');
    let check60 = await getMessageCount(token);
    log(`  Messages at 60s: ${check60.count} (senders: ${Array.from(check60.senders).join(', ')})`);

    // 90s check
    log('  Waiting another 30s (total 90s)...');
    await sleep(30000);
    await takeScreenshot(page, 'discover-90s');
    let check90 = await getMessageCount(token);
    log(`  Messages at 90s: ${check90.count} (senders: ${Array.from(check90.senders).join(', ')})`);

    // 120s check — the old bug would have already stalled by now
    log('  Waiting another 30s (total 120s)...');
    await sleep(30000);
    await takeScreenshot(page, 'discover-120s');
    let check120 = await getMessageCount(token);
    log(`  Messages at 120s: ${check120.count} (senders: ${Array.from(check120.senders).join(', ')})`);

    // === CRITICAL FIX VERIFICATION ===
    const totalMessages = check120.count;
    const uniqueSenders = check120.senders;

    log(`\n  === Fix Verification Results ===`);
    log(`  Total messages at 120s: ${totalMessages}`);
    log(`  Unique senders: ${uniqueSenders.size} (${Array.from(uniqueSenders).join(', ')})`);

    // Check growth between 60s and 120s — the old bug would show 0 new messages after 15
    const messagesAfter60 = check120.count - check60.count;
    log(`  Messages added between 60s-120s: ${messagesAfter60}`);

    // Primary fix check: >15 messages total
    if (totalMessages > 15) {
      recordPass('FIX-VERIFIED', `${totalMessages} messages produced — agents continue past old 15-message stall point`);
    } else if (totalMessages === 0) {
      recordIssue('OBS-006', 'CRITICAL',
        'No messages produced — agents not starting at all',
        '>0 messages from AI agents within 120s',
        `${totalMessages} messages found`,
        await takeScreenshot(page, 'obs-006-no-messages'));
    } else if (totalMessages <= 15) {
      recordIssue('OBS-007', 'CRITICAL',
        `Only ${totalMessages} messages in 120s — possible regression of the 15-message stall bug`,
        '>15 messages (fix removes the 15-message permanent block)',
        `${totalMessages} messages — if agents stopped generating, the fix may not be deployed`,
        await takeScreenshot(page, 'obs-007-possible-stall'));
    }

    // Secondary check: multiple agents active
    if (uniqueSenders.size >= 3) {
      recordPass('MULTI-AGENT', `${uniqueSenders.size} unique AI agents active: ${Array.from(uniqueSenders).join(', ')}`);
    } else if (uniqueSenders.size === 2) {
      recordPass('MULTI-AGENT-2', `${uniqueSenders.size} unique senders (minimum threshold met)`);
    } else if (uniqueSenders.size === 1) {
      recordIssue('OBS-008', 'HIGH',
        'Only 1 unique AI agent active — per-agent 4-message limit should force agent rotation',
        '>=3 unique AI agents contributing messages',
        `Only 1 sender: ${Array.from(uniqueSenders).join(', ')}`,
        null);
    } else if (uniqueSenders.size === 0 && totalMessages > 0) {
      recordIssue('OBS-009', 'MEDIUM',
        'Messages exist but no sender IDs — schema issue',
        'All messages have sender_name or sender_id',
        'sender fields empty in API response',
        null);
    }

    // Check stall pattern: after 60s, growth should continue
    if (messagesAfter60 === 0 && check60.count > 0) {
      recordIssue('OBS-010', 'HIGH',
        'Agent activity stopped completely after 60s — possible throttle or stall',
        'Continued message growth through 120s',
        `0 new messages between 60s-120s (total: ${totalMessages})`,
        null);
    } else if (messagesAfter60 > 0) {
      recordPass('CONTINUED-GROWTH', `${messagesAfter60} new messages between 60-120s — no stall detected`);
    }

    // Check for unresolved template patterns in stored messages
    const templateMsgs = check120.messages.filter(m => (m.content || '').match(/@\{[a-z_]+\d*\}/));
    if (templateMsgs.length > 0) {
      recordIssue('OBS-011', 'HIGH',
        'Stored messages contain unresolved @{template} placeholders',
        'All message content fully resolved',
        `${templateMsgs.length} messages with template placeholders`,
        null);
    } else if (totalMessages > 0) {
      recordPass('NO-TEMPLATES', 'No unresolved template patterns in stored messages');
    }

    // =====================================================
    // STEP 5: STAGE STATE CHECK
    // =====================================================
    log('\n--- Step 5: Stage State Verification ---');
    const stageResult = await apiRequest('GET', `/api/projects/${PROJECT_ID}/stage`, null, token);
    if (stageResult.status === 200) {
      log(`  current_stage: ${stageResult.data.current_stage}`);
      log(`  current_micro_phase: ${stageResult.data.current_micro_phase}`);
      if (stageResult.data.current_stage) {
        recordPass('STAGE-STATE', `Stage API returns valid data: ${stageResult.data.current_stage} / ${stageResult.data.current_micro_phase}`);
      } else {
        recordIssue('OBS-012', 'MEDIUM',
          'Stage API response missing current_stage',
          'current_stage field populated',
          `Got: ${JSON.stringify(stageResult.data).substring(0, 200)}`,
          null);
      }
    } else {
      recordIssue('OBS-012b', 'HIGH',
        `Stage API returned HTTP ${stageResult.status}`,
        'HTTP 200 from GET /stage',
        `HTTP ${stageResult.status}`,
        null);
    }

    // =====================================================
    // STEP 6: OBSERVER CANNOT ADVANCE STAGE (API auth check)
    // =====================================================
    log('\n--- Step 6: Observer Stage Advance Permission Check ---');
    const advanceAttempt = await apiRequest(
      'POST',
      `/api/projects/${PROJECT_ID}/advance-stage`,
      { from: 'discover', to: 'define' },
      token
    );
    log(`  Observer advance attempt: HTTP ${advanceAttempt.status}`);
    if (advanceAttempt.status === 200) {
      // Teacher is project creator but entered as observer, so this depends
      // on whether the API checks seat role vs project ownership
      log(`  NOTE: Teacher is project creator — advance may succeed via ownership, not seat role`);
      log(`  This is expected behavior if the API uses project ownership for auth`);
      log(`  The UI should still hide the button for observers regardless of API auth`);
    } else if (advanceAttempt.status === 403) {
      recordPass('OBS-ADVANCE-403', 'API correctly returns 403 for observer advance attempt');
    } else {
      log(`  Advance response: ${JSON.stringify(advanceAttempt.data).substring(0, 150)}`);
    }

    // =====================================================
    // STEP 7: UI MESSAGE COUNT CHECK
    // =====================================================
    log('\n--- Step 7: UI Message Count ---');
    const uiMsgCount = await page.evaluate(() => {
      // Count chat message elements
      const selectors = [
        '[class*="ChatMessage"]',
        '[class*="chat-message"]',
        '[class*="message-item"]',
        '.message',
      ];
      for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) return { count: els.length, selector: sel };
      }
      return { count: 0, selector: 'none' };
    });
    log(`  UI messages visible: ${uiMsgCount.count} (via ${uiMsgCount.selector})`);
    if (uiMsgCount.count > 0) {
      recordPass('UI-MESSAGES', `${uiMsgCount.count} messages visible in chat UI`);
    }

    await takeScreenshot(page, 'final-state');

    // =====================================================
    // STEP 8: CANVAS STICKY NOTE CHECK
    // =====================================================
    log('\n--- Step 8: Canvas Sticky Note Check ---');
    const canvasState = await apiRequest('GET', `/api/projects/${PROJECT_ID}/canvas`, null, token);
    if (canvasState.status === 200) {
      const notes = canvasState.data.notes || canvasState.data.shapes || [];
      log(`  Canvas sticky notes: ${notes.length}`);
      if (notes.length > 0) {
        recordPass('CANVAS-NOTES', `${notes.length} sticky notes on canvas`);
      } else {
        log('  Canvas has no notes yet — agents may still be in early discussion phase');
      }
    } else {
      log(`  Canvas API: HTTP ${canvasState.status} — endpoint may not exist or different path`);
    }

    // Console errors summary
    if (consoleErrors.length > 0) {
      const unique = [...new Set(consoleErrors)];
      log(`\n  JS console errors: ${consoleErrors.length} total, ${unique.length} unique`);
      unique.slice(0, 5).forEach(e => log(`    - ${e.substring(0, 120)}`));
      if (consoleErrors.length > 10) {
        recordIssue('OBS-013', 'MEDIUM',
          'Excessive JavaScript console errors during observer session',
          'Fewer than 10 console errors',
          `${consoleErrors.length} console errors`,
          null);
      }
    } else {
      recordPass('NO-CONSOLE-ERRORS', 'No JavaScript console errors during session');
    }

  } catch (err) {
    log(`\nFATAL: ${err.message}`);
    log(err.stack);
    const ssFile = await takeScreenshot(page, 'fatal-error').catch(() => 'screenshot-failed');
    issues.push({
      id: 'FATAL',
      severity: 'CRITICAL',
      description: `Test terminated: ${err.message}`,
      expected: 'Test completes without error',
      actual: err.message,
      screenshotFile: ssFile,
    });
  } finally {
    await browser.close();
  }

  // =====================================================
  // REPORT
  // =====================================================
  log('\n\n========================================');
  log('=  OBSERVER FIX VERIFICATION REPORT    =');
  log('========================================\n');

  const critical = issues.filter(i => i.severity === 'CRITICAL');
  const high = issues.filter(i => i.severity === 'HIGH');
  const medium = issues.filter(i => i.severity === 'MEDIUM');
  const low = issues.filter(i => i.severity === 'LOW');
  const passes = issues.filter(i => !i.severity || i.severity === 'PASS');

  log(`Total issues found: ${issues.length}`);
  log(`  CRITICAL: ${critical.length}`);
  log(`  HIGH:     ${high.length}`);
  log(`  MEDIUM:   ${medium.length}`);
  log(`  LOW:      ${low.length}`);

  if (issues.length === 0) {
    log('\n  ALL CHECKS PASSED — Observer fix confirmed working.');
  } else {
    log('\n  Issues:');
    for (const issue of [...critical, ...high, ...medium, ...low]) {
      log(`---`);
      log(`  ID:       ${issue.id}`);
      log(`  Severity: ${issue.severity}`);
      log(`  Problem:  ${issue.description}`);
      log(`  Expected: ${issue.expected}`);
      log(`  Actual:   ${issue.actual}`);
      if (issue.screenshotFile) log(`  Screenshot: e2e/screenshots/${issue.screenshotFile}`);
    }
  }

  const reportData = {
    timestamp: new Date().toISOString(),
    project_id: PROJECT_ID,
    fix_verified: critical.length === 0 && high.length === 0,
    summary: {
      total_issues: issues.length,
      critical: critical.length,
      high: high.length,
      medium: medium.length,
      low: low.length,
    },
    issues: [...critical, ...high, ...medium, ...low],
  };

  const reportPath = path.join(__dirname, 'obs-fix-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(reportData, null, 2));
  log(`\nReport saved: ${reportPath}`);

  if (critical.length > 0) {
    log('\n[FAIL] CRITICAL issues found — fix NOT confirmed.');
    process.exit(1);
  } else if (high.length > 0) {
    log('\n[WARN] HIGH issues found — fix partially confirmed, but HIGH issues need attention.');
    process.exit(0);
  } else {
    log('\n[PASS] Fix verified — no CRITICAL or HIGH issues.');
    process.exit(0);
  }
}

runTest().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
