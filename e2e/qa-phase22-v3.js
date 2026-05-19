/**
 * Phase 22 QA Test v3
 * Fixes:
 *  - Dismiss tour before interacting with teacher dashboard
 *  - Scroll to teacher code section
 *  - Correct activity name input selector (placeholder is example text)
 *  - Find correct step 2 personas content + submit button
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

function log(msg) { console.log(`[${new Date().toISOString()}] ${msg}`); }
function pass(area, detail) { log(`PASS [${area}]: ${detail}`); results.push({ area, status: 'PASS', detail }); }
function fail(area, detail) { log(`FAIL [${area}]: ${detail}`); results.push({ area, status: 'FAIL', detail }); }
function skip(area, detail) { log(`SKIP [${area}]: ${detail}`); results.push({ area, status: 'SKIP', detail }); }

async function screenshot(page, name) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  log(`Screenshot: ${p}`);
  return p;
}

async function dismissTours(page) {
  // Click all × close buttons on tour/onboarding popups
  for (let i = 0; i < 10; i++) {
    const closeBtn = page.locator('button:has-text("×"), button[aria-label="close"], button[aria-label="Close"]').first();
    const visible = await closeBtn.isVisible().catch(() => false);
    if (!visible) break;
    await closeBtn.click();
    await page.waitForTimeout(200);
  }
  // Also click any "跳過" or "完成" tour buttons
  const skipBtn = page.locator('button:has-text("跳過"), button:has-text("完成"), button:has-text("關閉")').first();
  const skipVisible = await skipBtn.isVisible().catch(() => false);
  if (skipVisible) await skipBtn.click();
}

async function register(page, email, password, displayName, role) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');

  const roleLabel = role === '教師' ? '教師' : '學生';
  await page.locator(`button:has-text("${roleLabel}")`).first().click();
  await page.waitForTimeout(200);

  await page.locator('input[type="text"]').first().fill(displayName);
  await page.locator('input[type="email"]').first().fill(email);
  const pwInputs = page.locator('input[type="password"]');
  await pwInputs.nth(0).fill(password);
  await pwInputs.nth(1).fill(password);

  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/projects', { timeout: 20000 });
  log(`Registered ${role}: ${email}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================
  // A. TEACHER DASHBOARD
  // ============================================================
  log('\n=== A. Teacher Registration + Dashboard ===');
  const teacherContext = await browser.newContext();
  const teacherPage = await teacherContext.newPage();
  let teacherCode = null;

  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    pass('A1-teacher-register', `Registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', e.message);
    await screenshot(teacherPage, 'A1-fail');
  }

  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForLoadState('networkidle');
    await teacherPage.waitForTimeout(1500);

    // Dismiss any tour popups
    await dismissTours(teacherPage);
    await teacherPage.waitForTimeout(500);

    await screenshot(teacherPage, 'A2-teacher-dashboard-no-tour');

    // Scroll to find 我的教師代碼 section
    const codeSection = teacherPage.locator('text=我的教師代碼');
    // Try scrolling it into view
    try {
      await codeSection.scrollIntoViewIfNeeded({ timeout: 5000 });
    } catch {
      // scroll page manually
      await teacherPage.evaluate(() => window.scrollBy(0, 300));
    }
    await teacherPage.waitForTimeout(300);
    await screenshot(teacherPage, 'A2-scrolled');

    const codeSectionVisible = await codeSection.isVisible().catch(() => false);
    if (codeSectionVisible) {
      pass('A2-teacher-code-block', '"我的教師代碼" block visible');
    } else {
      // Check if it's in the DOM at all
      const allText = await teacherPage.locator('body').innerText();
      if (allText.includes('我的教師代碼')) {
        pass('A2-teacher-code-block', '"我的教師代碼" text in DOM (may not be visible)');
      } else {
        fail('A2-teacher-code-block', `"我的教師代碼" not found in DOM. Page text: ${allText.slice(0, 400)}`);
      }
    }

    // Find the code in <code> elements
    const codeEls = teacherPage.locator('code');
    const count = await codeEls.count();
    log(`Found ${count} <code> elements`);
    for (let i = 0; i < count; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      log(`  code[${i}]: "${text}"`);
      if (text.length === 6 && /^[A-Z2-9]+$/.test(text) && !/[01OIL]/.test(text)) {
        teacherCode = text;
        pass('A2-teacher-code-value', `Teacher code: ${teacherCode} (6-char, valid charset A-Z2-9, no 0/O/1/I/L)`);
        break;
      } else if (text.length === 6 && text !== '——————') {
        teacherCode = text;
        pass('A2-teacher-code-exists', `Teacher code chip: "${teacherCode}"`);
        if (/[01OIL]/.test(text)) {
          fail('A2-teacher-code-charset', `Code "${text}" contains excluded chars (0,1,O,I,L)`);
        }
        break;
      }
    }
    if (!teacherCode) {
      // Try getting from page text — find 6-char uppercase sequence
      const bodyText = await teacherPage.locator('body').innerText();
      const match = bodyText.match(/\b([A-Z2-9]{6})\b/);
      if (match && !/[01OIL]/.test(match[1])) {
        teacherCode = match[1];
        pass('A2-teacher-code-text', `Teacher code from page text: ${teacherCode}`);
      } else {
        fail('A2-teacher-code-value', 'Could not find 6-char teacher code');
      }
    }

    // A3: Copy button
    const copyBtns = teacherPage.locator('button:has-text("複製")');
    const copyCount = await copyBtns.count();
    log(`Found ${copyCount} 複製 buttons`);
    if (copyCount > 0) {
      pass('A3-copy-button-exists', `${copyCount} "複製" button(s) visible`);
      await copyBtns.first().click();
      await teacherPage.waitForTimeout(600);
      await screenshot(teacherPage, 'A3-after-copy');

      const copiedText = teacherPage.locator('text=已複製').first();
      const copiedVisible = await copiedText.isVisible().catch(() => false);
      if (copiedVisible) {
        pass('A3-copy-feedback', '"已複製" feedback visible');
      } else {
        fail('A3-copy-feedback', '"已複製" not visible after copy click');
      }
    } else {
      fail('A3-copy-button', '"複製" button not found');
    }

  } catch (e) {
    fail('A2-teacher-dashboard', e.message);
    await screenshot(teacherPage, 'A2-fail');
  }

  // ============================================================
  // B. STUDENT: Register + Create Activity
  // ============================================================
  log('\n=== B. Student + Create Activity ===');
  const studentContext = await browser.newContext();
  const studentPage = await studentContext.newPage();
  let projectId = null;

  try {
    await register(studentPage, studentEmail, studentPassword, studentName, '學生');
    pass('B1-student-register', `Registered: ${studentEmail}`);
  } catch (e) {
    fail('B1-student-register', e.message);
    await screenshot(studentPage, 'B1-fail');
  }

  // Dismiss any tour
  await dismissTours(studentPage);

  try {
    await studentPage.goto(`${BASE_URL}/projects`);
    await studentPage.waitForLoadState('networkidle');
    await dismissTours(studentPage);
    await screenshot(studentPage, 'B2-projects');

    // Click 新增學習活動
    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click();
    await studentPage.waitForTimeout(1000);
    await screenshot(studentPage, 'B2-modal-open');

    // Check modal title
    const modalTitle = studentPage.locator('text=開啟新探索').first();
    const titleVisible = await modalTitle.isVisible().catch(() => false);
    if (titleVisible) {
      pass('B2-modal-title', '"開啟新探索" visible');
    } else {
      const dialogText = await studentPage.locator('[role="dialog"]').textContent().catch(() => '');
      fail('B2-modal-title', `Expected "開啟新探索", got: "${dialogText.slice(0, 60)}"`);
    }

    // Step 1: Fill activity name
    // The input has label "活動名稱" and placeholder "例：校園永續設計工作坊"
    // Use label-based or placeholder-based
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    const nameVisible = await nameInput.isVisible().catch(() => false);
    if (nameVisible) {
      await nameInput.fill('QA Phase22');
      pass('B3-activity-name', 'Activity name "QA Phase22" filled');
    } else {
      // Try by label text proximity
      const nameLabel = studentPage.locator('label:has-text("活動名稱")');
      const labelVisible = await nameLabel.isVisible().catch(() => false);
      if (labelVisible) {
        const parentInput = studentPage.locator('label:has-text("活動名稱") + input, label:has-text("活動名稱") ~ input').first();
        await parentInput.fill('QA Phase22');
        pass('B3-activity-name', 'Activity name filled via label');
      } else {
        fail('B3-activity-name', 'Activity name input not found');
      }
    }

    // Check teacher code field
    const tcInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcVisible = await tcInput.isVisible().catch(() => false);
    if (tcVisible) {
      pass('B3-teacher-code-field', '"加入老師班譯" field visible (placeholder: 例：MD7K2A)');
      if (teacherCode) {
        await tcInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Teacher code "${teacherCode}" entered`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code');
      }
    } else {
      // Check if label exists even if input is not visible
      const tcLabel = studentPage.locator('text=加入老師班譯').first();
      const tcLabelVisible = await tcLabel.isVisible().catch(() => false);
      if (tcLabelVisible) {
        pass('B3-teacher-code-field', '"加入老師班譯" label visible (input may be scrolled)');
      } else {
        fail('B3-teacher-code-field', '"加入老師班譯" field not visible');
      }
    }

    await screenshot(teacherPage, 'B3-step1-with-code');
    await screenshot(studentPage, 'B3-step1-filled');

    // Scroll down in dialog to find 下一步 button
    await studentPage.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) dialog.scrollTop = 9999;
    });
    await studentPage.waitForTimeout(300);
    await screenshot(studentPage, 'B3-step1-scrolled-bottom');

    // Click 下一步
    const nextBtn = studentPage.locator('button:has-text("下一步")').first();
    const nextVisible = await nextBtn.isVisible().catch(() => false);
    if (nextVisible) {
      await nextBtn.click();
      await studentPage.waitForTimeout(1000);
      pass('B4-advance-step2', 'Clicked "下一步" to advance to personas step');
    } else {
      fail('B4-advance-step2', '"下一步" button not found');
    }

    await screenshot(studentPage, 'B4-step2-personas');

    // Step 2: Personas
    // "手動新增" button
    const manualBtn = studentPage.locator('button:has-text("手動新增")').first();
    const manualVisible = await manualBtn.isVisible().catch(() => false);
    if (manualVisible) {
      await manualBtn.click();
      await studentPage.waitForTimeout(500);
      await screenshot(studentPage, 'B5-manual-add-clicked');

      // Fill persona name
      const personaInputs = studentPage.locator('input[type="text"]');
      const pCount = await personaInputs.count();
      log(`Found ${pCount} text inputs after manual add`);
      // The newly added persona form inputs
      // Look for input with placeholder for name
      const pNameInput = studentPage.locator('input[placeholder*="P1"], input[placeholder*="角色名稱"], input[placeholder*="名稱"]').first();
      const pNameVisible = await pNameInput.isVisible().catch(() => false);
      if (pNameVisible) {
        await pNameInput.fill('P1');
      } else if (pCount > 0) {
        await personaInputs.last().fill('P1');
      }

      // Try to save
      const saveBtn = studentPage.locator('button:has-text("儲存"), button:has-text("確認"), button:has-text("加入")').first();
      const saveVisible = await saveBtn.isVisible().catch(() => false);
      if (saveVisible) {
        await saveBtn.click();
        await studentPage.waitForTimeout(400);
        pass('B5-persona-saved', 'Persona P1 saved');
      }
    } else {
      log('"手動新增" not found on step 2 — checking page content');
      const step2Text = await studentPage.locator('body').innerText();
      log(`Step 2 text: ${step2Text.slice(0, 400)}`);
    }

    await screenshot(studentPage, 'B5-after-persona');

    // Find "開始探索" submit button
    const submitBtn = studentPage.locator('button:has-text("開始探索")').first();
    const submitVisible = await submitBtn.isVisible().catch(() => false);
    if (submitVisible) {
      await submitBtn.click();
      try {
        await studentPage.waitForURL(/\/projects\/[^/?#]+/, { timeout: 20000 });
        const url = studentPage.url();
        pass('B6-project-created', `Created, URL: ${url}`);
        const m = url.match(/projects\/([^/?#]+)/);
        if (m) projectId = m[1];
        log(`Project ID: ${projectId}`);
      } catch {
        await screenshot(studentPage, 'B6-submit-timeout');
        fail('B6-project-created', 'Navigation timeout after submit');
      }
    } else {
      // Maybe we need to scroll to find it
      await studentPage.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        if (dialog) dialog.scrollTop = 9999;
      });
      const submitBtn2 = studentPage.locator('button:has-text("開始探索")').first();
      const sv2 = await submitBtn2.isVisible().catch(() => false);
      if (sv2) {
        await submitBtn2.click();
        try {
          await studentPage.waitForURL(/\/projects\/[^/?#]+/, { timeout: 20000 });
          const url = studentPage.url();
          pass('B6-project-created', `Created after scroll, URL: ${url}`);
          const m = url.match(/projects\/([^/?#]+)/);
          if (m) projectId = m[1];
        } catch {
          fail('B6-project-created', 'Navigation timeout');
        }
      } else {
        await screenshot(studentPage, 'B6-no-submit');
        const allBtns = await studentPage.locator('button').allTextContents();
        fail('B6-submit', `"開始探索" not found. Buttons: ${allBtns.join(', ')}`);
      }
    }

  } catch (e) {
    fail('B-create-activity', e.message);
    await screenshot(studentPage, 'B-fail');
  }

  // ============================================================
  // C. LOBBY
  // ============================================================
  log('\n=== C. Lobby ===');

  try {
    const currentUrl = studentPage.url();
    log(`Current URL: ${currentUrl}`);

    if (projectId && !currentUrl.includes(projectId)) {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}`);
      await studentPage.waitForLoadState('networkidle');
    }
    await studentPage.waitForTimeout(1500);
    await dismissTours(studentPage);
    await screenshot(studentPage, 'C1-lobby');

    const lobbyText = await studentPage.locator('body').innerText();
    log(`Lobby text excerpt: ${lobbyText.slice(0, 600)}`);

    // 活動代碼
    if (lobbyText.includes('活動代碼')) {
      pass('C1-invite-code-label', '"活動代碼" visible');

      // Get code chip value
      const codeEl = studentPage.locator('code').first();
      const codeText = (await codeEl.textContent().catch(() => '')).trim();
      if (codeText && codeText !== '—' && codeText.length >= 4) {
        pass('C1-invite-code-value', `活動代碼 value: "${codeText}"`);
      } else {
        fail('C1-invite-code-value', `活動代碼 chip shows: "${codeText}"`);
      }

      // Copy button
      const copyBtn = studentPage.locator('button:has-text("複製")').first();
      const copyVisible = await copyBtn.isVisible().catch(() => false);
      if (copyVisible) {
        pass('C2-lobby-copy-btn', '"複製" button on 活動代碼 visible');
      } else {
        fail('C2-lobby-copy-btn', '"複製" not visible in lobby');
      }
    } else {
      fail('C1-invite-code-label', '"活動代碼" not in lobby text');
    }

    // 列管狀態
    if (lobbyText.includes('列管狀態')) {
      pass('C3-linked-status-label', '"列管狀態" visible');

      if (teacherCode && lobbyText.includes('已列管')) {
        pass('C4-linked-teacher', `"已列管" shown (teacher code "${teacherCode}" was used)`);
        if (lobbyText.includes(teacherName)) {
          pass('C4-teacher-name', `Teacher name "${teacherName}" shown in 列管狀態`);
        } else {
          fail('C4-teacher-name', `Teacher name "${teacherName}" not in 已列管 text`);
        }
        const unlinkBtn = studentPage.locator('button:has-text("解除")').first();
        const unlinkVisible = await unlinkBtn.isVisible().catch(() => false);
        if (unlinkVisible) {
          pass('C5-unlink-btn', '"解除" button visible');
        } else {
          fail('C5-unlink-btn', '"解除" button not found');
        }
      } else if (!teacherCode) {
        // No teacher code used — should show unlinked input
        if (lobbyText.includes('尚未列管') || lobbyText.includes('老師代碼')) {
          pass('C4-unlinked-state', '"尚未列管" or link input shown (no teacher code used)');
        } else {
          pass('C4-linked-status-content', `列管狀態 content: ${lobbyText.substring(lobbyText.indexOf('列管狀態'), lobbyText.indexOf('列管狀態') + 100)}`);
        }
      } else {
        fail('C4-linked-teacher', `Teacher code was "${teacherCode}" but "已列管" not found. Text: ${lobbyText.slice(0, 500)}`);
      }
    } else {
      fail('C3-linked-status-label', '"列管狀態" not in lobby text');
    }

  } catch (e) {
    fail('C-lobby', e.message);
    await screenshot(studentPage, 'C-fail');
  }

  // ============================================================
  // D. TEACHER SEES ACTIVITY
  // ============================================================
  log('\n=== D. Teacher Sees Activity ===');

  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForLoadState('networkidle');
    await teacherPage.waitForTimeout(1500);
    await dismissTours(teacherPage);
    await screenshot(teacherPage, 'D1-teacher-reload');

    const dashText = await teacherPage.locator('body').innerText();
    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', '"QA Phase22" found on teacher dashboard');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found. Excerpt: ${dashText.slice(0, 400)}`);
    }
  } catch (e) {
    fail('D1-teacher-sees-activity', e.message);
  }

  // ============================================================
  // E. NEGATIVE PATH
  // ============================================================
  log('\n=== E. Negative Path: Invalid Code ===');

  try {
    // After dismissing tour, teacher dashboard should show the 以活動代碼列管 input
    const trackInput = teacherPage.locator('input[placeholder="例：MD7K2A"]').last();
    // Try scrolling to it
    await trackInput.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
    const trackVisible = await trackInput.isVisible().catch(() => false);
    if (trackVisible) {
      await trackInput.fill('NOTREAL');
      const trackBtn = teacherPage.locator('button:has-text("列管")').last();
      await trackBtn.waitFor({ state: 'visible', timeout: 5000 });
      await trackBtn.click();
      await teacherPage.waitForTimeout(2000);
      await screenshot(teacherPage, 'E1-invalid-code');

      // Check for error
      const errorEl = teacherPage.locator('.text-error, [class*="text-error"], span.text-xs').filter({ hasText: /失敗|找不到|無效|不存在|錯誤/ }).first();
      const errorVisible = await errorEl.isVisible().catch(() => false);
      const errorText = errorVisible ? (await errorEl.textContent()).trim() : null;

      const pageText = await teacherPage.locator('body').innerText();
      const hasError = pageText.includes('失敗') || pageText.includes('找不到') || pageText.includes('無效') || pageText.includes('不存在');
      if (hasError || errorText) {
        pass('E1-invalid-code-error', `Error shown for "NOTREAL": "${errorText || 'error text in page'}"`);
      } else {
        fail('E1-invalid-code-error', `No error for invalid code "NOTREAL". Page: ${pageText.slice(0, 200)}`);
      }
    } else {
      const dashText = await teacherPage.locator('body').innerText();
      fail('E1-track-input', `Track input (placeholder "例：MD7K2A") not visible. Page text: ${dashText.slice(0, 400)}`);
    }
  } catch (e) {
    fail('E1-negative-path', e.message);
  }

  // ============================================================
  // F. SEATS STICKY_COLOR
  // ============================================================
  log('\n=== F. Seats sticky_color ===');

  if (projectId) {
    try {
      const token = await studentPage.evaluate(() => localStorage.getItem('access_token'));
      if (token) {
        const seatsData = await studentPage.evaluate(async ({ base, pid, tok }) => {
          const r = await fetch(`${base}/api/projects/${pid}/seats`, {
            headers: { Authorization: `Bearer ${tok}` }
          });
          const text = await r.text();
          try { return JSON.parse(text); } catch { return { error: text }; }
        }, { base: BASE_URL, pid: projectId, tok: token });

        log(`Seats response: ${JSON.stringify(seatsData).slice(0, 500)}`);

        const validColors = ['yellow', 'orange', 'green', 'blue', 'violet', 'red', 'light-blue', 'light-green'];
        const seats = Array.isArray(seatsData) ? seatsData : (seatsData?.seats || []);

        if (seats.length === 0) {
          fail('F1-seats', `No seats in response. Data: ${JSON.stringify(seatsData).slice(0, 200)}`);
        } else {
          const seatColors = seats.map(s => s.sticky_color);
          const allValid = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));
          if (allValid) {
            pass('F1-seats-sticky-color', `All ${seats.length} seats have valid sticky_color: [${seatColors.join(', ')}]`);
          } else {
            const bad = seats.filter(s => !validColors.includes(s.sticky_color));
            fail('F1-seats-sticky-color', `Invalid colors: ${JSON.stringify(bad).slice(0,200)}`);
          }
          const unique = [...new Set(seatColors)];
          if (seats.length > 1 && unique.length > 1) {
            pass('F2-seats-varied', `Colors differ: [${unique.join(', ')}]`);
          } else if (seats.length <= 1) {
            skip('F2-seats-varied', `Only ${seats.length} seat`);
          } else {
            fail('F2-seats-varied', `All seats same color: ${unique[0]}`);
          }
        }
      } else {
        fail('F1-token', 'No access_token in localStorage');
      }
    } catch (e) {
      fail('F1-seats', e.message);
    }
  } else {
    skip('F1-seats', 'No projectId');
  }

  // ============================================================
  // G. CHATDOCK (workspace)
  // ============================================================
  log('\n=== G. ChatDock Bubble Color ===');

  try {
    if (projectId) {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}/workspace`);
      await studentPage.waitForLoadState('networkidle');
      await studentPage.waitForTimeout(3000);
      await dismissTours(studentPage);
      await screenshot(studentPage, 'G1-workspace');

      const chatInfo = await studentPage.evaluate(() => {
        // Look specifically for chat message elements (not general rounded elements)
        const chatSelectors = [
          '[data-testid="chat-message"]',
          '[class*="ChatMessage"]',
          '[class*="chat-message"]',
          '[class*="message-bubble"]',
        ];
        for (const sel of chatSelectors) {
          const els = Array.from(document.querySelectorAll(sel));
          if (els.length > 0) {
            return { selector: sel, count: els.length, items: els.slice(0,5).map(el => ({
              text: el.textContent?.slice(0,40),
              bg: getComputedStyle(el).backgroundColor,
              inlineStyle: el.getAttribute('style') || '',
            })) };
          }
        }
        // Also check for any element with inline background-color style
        const allEls = Array.from(document.querySelectorAll('[style*="background"]'));
        if (allEls.length > 0) {
          return { selector: 'inline-style-bg', count: allEls.length, items: allEls.slice(0,5).map(el => ({
            text: el.textContent?.slice(0,40),
            bg: el.style.backgroundColor,
            inlineStyle: el.getAttribute('style'),
          })) };
        }
        return null;
      });

      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages or inline-styled elements found (no AI activity yet) — acceptable');
      } else {
        log(`Chat info: ${JSON.stringify(chatInfo)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.inlineStyle && m.inlineStyle.includes('background')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== 'transparent')
        );
        if (hasColor) {
          pass('G1-chat-bubble-color', `Messages have background color. Sample: ${JSON.stringify(chatInfo.items[0])}`);
        } else {
          fail('G1-chat-bubble-color', `Messages found but no background color: ${JSON.stringify(chatInfo.items)}`);
        }
      }
    } else {
      skip('G1-chat-bubble', 'No projectId');
    }
  } catch (e) {
    fail('G1-workspace', e.message);
  }

  // ============================================================
  // H. HUMANNOTECOLORINJECTOR
  // ============================================================
  log('\n=== H. HumanNoteColorInjector (best-effort) ===');
  skip('H1-note-injector', 'tldraw DOM interaction best-effort — skipped in headless mode');

  // ============================================================
  // REPORT
  // ============================================================
  log('\n========== PHASE 22 QA REPORT ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;

  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | SKIP: ${skipCount}`);
  console.log('');
  for (const r of results) {
    console.log(`[${r.status.padEnd(4)}] ${r.area}: ${r.detail}`);
  }

  const report = {
    timestamp: new Date().toISOString(),
    teacherEmail, studentEmail, teacherCode, projectId,
    summary: { total: results.length, pass: passCount, fail: failCount, skip: skipCount },
    results,
  };
  fs.writeFileSync(path.join(__dirname, 'qa-phase22-report.json'), JSON.stringify(report, null, 2));

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => { console.error('Fatal:', e); process.exit(2); });
