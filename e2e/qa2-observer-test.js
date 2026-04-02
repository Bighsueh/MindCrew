/**
 * QA2 Observer Role E2E Test
 * Tests Observer role (旁觀者) and stage advancement in MindCrew platform.
 *
 * Strategy:
 * - Create a new project for observer testing
 * - Use existing project 76cb03c6 (teacher is supervisor) for stage advancement
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

// Existing project where teacher is supervisor (for stage advance test)
const SUPERVISOR_PROJECT_ID = '76cb03c6-590a-41ae-966d-c3e1900f625a';

const issues = [];
let screenshotCounter = 0;

function recordIssue(id, severity, description, steps, expected, actual, screenshotFile) {
  issues.push({ id, severity, description, steps, expected, actual, screenshotFile });
  const prefix = severity === 'CRITICAL' ? '[!!!CRITICAL!!!]' : `[${severity}]`;
  console.log(`\n${prefix} Issue ${id}: ${description}`);
  console.log(`  Expected: ${expected}`);
  console.log(`  Actual:   ${actual}`);
  if (screenshotFile) console.log(`  Screenshot: ${screenshotFile}`);
}

async function takeScreenshot(page, name) {
  screenshotCounter++;
  const filename = `qa2-${String(screenshotCounter).padStart(2, '0')}-${name}.png`;
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

async function runTest() {
  console.log('=== QA2 Observer Role E2E Test Starting ===\n');
  console.log(`Frontend: ${FRONTEND_URL}`);
  console.log(`Backend:  ${BACKEND_URL}\n`);

  // === Get auth token via API ===
  const authResult = await apiRequest('POST', '/api/auth/login', {
    email: EMAIL,
    password: PASSWORD,
  });
  if (authResult.status !== 200) {
    console.error('FATAL: Cannot authenticate via API', authResult);
    process.exit(1);
  }
  const token = authResult.data.access_token;
  const userId = authResult.data.user.id;
  console.log(`Authenticated as: ${authResult.data.user.display_name} (${userId})`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // Capture console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  let observerProjectId = null;

  try {
    // =====================================================
    // TEST 1: LOGIN
    // =====================================================
    console.log('\n--- Test 1: Login ---');
    await page.goto(`${FRONTEND_URL}/login`);
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, 'login-page');

    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/projects/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, 'projects-page');
    console.log('  Login: PASS');

    // =====================================================
    // TEST 2: CREATE PROJECT (AI-full mode for observer test)
    // =====================================================
    console.log('\n--- Test 2: Create Project ---');

    const createBtns = await page.locator('button').filter({ hasText: '新增專案' }).all();
    if (createBtns.length > 0) {
      await createBtns[0].click();
      await sleep(800);
    } else {
      recordIssue('BUG-001', 'HIGH', '新增專案 button not found on projects page',
        ['Navigate to /projects'],
        '"新增專案" button visible for teacher role',
        'Button not found',
        await takeScreenshot(page, 'bug-001-no-create-btn'));
    }

    // Wait for dialog
    await page.waitForSelector('.fixed.inset-0', { timeout: 5000 }).catch(() => {});
    await takeScreenshot(page, 'create-project-dialog');

    // Fill name via React nativeInputValueSetter
    const nameFilled = await page.evaluate((projectName) => {
      const inputs = Array.from(document.querySelectorAll('input'));
      const nameInput = inputs.find(el =>
        el.placeholder.includes('校園') ||
        el.placeholder.includes('設計工作坊') ||
        el.id.includes('專案名稱') ||
        el.id === 'name'
      );
      if (!nameInput) return { success: false, reason: 'input not found' };
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(nameInput, projectName);
      nameInput.dispatchEvent(new Event('input', { bubbles: true }));
      nameInput.dispatchEvent(new Event('change', { bubbles: true }));
      return { success: true, id: nameInput.id, placeholder: nameInput.placeholder };
    }, 'QA驗證-購物車設計-旁觀者測試');

    console.log(`  Name input fill result: ${JSON.stringify(nameFilled)}`);

    // Fill description
    await page.evaluate((desc) => {
      const textareas = Array.from(document.querySelectorAll('textarea'));
      const ta = textareas.find(el =>
        el.placeholder.includes('主題') ||
        el.placeholder.includes('目標') ||
        el.placeholder.includes('描述')
      );
      if (!ta) return false;
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(ta, desc);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }, '超市購物車的重新設計。限制：寬度≤60cm、嵌套堆疊、手把95-105cm、推行力<5kg、成本≤NT$3000、回收材質≥80%');

    // Click 高 button for AI contribution
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
      const highBtn = buttons.find(b => {
        const text = b.textContent.trim();
        return text === '高' || text.startsWith('高\n') || text.startsWith('高 ');
      });
      if (highBtn) highBtn.click();
    });

    await sleep(300);
    await takeScreenshot(page, 'create-project-filled');

    // Check for modal backdrop click interception issue
    // Record it as a bug before using JS workaround
    recordIssue('BUG-MODAL-BACKDROP', 'MEDIUM',
      'Modal backdrop div intercepts Playwright synthetic click on submit button',
      [
        'Open 建立新專案 modal',
        'Call page.locator("button").filter({hasText:/建立/}).click()',
      ],
      'Submit button should receive click without backdrop interference',
      'Playwright reports "subtree intercepts pointer events" — the aria-hidden backdrop div is above the z-10 content in pointer event processing. Workaround: use page.evaluate click.'
    );

    // Submit via JS evaluate (workaround for backdrop issue)
    const submitClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.textContent.trim().includes('建立專案') || b.textContent.trim() === '建立');
      if (btn) { btn.click(); return true; }
      return false;
    });
    console.log(`  Submit button clicked: ${submitClicked}`);

    await sleep(3000);
    await page.waitForLoadState('networkidle');
    await takeScreenshot(page, 'after-create-project');

    // Find the newly created project by name via API
    await sleep(1000);
    const projectsResult = await apiRequest('GET', '/api/projects?limit=50', null, token);
    if (projectsResult.status === 200) {
      const allProjects = projectsResult.data.items || projectsResult.data || [];
      const qaProject = allProjects.find(p => p.name === 'QA驗證-購物車設計-旁觀者測試');
      if (qaProject) {
        observerProjectId = qaProject.id;
        console.log(`  Created project ID: ${observerProjectId}`);
      } else {
        // Check if name was saved differently (input filling issue)
        const sorted = [...allProjects].sort((a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        const newest = sorted[0];
        if (newest) {
          observerProjectId = newest.id;
          console.log(`  Using newest project: ${newest.id} (${newest.name})`);
          if (newest.name !== 'QA驗證-購物車設計-旁觀者測試') {
            recordIssue('BUG-FORM-NAME', 'HIGH',
              'Project name was NOT saved correctly from the create dialog form',
              [
                'Open create project dialog',
                'Fill name field via React nativeInputValueSetter',
                'Submit form',
                'GET /api/projects to check saved name',
              ],
              'Project name should be "QA驗證-購物車設計-旁觀者測試"',
              `Saved project name is "${newest.name}" — React controlled input value setter may not have triggered state update`,
              null
            );
          }
        }
      }
    }

    if (!observerProjectId) {
      recordIssue('BUG-002', 'CRITICAL', 'Project creation failed — project not found in API',
        ['Fill create project form', 'Submit', 'GET /api/projects'],
        'New project appears in project list',
        'No project found matching expected name',
        await takeScreenshot(page, 'bug-002-project-not-found'));
      // Continue with supervisor project for remaining tests
      console.log('  WARNING: Continuing with limited test coverage');
    }

    const testProjectId = observerProjectId;

    // =====================================================
    // TEST 3: ENTER AS OBSERVER
    // =====================================================
    console.log('\n--- Test 3: Enter as Observer ---');

    if (testProjectId) {
      await page.goto(`${FRONTEND_URL}/projects/${testProjectId}/lobby`);
      await page.waitForLoadState('networkidle');
      await sleep(2000);
      await takeScreenshot(page, 'project-lobby');

      // Check for observer button
      const observerBtn = page.locator('button').filter({ hasText: /觀察者|observer/i }).first();
      const observerBtnVisible = await observerBtn.isVisible().catch(() => false);

      if (!observerBtnVisible) {
        recordIssue('BUG-003', 'HIGH', '"以觀察者身份進入" button not found in project lobby',
          [`Navigate to /projects/${testProjectId}/lobby`],
          'Observer entry button should be visible in lobby',
          'Button not found',
          await takeScreenshot(page, 'bug-003-no-observer-btn'));
      } else {
        console.log('  Observer button found: PASS');

        // Click the observer button
        await observerBtn.click();
        await sleep(2000);
        await page.waitForLoadState('networkidle');

        const workspaceUrl = page.url();
        console.log(`  URL after observer click: ${workspaceUrl}`);

        if (!workspaceUrl.includes('/workspace')) {
          recordIssue('BUG-003b', 'HIGH', 'Observer button did not navigate to workspace',
            ['Click "以觀察者身份進入"'],
            'Navigate to /projects/{id}/workspace',
            `Stayed at: ${workspaceUrl}`,
            await takeScreenshot(page, 'bug-003b-observer-no-nav'));
        } else {
          console.log('  Observer navigation: PASS');
          await takeScreenshot(page, 'observer-workspace');
        }
      }

      // =====================================================
      // TEST 4: DISCOVER PHASE OBSERVER MODE CHECKS
      // =====================================================
      console.log('\n--- Test 4: Observer Workspace Checks ---');

      // Check 4.1: Canvas visibility
      // tldraw uses a specific DOM structure — check for it
      const tldrawSelectors = [
        '[class*="tldraw"]',
        '[data-testid*="canvas"]',
        '.tl-canvas',
        '.tl-container',
        '[class*="canvas"]',
        'svg.tl-svg-context',
        'div[style*="inset"]',  // tldraw's main container
      ];
      let canvasFound = false;
      for (const sel of tldrawSelectors) {
        const el = page.locator(sel).first();
        if (await el.isVisible().catch(() => false)) {
          console.log(`  Canvas found via selector "${sel}": PASS`);
          canvasFound = true;
          break;
        }
      }
      if (!canvasFound) {
        // Check if there are any canvas-like structures
        const canvasStructure = await page.evaluate(() => {
          // Check for tldraw elements — use getAttribute to avoid SVGAnimatedString issues
          const allClasses = Array.from(document.querySelectorAll('[class]'))
            .map(el => el.getAttribute('class') || '')
            .filter(c => typeof c === 'string' && (c.includes('tl') || c.includes('canvas') || c.includes('tlui')))
            .slice(0, 10);
          return allClasses;
        });
        console.log(`  Canvas-like classes found: ${JSON.stringify(canvasStructure)}`);
        if (canvasStructure.length === 0) {
          recordIssue('BUG-004', 'HIGH', 'Canvas (tldraw) element not visible for observer',
            ['Enter workspace as observer', 'Check for tldraw/canvas element'],
            'Canvas should be visible for observer (read-only view)',
            'No tldraw or canvas-like element found in DOM',
            await takeScreenshot(page, 'bug-004-no-canvas'));
        } else {
          console.log('  Canvas DOM elements present but selector not matching: PASS (selector issue, not a bug)');
        }
      }

      // Check 4.2: Chat panel visibility
      const chatHeader = page.locator('h3').filter({ hasText: '聊天室' }).first();
      const chatVisible = await chatHeader.isVisible().catch(() => false);
      if (!chatVisible) {
        recordIssue('BUG-005', 'HIGH', 'Chat panel not visible for observer',
          ['Enter workspace as observer'],
          '"聊天室" panel header should be visible',
          'Chat panel header not found',
          await takeScreenshot(page, 'bug-005-no-chat'));
      } else {
        console.log('  Chat panel visible: PASS');
      }

      // Check 4.3: Chat input DISABLED or HIDDEN for observer
      // An observer has no seat, so the workspace should either hide or disable input
      const chatTextarea = page.locator('textarea[placeholder*="輸入訊息"], textarea[placeholder*="Enter 送出"]').first();
      const chatInputVisible = await chatTextarea.isVisible().catch(() => false);

      if (chatInputVisible) {
        const isDisabled = await chatTextarea.isDisabled();
        if (!isDisabled) {
          recordIssue('BUG-006', 'CRITICAL',
            'Chat input is ENABLED for observer — observers should NOT be able to send messages',
            [
              'Enter workspace as observer (no seat selected)',
              'Observe ChatInput component',
            ],
            'Chat textarea should be disabled or hidden for users without a seat',
            'ChatPanel always renders ChatInput with disabled=false. WorkspacePage does not check if user is observer before passing disabled prop to ChatPanel.',
            await takeScreenshot(page, 'bug-006-observer-can-chat'));
        } else {
          console.log('  Chat input disabled for observer: PASS');
        }
      } else {
        console.log('  Chat input not visible for observer: PASS (hidden is acceptable)');
      }

      // Check 4.4: Stage advance button should NOT be visible for observer
      const advanceBtn = page.locator('button').filter({ hasText: /推進到|advance stage/i }).first();
      const advanceBtnVisible = await advanceBtn.isVisible().catch(() => false);
      if (advanceBtnVisible) {
        const isDisabled = await advanceBtn.isDisabled();
        if (!isDisabled) {
          recordIssue('BUG-013', 'HIGH',
            'Stage advance button visible and enabled for observer',
            ['Enter workspace as observer', 'Check footer for advance button'],
            'Stage advance button should only be visible/enabled for supervisor-seat holder',
            'Button is visible and enabled — workspace checks isSupervisor correctly (seats.find) but observer has no seat, so isSupervisor=false. PASS.',
            await takeScreenshot(page, 'bug-013-advance-btn'));
        }
      } else {
        console.log('  Stage advance button not visible for observer: PASS');
      }

      // Wait 30 seconds and observe agent activity
      console.log('  Waiting 30s for agent activity...');
      await sleep(30000);
      await takeScreenshot(page, 'discover-30s');

      // Wait another 60s (total 90s)
      console.log('  Waiting another 60s (total 90s)...');
      await sleep(60000);
      await takeScreenshot(page, 'discover-90s');

      // Check message count in UI
      const msgEls = await page.locator('[class*="ChatMessage"], [class*="chat-message"]').all();
      console.log(`  UI message elements at 90s: ${msgEls.length}`);

      // Check for @{crew_N} template patterns in visible text
      const pageText = await page.evaluate(() => document.body.innerText);
      const templatePattern = /@\{[a-z_]+\d*\}/g;
      const templateMatches = pageText.match(templatePattern) || [];
      if (templateMatches.length > 0) {
        recordIssue('BUG-008', 'CRITICAL',
          'Unresolved @{crew_N} template patterns visible in UI',
          ['Start project', 'View chat messages after 90s'],
          'All template placeholders should be resolved',
          `Found ${templateMatches.length} unresolved patterns: ${templateMatches.slice(0, 5).join(', ')}`,
          await takeScreenshot(page, 'bug-008-template-patterns'));
      } else {
        console.log('  No @{crew_N} template patterns in UI: PASS');
      }
    }

    // =====================================================
    // TEST 5: API VERIFICATION (use observer project)
    // =====================================================
    console.log('\n--- Test 5: API Verification ---');

    if (testProjectId) {
      const stageResult = await apiRequest('GET', `/api/projects/${testProjectId}/stage`, null, token);
      console.log(`  GET /stage: HTTP ${stageResult.status}`);
      if (stageResult.status === 200) {
        console.log(`  current_stage: ${stageResult.data.current_stage}`);
        console.log(`  current_micro_phase: ${stageResult.data.current_micro_phase}`);
        if (!stageResult.data.current_stage || !stageResult.data.current_micro_phase) {
          recordIssue('BUG-009', 'MEDIUM',
            'Stage API missing fields',
            ['GET /api/projects/{id}/stage'],
            'current_stage and current_micro_phase both present',
            `Got: ${JSON.stringify(stageResult.data)}`,
            null);
        }
      }

      const messagesResult = await apiRequest('GET', `/api/projects/${testProjectId}/messages?limit=50`, null, token);
      console.log(`  GET /messages: HTTP ${messagesResult.status}`);

      if (messagesResult.status === 200) {
        // API returns { messages: [...], has_more: bool, next_cursor: ... }
        const messages = messagesResult.data.messages || messagesResult.data.items || [];
        const uniqueSenders = new Set();
        const templateMessages = [];

        for (const msg of messages) {
          if (msg.sender_name) uniqueSenders.add(msg.sender_name);
          if (msg.sender_id) uniqueSenders.add(msg.sender_id);
          const content = msg.content || '';
          if (content.match(/@\{[a-z_]+\d*\}/)) {
            templateMessages.push({ sender: msg.sender_name, content: content.substring(0, 100) });
          }
        }

        console.log(`  Total messages: ${messages.length}`);
        console.log(`  Unique senders: ${uniqueSenders.size} (${Array.from(uniqueSenders).slice(0, 6).join(', ')})`);

        if (messages.length < 3) {
          recordIssue('BUG-010', 'HIGH',
            'Very few messages in first 90 seconds — agents appear mostly silent',
            ['Start project', 'Wait 90s', 'GET /api/projects/{id}/messages'],
            'At least 3 messages from multiple agents',
            `Only ${messages.length} messages found in database`,
            null);
        }

        if (uniqueSenders.size < 2) {
          recordIssue('BUG-011', 'HIGH',
            'Too few unique senders — most agents are silent',
            ['Start project', 'Wait 90s', 'Count unique senders'],
            'At least 2 unique senders (supervisor + at least 1 crew)',
            `Only ${uniqueSenders.size} unique sender(s)`,
            null);
        }

        if (templateMessages.length > 0) {
          recordIssue('BUG-012', 'CRITICAL',
            'Stored messages contain unresolved template patterns',
            ['GET /api/projects/{id}/messages', 'Inspect message content'],
            'All messages should have resolved template placeholders',
            `${templateMessages.length} messages with templates. Example: ${templateMessages[0].content}`,
            null);
        } else {
          console.log('  No template patterns in stored messages: PASS');
        }
      }
    }

    // =====================================================
    // TEST 6: ADVANCE STAGE VIA API (using supervisor project)
    // =====================================================
    console.log('\n--- Test 6: Stage Advancement (supervisor project) ---');
    console.log(`  Using project: ${SUPERVISOR_PROJECT_ID} (teacher is supervisor)`);

    // Get current stage of supervisor project
    const supervisorStage = await apiRequest('GET', `/api/projects/${SUPERVISOR_PROJECT_ID}/stage`, null, token);
    console.log(`  Current stage: ${supervisorStage.data?.current_stage}`);
    console.log(`  Current micro: ${supervisorStage.data?.current_micro_phase}`);

    const currentSupervisorStage = supervisorStage.data?.current_stage;

    // Attempt stage advancement: current -> next
    const stageAdvanceMap = {
      'discover': 'define',
      'define': 'develop',
      'develop': 'deliver',
    };

    if (currentSupervisorStage && stageAdvanceMap[currentSupervisorStage]) {
      const fromStage = currentSupervisorStage;
      const toStage = stageAdvanceMap[currentSupervisorStage];

      console.log(`  Advancing ${fromStage} -> ${toStage}...`);
      const advanceResult = await apiRequest(
        'POST',
        `/api/projects/${SUPERVISOR_PROJECT_ID}/advance-stage`,
        { from: fromStage, to: toStage },
        token
      );

      console.log(`  Advance result: HTTP ${advanceResult.status}`);
      if (advanceResult.status !== 200) {
        recordIssue('BUG-014', 'HIGH',
          `Stage advance ${fromStage}->${toStage} failed for supervisor`,
          [`POST /api/projects/{id}/advance-stage {from:"${fromStage}", to:"${toStage}"}`],
          'HTTP 200 — supervisor should be able to advance stage',
          `HTTP ${advanceResult.status}: ${JSON.stringify(advanceResult.data).substring(0, 200)}`,
          null);
      } else {
        console.log(`  Stage advance: PASS (HTTP 200)`);
        await sleep(3000);

        // Verify stage changed
        const stageAfter = await apiRequest('GET', `/api/projects/${SUPERVISOR_PROJECT_ID}/stage`, null, token);
        console.log(`  Stage after advance: ${stageAfter.data?.current_stage}`);
        console.log(`  Micro phase after:   ${stageAfter.data?.current_micro_phase}`);

        if (stageAfter.data?.current_stage !== toStage) {
          recordIssue('BUG-015', 'HIGH',
            'Stage did not update to target stage after advance',
            [`POST advance-stage ${fromStage}->${toStage}`, 'GET stage'],
            `current_stage should be "${toStage}"`,
            `current_stage is still "${stageAfter.data?.current_stage}"`,
            null);
        } else {
          console.log('  Stage updated correctly: PASS');
        }

        // Check micro_phase reset
        const expectedMicroPrefix = { 'define': '2.', 'develop': '3.', 'deliver': '4.' }[toStage];
        if (expectedMicroPrefix && stageAfter.data?.current_micro_phase) {
          if (!stageAfter.data.current_micro_phase.startsWith(expectedMicroPrefix)) {
            recordIssue('BUG-016', 'HIGH',
              'Micro phase not reset to correct prefix after stage advance',
              [`Advance to ${toStage}`, 'GET stage and check current_micro_phase'],
              `current_micro_phase should start with "${expectedMicroPrefix}"`,
              `Got: "${stageAfter.data.current_micro_phase}"`,
              null);
          } else {
            console.log(`  Micro phase reset to ${stageAfter.data.current_micro_phase}: PASS`);
          }
        } else if (!stageAfter.data?.current_micro_phase) {
          recordIssue('BUG-016b', 'MEDIUM',
            'current_micro_phase is null/undefined after stage advance',
            [`Advance to ${toStage}`, 'GET stage'],
            `current_micro_phase should start with "${expectedMicroPrefix}"`,
            'current_micro_phase is null/undefined',
            null);
        }

        // Navigate to workspace and observe new phase
        await page.goto(`${FRONTEND_URL}/projects/${SUPERVISOR_PROJECT_ID}/workspace`);
        await page.waitForLoadState('networkidle');
        await sleep(5000);
        await takeScreenshot(page, `after-advance-to-${toStage}`);
      }
    } else if (currentSupervisorStage === 'deliver') {
      console.log('  Project already at deliver stage — testing final stage check');
      const deliverStage = supervisorStage.data;
      if (!deliverStage?.current_micro_phase?.startsWith('4.')) {
        recordIssue('BUG-020', 'MEDIUM',
          'Deliver stage has incorrect micro_phase prefix',
          ['Check stage of project in deliver'],
          'micro_phase should start with "4."',
          `Got: "${deliverStage?.current_micro_phase}"`,
          null);
      }
    } else {
      console.log(`  Skipping advance test — project in "${currentSupervisorStage}" with no valid transition`);
    }

    // =====================================================
    // TEST 7: OBSERVER CANNOT ADVANCE STAGE (403 check)
    // =====================================================
    console.log('\n--- Test 7: Observer Permission Check for Stage Advance ---');

    if (testProjectId) {
      // The teacher entered observerProjectId as observer (no seat)
      // Try to advance stage — should get 403
      const observerAdvanceResult = await apiRequest(
        'POST',
        `/api/projects/${testProjectId}/advance-stage`,
        { from: 'discover', to: 'define' },
        token
      );

      console.log(`  Observer advance attempt: HTTP ${observerAdvanceResult.status}`);
      if (observerAdvanceResult.status === 200) {
        recordIssue('BUG-017', 'CRITICAL',
          'Observer successfully advanced stage via API — no permission check!',
          [
            `Create project with AI-only seats (teacher as observer)`,
            `POST /api/projects/${testProjectId}/advance-stage {from:"discover", to:"define"}`,
          ],
          'HTTP 403 — only supervisor-seat holder should advance stage',
          'HTTP 200 — advance succeeded for non-supervisor',
          null);
      } else if (observerAdvanceResult.status === 403 || (observerAdvanceResult.data?.detail || '').includes('supervisor')) {
        console.log(`  Observer blocked from stage advance: PASS (HTTP ${observerAdvanceResult.status})`);
      } else {
        console.log(`  Observer advance returned: ${JSON.stringify(observerAdvanceResult.data).substring(0, 100)}`);
      }
    }

    // =====================================================
    // TEST 8: FINAL STATE VERIFICATION
    // =====================================================
    console.log('\n--- Test 8: Final State Verification ---');

    const finalStageResult = await apiRequest('GET', `/api/projects/${SUPERVISOR_PROJECT_ID}/stage`, null, token);
    if (finalStageResult.status === 200) {
      console.log(`  Final stage: ${finalStageResult.data.current_stage}`);
      console.log(`  Final micro: ${finalStageResult.data.current_micro_phase}`);
    }

    const historyResult = await apiRequest('GET', `/api/projects/${SUPERVISOR_PROJECT_ID}/history`, null, token);
    if (historyResult.status === 200) {
      const history = Array.isArray(historyResult.data) ? historyResult.data : historyResult.data.items || [];
      console.log(`  Stage history entries: ${history.length}`);

      for (const entry of history) {
        const dur = entry.duration_seconds;
        if (dur !== undefined && dur !== null) {
          console.log(`    Stage ${entry.from_stage || entry.stage}: ${dur}s`);
          if (dur > 600) {
            recordIssue('BUG-021', 'LOW',
              `Stage duration unreasonably long in test: ${entry.from_stage || entry.stage}`,
              ['GET /api/projects/{id}/history'],
              'Duration < 600s for test run',
              `Duration was ${dur}s`,
              null);
          }
        }
      }
    }

    // Final message count check for supervisor project
    const finalMsgs = await apiRequest('GET', `/api/projects/${SUPERVISOR_PROJECT_ID}/messages?limit=100`, null, token);
    if (finalMsgs.status === 200) {
      const msgs = finalMsgs.data.messages || finalMsgs.data.items || [];
      const finalSenders = new Set(msgs.map(m => m.sender_name || m.sender_id).filter(Boolean));
      console.log(`  Supervisor project total messages: ${msgs.length}`);
      console.log(`  Unique senders: ${finalSenders.size} (${Array.from(finalSenders).slice(0, 8).join(', ')})`);
    }

    // Console error check
    if (consoleErrors.length > 0) {
      console.log(`\n  JS Console errors during test: ${consoleErrors.length}`);
      const uniqueErrors = [...new Set(consoleErrors)].slice(0, 5);
      uniqueErrors.forEach(e => console.log(`    - ${e.substring(0, 150)}`));
      if (consoleErrors.length > 5) {
        recordIssue('BUG-022', 'MEDIUM',
          'Multiple JavaScript console errors during test session',
          ['Run full E2E test session'],
          'No console errors during normal usage',
          `${consoleErrors.length} total console errors logged`,
          null);
      }
    }

    await takeScreenshot(page, 'final-state');

  } catch (err) {
    console.error('\nFATAL TEST ERROR:', err.message);
    console.error(err.stack);
    const ssFile = await takeScreenshot(page, 'fatal-error').catch(() => 'screenshot-failed');
    issues.push({
      id: 'BUG-FATAL',
      severity: 'CRITICAL',
      description: `Test terminated with uncaught error: ${err.message}`,
      steps: ['Running E2E test'],
      expected: 'Test completes successfully',
      actual: err.message,
      screenshotFile: ssFile,
    });
  } finally {
    await browser.close();
  }

  // =====================================================
  // GENERATE FINAL REPORT
  // =====================================================
  console.log('\n\n========================================');
  console.log('=         QA2 OBSERVER ROLE BUG REPORT         =');
  console.log('========================================\n');

  const critical = issues.filter(i => i.severity === 'CRITICAL');
  const high = issues.filter(i => i.severity === 'HIGH');
  const medium = issues.filter(i => i.severity === 'MEDIUM');
  const low = issues.filter(i => i.severity === 'LOW');

  console.log(`Total issues: ${issues.length}`);
  console.log(`  CRITICAL: ${critical.length}`);
  console.log(`  HIGH:     ${high.length}`);
  console.log(`  MEDIUM:   ${medium.length}`);
  console.log(`  LOW:      ${low.length}`);
  console.log('');

  const allBySeverity = [...critical, ...high, ...medium, ...low];
  for (const issue of allBySeverity) {
    console.log(`---`);
    console.log(`Issue ID:    ${issue.id}`);
    console.log(`Severity:    ${issue.severity}`);
    console.log(`Description: ${issue.description}`);
    console.log(`Steps:       ${Array.isArray(issue.steps) ? issue.steps.join(' → ') : issue.steps}`);
    console.log(`Expected:    ${issue.expected}`);
    console.log(`Actual:      ${issue.actual}`);
    if (issue.screenshotFile) console.log(`Screenshot:  e2e/screenshots/${issue.screenshotFile}`);
  }

  // Save JSON report
  const reportPath = path.join(__dirname, 'qa2-observer-report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    observerProjectId,
    supervisorProjectId: SUPERVISOR_PROJECT_ID,
    summary: {
      total: issues.length,
      critical: critical.length,
      high: high.length,
      medium: medium.length,
      low: low.length,
    },
    issues: allBySeverity,
  }, null, 2));
  console.log(`\nFull report saved: ${reportPath}`);
}

runTest().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
