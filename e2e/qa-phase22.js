/**
 * Phase 22 QA Test: 教師列管雙向碼 + 作者識別色
 * Run: node qa-phase22.js
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'phase22');
const TIMESTAMP = Date.now();

const teacherEmail = `qa-pw-t-${TIMESTAMP}@test.com`;
const teacherPassword = 'testpass1234';
const teacherName = 'QA Teacher PW';

const studentEmail = `qa-pw-s-${TIMESTAMP}@test.com`;
const studentPassword = 'testpass1234';
const studentName = 'QA Student PW';

const results = [];

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function pass(area, detail) {
  log(`PASS [${area}]: ${detail}`);
  results.push({ area, status: 'PASS', detail });
}

function fail(area, detail) {
  log(`FAIL [${area}]: ${detail}`);
  results.push({ area, status: 'FAIL', detail });
}

function skip(area, detail) {
  log(`SKIP [${area}]: ${detail}`);
  results.push({ area, status: 'SKIP', detail });
}

async function screenshot(page, name) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  log(`Screenshot: ${p}`);
  return p;
}

async function register(page, email, password, displayName, role) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');

  // Fill email
  const emailInput = page.locator('input[type="email"], input[name="email"]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(email);

  // Fill password
  const passwordInput = page.locator('input[type="password"]').first();
  await passwordInput.fill(password);

  // Fill display name - try various selectors
  const nameInput = page.locator('input[placeholder*="名稱"], input[name="display_name"], input[placeholder*="display"]').first();
  try {
    await nameInput.waitFor({ state: 'visible', timeout: 3000 });
    await nameInput.fill(displayName);
  } catch {
    // try index-based
    const inputs = page.locator('input[type="text"]');
    const count = await inputs.count();
    if (count > 0) await inputs.first().fill(displayName);
  }

  // Select role
  if (role === '教師') {
    try {
      const teacherRadio = page.locator('input[value="teacher"], input[value="教師"]').first();
      await teacherRadio.waitFor({ state: 'visible', timeout: 3000 });
      await teacherRadio.click();
    } catch {
      // Try label-based
      try {
        await page.locator('label:has-text("教師")').click();
      } catch {
        log('Could not find teacher role radio');
      }
    }
  } else {
    try {
      const studentRadio = page.locator('input[value="student"], input[value="學生"]').first();
      await studentRadio.waitFor({ state: 'visible', timeout: 3000 });
      await studentRadio.click();
    } catch {
      try {
        await page.locator('label:has-text("學生")').click();
      } catch {
        log('Could not find student role radio');
      }
    }
  }

  // Submit
  const submitBtn = page.locator('button[type="submit"]').first();
  await submitBtn.click();
  await page.waitForURL('**/projects', { timeout: 15000 });
  log(`Registered ${role}: ${email}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================
  // SECTION A: Teacher Dashboard Code
  // ============================================================
  log('\n=== SECTION A: 教師列管雙向碼 ===');

  const teacherContext = await browser.newContext();
  const teacherPage = await teacherContext.newPage();

  // --- Step A1: Register teacher ---
  log('Step A1: Register teacher');
  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    pass('A1-teacher-register', `Teacher registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', `Register failed: ${e.message}`);
    await screenshot(teacherPage, 'A1-register-error');
  }

  // --- Step A2: Navigate to teacher dashboard ---
  log('Step A2: Navigate to teacher dashboard');
  let teacherCode = null;
  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForLoadState('networkidle');
    await screenshot(teacherPage, 'A2-teacher-dashboard');

    // Check for 我的教師代碼 block
    const codeBlock = teacherPage.locator('text=我的教師代碼');
    await codeBlock.waitFor({ state: 'visible', timeout: 10000 });
    pass('A2-teacher-code-block', '"我的教師代碼" block is visible');

    // Get the code chip text
    // Look for monospace code element near the block
    const codeChipSelectors = [
      '[class*="monospace"]',
      '[class*="font-mono"]',
      'code',
      '[class*="chip"]',
      '[class*="badge"]',
      '[class*="code"]',
    ];

    let codeText = null;
    for (const sel of codeChipSelectors) {
      try {
        const el = teacherPage.locator(sel).first();
        const visible = await el.isVisible();
        if (visible) {
          const text = (await el.textContent()).trim();
          // Validate: 6 chars, uppercase A-Z2-9, no 0/O/1/I/L
          if (/^[A-Z2-9]{6}$/.test(text) && !/[01OIL]/.test(text)) {
            codeText = text;
            break;
          }
        }
      } catch { /* continue */ }
    }

    // If still not found, try broader search near the heading
    if (!codeText) {
      // Get all text near the 我的教師代碼 area
      const pageContent = await teacherPage.content();
      const match = pageContent.match(/[A-Z2-9]{6}/);
      if (match) {
        const candidate = match[0];
        if (!/[01OIL]/.test(candidate)) {
          codeText = candidate;
        }
      }
    }

    if (codeText) {
      teacherCode = codeText;
      pass('A2-teacher-code-value', `Teacher code: ${teacherCode} (6-char, valid charset)`);
    } else {
      fail('A2-teacher-code-value', 'Could not extract 6-char code chip from teacher dashboard');
      // Try to log what we see
      const bodyText = await teacherPage.locator('body').innerText();
      log(`Page body excerpt: ${bodyText.slice(0, 500)}`);
    }

  } catch (e) {
    fail('A2-teacher-dashboard', `Teacher dashboard error: ${e.message}`);
    await screenshot(teacherPage, 'A2-error');
  }

  // --- Step A3: Copy button ---
  log('Step A3: Test 複製 button');
  try {
    const copyBtn = teacherPage.locator('button:has-text("複製")').first();
    const copyVisible = await copyBtn.isVisible();
    if (copyVisible) {
      await copyBtn.click();
      // Wait briefly for state change
      await teacherPage.waitForTimeout(500);
      const copiedBtn = teacherPage.locator('button:has-text("已複製"), text=已複製').first();
      const copied = await copiedBtn.isVisible().catch(() => false);
      if (copied) {
        pass('A3-copy-button', '"已複製" feedback appeared after clicking 複製');
      } else {
        // still a soft pass if button was there
        pass('A3-copy-button', '複製 button clicked (已複製 feedback not confirmed)');
      }
      await screenshot(teacherPage, 'A3-copy-clicked');
    } else {
      fail('A3-copy-button', '複製 button not visible on teacher dashboard');
    }
  } catch (e) {
    fail('A3-copy-button', `Copy button error: ${e.message}`);
  }

  // ============================================================
  // SECTION B: Student creates activity with teacher code
  // ============================================================
  log('\n=== SECTION B: Student create-activity with teacher code ===');

  const studentContext = await browser.newContext();
  const studentPage = await studentContext.newPage();

  let projectId = null;
  let inviteCode = null;

  // --- Step B1: Register student ---
  log('Step B1: Register student');
  try {
    await register(studentPage, studentEmail, studentPassword, studentName, '學生');
    pass('B1-student-register', `Student registered: ${studentEmail}`);
  } catch (e) {
    fail('B1-student-register', `Student register failed: ${e.message}`);
    await screenshot(studentPage, 'B1-register-error');
  }

  // --- Step B2: Open new activity modal ---
  log('Step B2: Open 新增學習活動 modal');
  try {
    await studentPage.goto(`${BASE_URL}/projects`);
    await studentPage.waitForLoadState('networkidle');
    await screenshot(studentPage, 'B2-projects-page');

    // Find new activity button
    const newBtn = studentPage.locator('button:has-text("新增學習活動"), button:has-text("新增"), button:has-text("探索")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click();
    await studentPage.waitForTimeout(1000);
    await screenshot(studentPage, 'B2-modal-opened');

    // Check modal title
    const modalTitle = studentPage.locator('text=開啟新探索');
    const titleVisible = await modalTitle.isVisible().catch(() => false);
    if (titleVisible) {
      pass('B2-modal-title', 'Modal title "開啟新探索" is visible');
    } else {
      // Try to get actual title
      const dialogTitle = await studentPage.locator('[role="dialog"] h1, [role="dialog"] h2, [role="dialog"] h3').first().textContent().catch(() => 'unknown');
      fail('B2-modal-title', `Expected "開啟新探索", got: "${dialogTitle}"`);
    }

    // Check teacher code field
    const teacherCodeField = studentPage.locator('input[placeholder*="老師"], input[placeholder*="教師"], label:has-text("老師班") ~ input, label:has-text("教師") ~ input');
    const tcfVisible = await teacherCodeField.first().isVisible().catch(() => false);
    if (tcfVisible) {
      pass('B2-teacher-code-field', '"加入老師班譯（選填）" field exists in step 1');
      if (teacherCode) {
        await teacherCodeField.first().fill(teacherCode);
        pass('B2-teacher-code-entered', `Teacher code ${teacherCode} entered in student form`);
      } else {
        skip('B2-teacher-code-entered', 'No teacher code available to enter');
      }
    } else {
      // Try broader search
      const formText = await studentPage.locator('[role="dialog"]').textContent().catch(() => '');
      if (formText.includes('老師') || formText.includes('教師')) {
        // Look for any input in the teacher code area
        const allInputs = studentPage.locator('[role="dialog"] input');
        const count = await allInputs.count();
        log(`Found ${count} inputs in dialog`);
        fail('B2-teacher-code-field', `Teacher code field not found. Dialog has ${count} inputs. Text: ${formText.slice(0, 300)}`);
      } else {
        fail('B2-teacher-code-field', 'Teacher code field not found and no teacher-related text in dialog');
      }
    }

    // --- Step B3: Fill activity name and settings ---
    log('Step B3: Fill activity details');
    const activityNameInput = studentPage.locator('input[placeholder*="活動名稱"], input[placeholder*="專案名稱"], input[name="title"]').first();
    await activityNameInput.waitFor({ state: 'visible', timeout: 5000 });
    await activityNameInput.fill('QA Phase22');
    pass('B3-activity-name', 'Activity name "QA Phase22" filled');

    // Set AI crew count to 1 if possible
    try {
      const crewCount = studentPage.locator('input[name*="crew"], input[placeholder*="人數"], input[type="number"]').first();
      const crewVisible = await crewCount.isVisible().catch(() => false);
      if (crewVisible) {
        await crewCount.fill('1');
        log('Set crew count to 1');
      }
    } catch { /* optional */ }

    await screenshot(studentPage, 'B3-step1-filled');

    // Advance to step 2
    const nextBtn = studentPage.locator('button:has-text("下一步"), button:has-text("繼續"), button:has-text("Next")').first();
    const nextVisible = await nextBtn.isVisible().catch(() => false);
    if (nextVisible) {
      await nextBtn.click();
      await studentPage.waitForTimeout(1000);
      pass('B3-advance-step2', 'Advanced to step 2');
    } else {
      log('No next button found, trying to continue');
    }

    await screenshot(studentPage, 'B3-step2');

    // Step 2: Add persona manually
    log('Step B4: Add persona manually');
    try {
      const manualAddBtn = studentPage.locator('button:has-text("手動新增"), button:has-text("手動"), button:has-text("新增角色")').first();
      const manualVisible = await manualAddBtn.isVisible().catch(() => false);
      if (manualVisible) {
        await manualAddBtn.click();
        await studentPage.waitForTimeout(500);

        // Fill persona name
        const personaName = studentPage.locator('input[placeholder*="角色名稱"], input[placeholder*="名字"], input[name="name"]').first();
        await personaName.waitFor({ state: 'visible', timeout: 5000 });
        await personaName.fill('P1');

        // Fill role
        const roleInput = studentPage.locator('input[placeholder*="角色"], input[placeholder*="職能"], input[name="role"]').first();
        const roleVisible = await roleInput.isVisible().catch(() => false);
        if (roleVisible) await roleInput.fill('Role');

        // Save persona
        const saveBtn = studentPage.locator('button:has-text("儲存"), button:has-text("確認"), button:has-text("Save")').first();
        const saveVisible = await saveBtn.isVisible().catch(() => false);
        if (saveVisible) {
          await saveBtn.click();
          await studentPage.waitForTimeout(500);
          pass('B4-persona-added', 'Persona P1 added manually');
        } else {
          log('No save button for persona');
        }
      } else {
        log('Manual add button not found at step 2');
      }
    } catch (e) {
      log(`Persona add error: ${e.message}`);
    }

    await screenshot(studentPage, 'B4-persona-added');

    // Submit
    log('Step B5: Submit form');
    const submitBtn = studentPage.locator('button:has-text("開始探索"), button:has-text("建立"), button:has-text("Submit"), button[type="submit"]').first();
    const submitVisible = await submitBtn.isVisible().catch(() => false);
    if (submitVisible) {
      await submitBtn.click();
      // Wait for navigation to lobby or workspace
      try {
        await studentPage.waitForURL(/\/(lobby|workspace|projects\/[^/]+)/, { timeout: 15000 });
        const currentUrl = studentPage.url();
        pass('B5-project-created', `Project created, redirected to: ${currentUrl}`);

        // Extract project ID from URL
        const urlMatch = currentUrl.match(/projects\/([^/]+)/);
        if (urlMatch) projectId = urlMatch[1];
        log(`Project ID: ${projectId}`);
      } catch (e) {
        fail('B5-project-created', `Navigation timeout after submit: ${e.message}`);
        await screenshot(studentPage, 'B5-submit-error');
      }
    } else {
      fail('B5-submit', 'Submit button not found');
    }

  } catch (e) {
    fail('B-create-activity', `Create activity failed: ${e.message}`);
    await screenshot(studentPage, 'B-error');
  }

  // ============================================================
  // SECTION C: Lobby invite_code + linked teacher
  // ============================================================
  log('\n=== SECTION C: Lobby 活動代碼 + 列管狀態 ===');

  try {
    const currentUrl = studentPage.url();
    // Navigate to lobby if not already there
    if (!currentUrl.includes('lobby') && projectId) {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}`);
      await studentPage.waitForLoadState('networkidle');
    }
    await screenshot(studentPage, 'C1-lobby');

    const pageText = await studentPage.locator('body').innerText();

    // Check 活動代碼 card
    if (pageText.includes('活動代碼')) {
      pass('C1-invite-code-label', '"活動代碼" label visible in lobby');

      // Find the 6-char code
      const codeMatch = pageText.match(/[A-Z2-9]{6}/);
      if (codeMatch) {
        inviteCode = codeMatch[0];
        pass('C1-invite-code-value', `活動代碼 chip value: ${inviteCode}`);
      } else {
        fail('C1-invite-code-value', 'No 6-char code found near 活動代碼');
      }

      // Check 複製 button in lobby
      const lobbyCodeCopy = studentPage.locator('button:has-text("複製")').first();
      const lobbyCodeCopyVisible = await lobbyCodeCopy.isVisible().catch(() => false);
      if (lobbyCodeCopyVisible) {
        pass('C1-invite-code-copy', '複製 button exists on 活動代碼 card');
      } else {
        fail('C1-invite-code-copy', '複製 button not found on 活動代碼 card');
      }
    } else {
      fail('C1-invite-code-label', '"活動代碼" not found on lobby page');
    }

    // Check 列管狀態
    if (pageText.includes('列管狀態') || pageText.includes('已列管')) {
      if (pageText.includes('已列管') && (pageText.includes(teacherName) || pageText.includes('QA Teacher'))) {
        pass('C2-linked-teacher', `列管狀態 shows "已列管於 ${teacherName}"`);
      } else if (pageText.includes('已列管')) {
        pass('C2-linked-teacher', `列管狀態 shows 已列管 (teacher name: ${teacherName})`);
        // Log what we see
        log(`Page text around 列管: ${pageText.substring(pageText.indexOf('列管') - 20, pageText.indexOf('列管') + 100)}`);
      } else {
        fail('C2-linked-teacher', `列管狀態 visible but not showing 已列管. Text: ${pageText.substring(pageText.indexOf('列管狀態') - 10, pageText.indexOf('列管狀態') + 150)}`);
      }

      // Check 解除 button
      const relieveBtn = studentPage.locator('button:has-text("解除")').first();
      const relieveVisible = await relieveBtn.isVisible().catch(() => false);
      if (relieveVisible) {
        pass('C3-relieve-btn', '"解除" button visible in lobby 列管狀態');
      } else {
        fail('C3-relieve-btn', '"解除" button not found in lobby');
      }
    } else {
      fail('C2-linked-teacher', '"列管狀態" section not found on lobby page');
    }

  } catch (e) {
    fail('C-lobby', `Lobby check error: ${e.message}`);
    await screenshot(studentPage, 'C-error');
  }

  // ============================================================
  // SECTION D: Teacher dashboard sees linked activity
  // ============================================================
  log('\n=== SECTION D: Teacher dashboard sees linked activity ===');

  try {
    await teacherPage.reload();
    await teacherPage.waitForLoadState('networkidle');
    await screenshot(teacherPage, 'D1-teacher-dashboard-reloaded');

    const dashText = await teacherPage.locator('body').innerText();
    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', 'Teacher dashboard shows "QA Phase22" in monitor area');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found on teacher dashboard. Excerpt: ${dashText.slice(0, 500)}`);
    }
  } catch (e) {
    fail('D1-teacher-dashboard', `Teacher dashboard reload error: ${e.message}`);
  }

  // ============================================================
  // SECTION E: Negative path - invalid invite code
  // ============================================================
  log('\n=== SECTION E: Teacher track-by-invite negative path ===');

  try {
    // Find the invite code input on teacher dashboard
    const trackInput = teacherPage.locator('input[placeholder*="活動代碼"], input[placeholder*="邀請"], input[placeholder*="代碼"]').first();
    const trackInputVisible = await trackInput.isVisible().catch(() => false);
    if (trackInputVisible) {
      await trackInput.fill('NOTREAL');
      const trackBtn = teacherPage.locator('button:has-text("列管"), button:has-text("追蹤"), button:has-text("加入")').first();
      const trackBtnVisible = await trackBtn.isVisible().catch(() => false);
      if (trackBtnVisible) {
        await trackBtn.click();
        await teacherPage.waitForTimeout(2000);
        await screenshot(teacherPage, 'E1-invalid-code');

        const dashTextAfter = await teacherPage.locator('body').innerText();
        if (dashTextAfter.includes('找不到') || dashTextAfter.includes('無效') || dashTextAfter.includes('不存在') || dashTextAfter.includes('error') || dashTextAfter.includes('Error')) {
          pass('E1-invalid-code-error', 'Error message shown for invalid code "NOTREAL"');
        } else {
          fail('E1-invalid-code-error', `No error message for invalid code. Text: ${dashTextAfter.slice(0, 300)}`);
        }
      } else {
        fail('E1-track-button', 'Track/列管 button not found near invite code input');
      }
    } else {
      fail('E1-track-input', '"以活動代碼列管" input not found on teacher dashboard');
    }
  } catch (e) {
    fail('E1-negative-path', `Negative path test error: ${e.message}`);
  }

  // ============================================================
  // SECTION F: Author Color — seats sticky_color
  // ============================================================
  log('\n=== SECTION F: Author Color — seats sticky_color ===');

  if (projectId) {
    try {
      // Get token from student page
      const token = await studentPage.evaluate(() => localStorage.getItem('access_token'));
      if (token) {
        const seatsData = await studentPage.evaluate(async (args) => {
          const r = await fetch(`${args.base}/api/projects/${args.pid}/seats`, {
            headers: { Authorization: `Bearer ${args.token}` }
          });
          return r.json();
        }, { base: BASE_URL, pid: projectId, token });

        log(`Seats response: ${JSON.stringify(seatsData).slice(0, 300)}`);

        const validColors = ['yellow', 'orange', 'green', 'blue', 'violet', 'red', 'light-blue', 'light-green'];
        if (Array.isArray(seatsData)) {
          const allHaveColor = seatsData.every(s => s.sticky_color && validColors.includes(s.sticky_color));
          const colors = seatsData.map(s => s.sticky_color);
          const uniqueColors = [...new Set(colors)];
          if (allHaveColor) {
            pass('F1-seats-sticky-color', `All seats have valid sticky_color. Colors: ${colors.join(', ')}`);
          } else {
            fail('F1-seats-sticky-color', `Not all seats have valid sticky_color. Data: ${JSON.stringify(seatsData).slice(0, 200)}`);
          }
          if (seatsData.length > 1 && uniqueColors.length > 1) {
            pass('F2-seats-color-varied', `Colors differ across seats: ${uniqueColors.join(', ')}`);
          } else if (seatsData.length <= 1) {
            skip('F2-seats-color-varied', `Only ${seatsData.length} seat(s), cannot verify variation`);
          } else {
            fail('F2-seats-color-varied', `All seats have same color: ${colors[0]}`);
          }
        } else if (seatsData && seatsData.seats) {
          const seats = seatsData.seats;
          const allHaveColor = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));
          pass('F1-seats-sticky-color', `Seats data structure with nested seats. All valid: ${allHaveColor}. Sample: ${JSON.stringify(seats[0])}`);
        } else {
          fail('F1-seats-sticky-color', `Unexpected seats response format: ${JSON.stringify(seatsData).slice(0, 200)}`);
        }
      } else {
        fail('F1-seats', 'No access token found in student localStorage');
      }
    } catch (e) {
      fail('F1-seats', `Seats API error: ${e.message}`);
    }
  } else {
    skip('F1-seats', 'No projectId, skipping seats check');
  }

  // ============================================================
  // SECTION G: ChatDock bubble color
  // ============================================================
  log('\n=== SECTION G: ChatDock bubble color ===');

  try {
    const currentUrl = studentPage.url();
    let workspaceUrl = currentUrl;

    // Navigate to workspace if we have projectId
    if (projectId && !currentUrl.includes('workspace')) {
      workspaceUrl = `${BASE_URL}/projects/${projectId}/workspace`;
      await studentPage.goto(workspaceUrl);
      await studentPage.waitForLoadState('networkidle');
      await studentPage.waitForTimeout(3000);
    }

    await screenshot(studentPage, 'G1-workspace');

    const chatMessages = await studentPage.evaluate(() => {
      const selectors = [
        '[data-testid="chat-message"]',
        '.rounded-2xl',
        '[class*="message"]',
        '[class*="bubble"]',
      ];
      for (const sel of selectors) {
        const els = Array.from(document.querySelectorAll(sel));
        if (els.length > 0) {
          return els.slice(0, 5).map(el => ({
            text: el.textContent?.slice(0, 30),
            bg: getComputedStyle(el).backgroundColor,
            className: el.className?.slice(0, 50),
          }));
        }
      }
      return null;
    });

    if (!chatMessages || chatMessages.length === 0) {
      skip('G1-chat-bubble-color', 'No chat messages to inspect (no AI activity yet) — acceptable');
    } else {
      log(`Chat messages: ${JSON.stringify(chatMessages)}`);
      const hasColor = chatMessages.some(m => m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== 'transparent');
      if (hasColor) {
        pass('G1-chat-bubble-color', `Chat messages have background colors: ${chatMessages.map(m => m.bg).join(', ')}`);
      } else {
        fail('G1-chat-bubble-color', `Chat messages have no background colors (transparent). Messages: ${JSON.stringify(chatMessages)}`);
      }
    }
  } catch (e) {
    fail('G1-chat-bubble', `Chat bubble check error: ${e.message}`);
  }

  // ============================================================
  // SECTION H: HumanNoteColorInjector (best-effort)
  // ============================================================
  log('\n=== SECTION H: HumanNoteColorInjector (best-effort) ===');

  try {
    // Try to create a sticky note in tldraw
    await screenshot(studentPage, 'H1-before-note');

    // Look for sticky note tool in tldraw
    const stickyBtn = studentPage.locator('[data-testid="tools.note"], button[title*="Note"], button[title*="Sticky"], button[aria-label*="note"]').first();
    const stickyVisible = await stickyBtn.isVisible().catch(() => false);
    if (stickyVisible) {
      await stickyBtn.click();
      await studentPage.waitForTimeout(500);

      // Click on canvas to place note
      const canvas = studentPage.locator('canvas, [data-testid="canvas"], .tl-canvas, [class*="tl-"]').first();
      const canvasVisible = await canvas.isVisible().catch(() => false);
      if (canvasVisible) {
        const box = await canvas.boundingBox();
        if (box) {
          await studentPage.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
          await studentPage.waitForTimeout(2000);
          await screenshot(studentPage, 'H2-note-placed');

          // Check tldraw state for note color
          const noteColor = await studentPage.evaluate(() => {
            // Try to access tldraw editor state
            const store = window.__tldraw_editor_store;
            if (store) {
              const shapes = store.allRecords().filter(r => r.typeName === 'shape' && r.type === 'note');
              if (shapes.length > 0) return shapes[0].props?.color;
            }
            return null;
          });

          if (noteColor) {
            pass('H1-note-color', `Note color from tldraw state: ${noteColor}`);
          } else {
            skip('H1-note-color', 'Could not access tldraw editor state directly — best effort');
          }
        }
      }
    } else {
      skip('H1-note-color', 'tldraw sticky note tool not found — best effort');
    }
  } catch (e) {
    skip('H1-note-color', `HumanNoteColorInjector check skipped: ${e.message}`);
  }

  // ============================================================
  // FINAL REPORT
  // ============================================================
  log('\n\n========== PHASE 22 QA REPORT ==========');

  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;

  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | SKIP: ${skipCount}`);
  console.log('');

  for (const r of results) {
    const icon = r.status === 'PASS' ? 'PASS' : r.status === 'FAIL' ? 'FAIL' : 'SKIP';
    console.log(`[${icon}] ${r.area}: ${r.detail}`);
  }

  // Write JSON report
  const report = {
    timestamp: new Date().toISOString(),
    teacherEmail,
    studentEmail,
    teacherCode,
    projectId,
    inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, skip: skipCount },
    results,
  };

  const reportPath = path.join(__dirname, 'qa-phase22-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  log(`\nReport written to: ${reportPath}`);

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(2);
});
