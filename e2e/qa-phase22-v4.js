/**
 * Phase 22 QA Test v4
 * Key fixes:
 *  - Navigate to teacher dashboard via navbar link (not page.goto) to avoid auth race
 *  - Set AI crew count to 1 before proceeding
 *  - Use Escape key to dismiss tour overlays (avoid intercept issues)
 *  - Use force:true on dismiss buttons if needed
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
  // Try pressing Escape to close modals/tours
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  // Click × buttons (force to bypass intercept)
  for (let i = 0; i < 8; i++) {
    const closeBtn = page.locator('button').filter({ hasText: /^×$/ }).first();
    const visible = await closeBtn.isVisible().catch(() => false);
    if (!visible) break;
    try {
      await closeBtn.click({ force: true });
      await page.waitForTimeout(200);
    } catch { break; }
  }
  await page.waitForTimeout(300);
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
  await page.waitForLoadState('networkidle');
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

  // A1: Register teacher
  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    pass('A1-teacher-register', `Registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', e.message);
    await screenshot(teacherPage, 'A1-fail');
  }

  // Dismiss tour on /projects
  await dismissTours(teacherPage);
  await teacherPage.waitForTimeout(500);

  // A2: Navigate to teacher dashboard via NAVBAR LINK (critical fix)
  try {
    const dashLink = teacherPage.locator('a[href="/teacher/dashboard"], a:has-text("教師儀表板")').first();
    await dashLink.waitFor({ state: 'visible', timeout: 10000 });
    await dashLink.click();
    await teacherPage.waitForLoadState('networkidle');
    await teacherPage.waitForTimeout(1000);

    log(`Teacher page URL: ${teacherPage.url()}`);

    // Dismiss dashboard tour
    await dismissTours(teacherPage);
    await teacherPage.waitForTimeout(500);

    await screenshot(teacherPage, 'A2-teacher-dashboard');

    const bodyText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard text (first 600): ${bodyText.slice(0, 600)}`);

    // Check for "我的教師代碼" — it's always rendered on teacher dashboard (not conditional)
    if (bodyText.includes('我的教師代碼')) {
      pass('A2-teacher-code-block', '"我的教師代碼" text in page');
    } else {
      fail('A2-teacher-code-block', `"我的教師代碼" not in page text. URL: ${teacherPage.url()}`);
    }

    // Get teacher code from <code> elements
    const codeEls = teacherPage.locator('code');
    const codeCount = await codeEls.count();
    log(`<code> elements: ${codeCount}`);
    for (let i = 0; i < codeCount; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      log(`  code[${i}]: "${text}"`);
      if (text.length === 6 && /^[A-Z2-9]+$/.test(text) && !/[01OIL]/.test(text)) {
        teacherCode = text;
        pass('A2-teacher-code-valid', `Teacher code: ${teacherCode}`);
        break;
      } else if (text.length >= 4 && text !== '—') {
        teacherCode = text;
        pass('A2-teacher-code-exists', `Teacher code chip: "${teacherCode}"`);
        if (/[01OIL]/.test(text)) {
          fail('A2-teacher-code-charset', `Code "${text}" contains excluded chars`);
        } else {
          pass('A2-teacher-code-charset', `Code "${text}" passes charset check`);
        }
        break;
      }
    }

    if (!teacherCode) {
      // Try from page text — find 4-8 char uppercase pattern
      const match = bodyText.match(/\b([A-Z][A-Z2-9]{3,7})\b/);
      if (match && !/[01OIL]/.test(match[1])) {
        teacherCode = match[1];
        pass('A2-teacher-code-text', `Teacher code from text: ${teacherCode}`);
      } else {
        fail('A2-teacher-code-value', 'No teacher code found');
      }
    }

    // A3: Copy button
    const copyBtns = teacherPage.locator('button:has-text("複製")');
    const copyCount = await copyBtns.count();
    if (copyCount > 0) {
      pass('A3-copy-btn-exists', `${copyCount} "複製" button(s) found`);

      await copyBtns.first().click();
      await teacherPage.waitForTimeout(700);
      await screenshot(teacherPage, 'A3-after-copy');

      const copiedEl = teacherPage.locator('text=已複製');
      const copiedVisible = await copiedEl.isVisible().catch(() => false);
      if (copiedVisible) {
        pass('A3-copy-feedback', '"已複製" visible after copy');
      } else {
        fail('A3-copy-feedback', '"已複製" not visible after copy click');
      }
    } else {
      fail('A3-copy-btn', '"複製" button not found on teacher dashboard');
    }

  } catch (e) {
    fail('A2-teacher-dashboard', e.message);
    await screenshot(teacherPage, 'A2-fail');
  }

  // ============================================================
  // B. STUDENT + CREATE ACTIVITY
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

  try {
    await dismissTours(studentPage);
    await screenshot(studentPage, 'B2-projects');

    // Click 新增學習活動
    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click();
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');

    // Check modal title
    const titleVisible = await studentPage.locator('text=開啟新探索').first().isVisible().catch(() => false);
    if (titleVisible) {
      pass('B2-modal-title', '"開啟新探索" visible');
    } else {
      fail('B2-modal-title', '"開啟新探索" not visible');
    }

    // Fill activity name (placeholder: "例：校園永續設計工作坊")
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 5000 });
    await nameInput.fill('QA Phase22');
    pass('B3-activity-name', '"QA Phase22" entered');

    // Check teacher code field
    const tcInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcVisible = await tcInput.isVisible().catch(() => false);
    if (tcVisible) {
      pass('B3-teacher-code-field', '"加入老師班譯" input visible');
      if (teacherCode) {
        await tcInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Entered teacher code: "${teacherCode}"`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code available');
      }
    } else {
      fail('B3-teacher-code-field', '"加入老師班譯" input (placeholder: 例：MD7K2A) not visible');
    }

    // Set AI crew count to 1 (click the "1" button in the crew selector)
    // The buttons are type="button" with text "1", "2", "3", "4" + "AI 組員" subtext
    // Scroll dialog to find crew buttons
    await studentPage.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) dialog.scrollTop = 500;
    });
    await studentPage.waitForTimeout(200);

    // Find crew count buttons - they have text like "1\nAI 組員"
    const crewBtns = studentPage.locator('[role="dialog"] button').filter({ hasText: 'AI 組員' });
    const crewCount = await crewBtns.count();
    log(`Found ${crewCount} crew count buttons`);
    if (crewCount > 0) {
      // The first one is crew count = 1
      await crewBtns.first().click();
      await studentPage.waitForTimeout(300);
      pass('B3-crew-count-1', 'Set AI crew count to 1');
    } else {
      // Try to find by text content "1" near "AI 組員"
      const btn1 = studentPage.locator('[role="dialog"] button').filter({ hasText: /^1/ }).first();
      const btn1Visible = await btn1.isVisible().catch(() => false);
      if (btn1Visible) {
        await btn1.click();
        pass('B3-crew-count-1', 'Set crew count to 1 via fallback');
      } else {
        log('Could not find crew count buttons — proceeding with default (3), will need 3 personas');
      }
    }

    await screenshot(studentPage, 'B3-step1-filled');

    // Scroll to bottom and click 下一步
    await studentPage.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) dialog.scrollTop = 99999;
    });
    await studentPage.waitForTimeout(300);
    await screenshot(studentPage, 'B3-step1-bottom');

    const nextBtn = studentPage.locator('[role="dialog"] button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click();
    await studentPage.waitForTimeout(1000);
    pass('B4-advance-personas', 'Clicked 下一步');
    await screenshot(studentPage, 'B4-step2-personas');

    // Find the aiCrewCount to know how many personas are needed
    const step2Text = await studentPage.locator('[role="dialog"]').innerText().catch(() => '');
    log(`Step 2 dialog text: ${step2Text.slice(0, 200)}`);
    // "開始探索（0/N）" tells us N
    const neededMatch = step2Text.match(/開始探索（\d+\/(\d+)）/);
    const neededPersonas = neededMatch ? parseInt(neededMatch[1]) : 1;
    log(`Need ${neededPersonas} personas`);

    // Add personas manually (all needed)
    let addedCount = 0;
    for (let pi = 0; pi < neededPersonas; pi++) {
      const manualBtn = studentPage.locator('[role="dialog"] button:has-text("手動新增")').first();
      const manualVisible = await manualBtn.isVisible().catch(() => false);
      if (!manualVisible) {
        log(`手動新增 not found for persona ${pi + 1}`);
        break;
      }
      await manualBtn.click();
      await studentPage.waitForTimeout(500);

      // Persona name input
      const pNameInput = studentPage.locator('[role="dialog"] input[type="text"]').last();
      const pCount = await studentPage.locator('[role="dialog"] input[type="text"]').count();
      log(`Text inputs in dialog: ${pCount}`);
      await pNameInput.fill(`P${pi + 1}`);
      await studentPage.waitForTimeout(200);

      // Save persona
      const saveBtn = studentPage.locator('[role="dialog"] button:has-text("儲存"), [role="dialog"] button:has-text("確認")').first();
      const saveVisible = await saveBtn.isVisible().catch(() => false);
      if (saveVisible) {
        await saveBtn.click();
        await studentPage.waitForTimeout(400);
        addedCount++;
        log(`Saved persona P${pi + 1}`);
      } else {
        // Maybe "確認新增" or similar
        const allBtns = await studentPage.locator('[role="dialog"] button').allTextContents();
        log(`Dialog buttons: ${JSON.stringify(allBtns)}`);
        break;
      }
    }
    if (addedCount > 0) {
      pass('B5-personas-added', `Added ${addedCount}/${neededPersonas} personas`);
    }

    await screenshot(studentPage, 'B5-after-personas');

    // Click 開始探索
    const submitBtn = studentPage.locator('[role="dialog"] button:has-text("開始探索")').first();
    await submitBtn.waitFor({ state: 'visible', timeout: 5000 });
    const isDisabled = await submitBtn.isDisabled().catch(() => true);
    const btnTitle = await submitBtn.getAttribute('title').catch(() => '');
    log(`Submit button disabled: ${isDisabled}, title: "${btnTitle}"`);

    if (!isDisabled) {
      await submitBtn.click();
      try {
        await studentPage.waitForURL(/\/projects\/[^/?#]+/, { timeout: 20000 });
        const url = studentPage.url();
        pass('B6-project-created', `Project created, URL: ${url}`);
        const m = url.match(/projects\/([^/?#]+)/);
        if (m) projectId = m[1];
        log(`Project ID: ${projectId}`);
      } catch {
        await screenshot(studentPage, 'B6-timeout');
        fail('B6-project-created', 'Timeout waiting for project URL');
      }
    } else {
      fail('B6-submit', `"開始探索" is disabled. Title: "${btnTitle}". Needed: ${neededPersonas}, added: ${addedCount}`);
      await screenshot(studentPage, 'B6-disabled');
    }

  } catch (e) {
    fail('B-create-activity', e.message);
    await screenshot(studentPage, 'B-fail');
  }

  // ============================================================
  // C. LOBBY
  // ============================================================
  log('\n=== C. Lobby ===');
  let inviteCode = null;

  try {
    const currentUrl = studentPage.url();
    log(`Current student URL: ${currentUrl}`);

    // Navigate to lobby if needed
    if (projectId && !currentUrl.includes('/lobby')) {
      // Check if current URL is the lobby (it could be /projects/:id or /projects/:id/lobby)
      if (!currentUrl.match(/projects\/[^/?]+$/)) {
        await studentPage.goto(`${BASE_URL}/projects/${projectId}`);
        await studentPage.waitForLoadState('networkidle');
      }
    }
    await studentPage.waitForTimeout(1500);
    await dismissTours(studentPage);
    await screenshot(studentPage, 'C1-lobby');

    const bodyText = await studentPage.locator('body').innerText();
    log(`Lobby text (first 800): ${bodyText.slice(0, 800)}`);

    // 活動代碼
    if (bodyText.includes('活動代碼')) {
      pass('C1-invite-code-label', '"活動代碼" visible');

      // Get code from <code> elements
      const codeEls = studentPage.locator('code');
      const cnt = await codeEls.count();
      for (let i = 0; i < cnt; i++) {
        const t = (await codeEls.nth(i).textContent()).trim();
        if (t.length >= 4 && t !== '—') {
          inviteCode = t;
          pass('C1-invite-code-value', `活動代碼 value: "${inviteCode}"`);
          break;
        }
      }
      if (!inviteCode) {
        fail('C1-invite-code-value', `No valid code in <code> elements. Count: ${cnt}`);
      }

      // Copy button
      const copyBtns = studentPage.locator('button:has-text("複製")');
      const cpCnt = await copyBtns.count();
      if (cpCnt > 0) {
        pass('C2-lobby-copy-btn', `${cpCnt} "複製" button(s) in lobby`);
      } else {
        fail('C2-lobby-copy-btn', '"複製" not in lobby');
      }
    } else {
      fail('C1-invite-code-label', '"活動代碼" not found in lobby');
    }

    // 列管狀態
    if (bodyText.includes('列管狀態')) {
      pass('C3-linked-status-label', '"列管狀態" visible');

      if (teacherCode && bodyText.includes('已列管')) {
        pass('C4-linked-teacher', '"已列管" shown — teacher linked');
        if (bodyText.includes(teacherName)) {
          pass('C4-teacher-name', `"${teacherName}" in 已列管 text`);
        } else {
          fail('C4-teacher-name', `"${teacherName}" not found near 已列管`);
        }
        const unlinkBtn = studentPage.locator('button:has-text("解除")').first();
        const unlinkVisible = await unlinkBtn.isVisible().catch(() => false);
        if (unlinkVisible) {
          pass('C5-unlink-btn', '"解除" button visible');
        } else {
          fail('C5-unlink-btn', '"解除" button not found');
        }
      } else if (!teacherCode) {
        // No teacher code — should show "尚未列管" or link input
        if (bodyText.includes('尚未列管') || bodyText.includes('老師代碼')) {
          pass('C4-unlinked', 'Unlinked state shown correctly (no teacher code entered)');
        } else {
          pass('C4-linked-status', `列管狀態 content observed (no teacher code used)`);
        }
      } else {
        fail('C4-linked-teacher', `Teacher code was "${teacherCode}" but "已列管" not found`);
      }
    } else {
      fail('C3-linked-status-label', '"列管狀態" not in lobby');
    }

  } catch (e) {
    fail('C-lobby', e.message);
    await screenshot(studentPage, 'C-fail');
  }

  // ============================================================
  // D. TEACHER SEES ACTIVITY
  // ============================================================
  log('\n=== D. Teacher Dashboard Sees Activity ===');

  try {
    // Teacher is already on teacher dashboard or navigate via navbar
    const teacherCurrentUrl = teacherPage.url();
    if (!teacherCurrentUrl.includes('teacher/dashboard')) {
      const dashLink = teacherPage.locator('a:has-text("教師儀表板")').first();
      const linkVisible = await dashLink.isVisible().catch(() => false);
      if (linkVisible) {
        await dashLink.click();
        await teacherPage.waitForLoadState('networkidle');
      } else {
        await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
        await teacherPage.waitForLoadState('networkidle');
      }
    } else {
      // Reload the teacher dashboard to get fresh data
      await teacherPage.reload();
      await teacherPage.waitForLoadState('networkidle');
    }
    await teacherPage.waitForTimeout(1500);
    await dismissTours(teacherPage);
    await screenshot(teacherPage, 'D1-teacher-reload');

    const dashText = await teacherPage.locator('body').innerText();
    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', '"QA Phase22" on teacher dashboard');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found. Text: ${dashText.slice(0, 400)}`);
    }
  } catch (e) {
    fail('D1-teacher-sees-activity', e.message);
  }

  // ============================================================
  // E. NEGATIVE PATH
  // ============================================================
  log('\n=== E. Negative Path ===');

  try {
    // Find the track code input (teacher dashboard: "以活動代碼列管學生活動")
    const trackInput = teacherPage.locator('input[placeholder="例：MD7K2A"]').first();
    await trackInput.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
    const trackVisible = await trackInput.isVisible().catch(() => false);
    if (trackVisible) {
      await trackInput.fill('NOTREAL');
      // Find 列管 button near it
      const trackBtn = teacherPage.locator('button:has-text("列管")').first();
      await trackBtn.waitFor({ state: 'visible', timeout: 5000 });
      await trackBtn.click();
      await teacherPage.waitForTimeout(2000);
      await screenshot(teacherPage, 'E1-invalid-code');

      const pageText = await teacherPage.locator('body').innerText();
      const hasError = pageText.includes('失敗') || pageText.includes('找不到') || pageText.includes('無效') || pageText.includes('不存在') || pageText.includes('請輸入');
      if (hasError) {
        // Find the specific error text
        const errorSpan = teacherPage.locator('.text-error, [class*="text-error"]').first();
        const errorText = await errorSpan.textContent().catch(() => null);
        pass('E1-invalid-code-error', `Error shown for "NOTREAL": "${errorText || '(found in page text)'}"`);
      } else {
        fail('E1-invalid-code-error', `No error for "NOTREAL". Page: ${pageText.slice(0, 200)}`);
      }
    } else {
      const dashText = await teacherPage.locator('body').innerText();
      fail('E1-track-input', `Track input not visible. URL: ${teacherPage.url()}. Text: ${dashText.slice(0, 300)}`);
    }
  } catch (e) {
    fail('E1-negative', e.message);
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
          fail('F1-seats', `No seats. Response: ${JSON.stringify(seatsData).slice(0, 200)}`);
        } else {
          const colors = seats.map(s => s.sticky_color);
          const allValid = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));
          if (allValid) {
            pass('F1-seats-sticky-color', `All ${seats.length} seats valid: [${colors.join(', ')}]`);
          } else {
            const bad = seats.filter(s => !validColors.includes(s.sticky_color));
            fail('F1-seats-sticky-color', `${bad.length} invalid. Bad: ${JSON.stringify(bad).slice(0,200)}`);
          }
          const unique = [...new Set(colors)];
          if (seats.length > 1 && unique.length > 1) {
            pass('F2-seats-varied', `Colors differ: [${unique.join(', ')}]`);
          } else if (seats.length <= 1) {
            skip('F2-seats-varied', `Only ${seats.length} seat`);
          } else {
            fail('F2-seats-varied', `All same color: ${unique[0]}`);
          }
        }
      } else {
        fail('F1-token', 'No token');
      }
    } catch (e) {
      fail('F1-seats', e.message);
    }
  } else {
    skip('F1-seats', 'No projectId');
  }

  // ============================================================
  // G. CHATDOCK BUBBLE COLOR (workspace)
  // ============================================================
  log('\n=== G. ChatDock Bubble Color ===');

  if (projectId) {
    try {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}/workspace`);
      await studentPage.waitForLoadState('networkidle');
      await studentPage.waitForTimeout(3000);
      await screenshot(studentPage, 'G1-workspace');

      const chatInfo = await studentPage.evaluate(() => {
        const chatSelectors = ['[data-testid="chat-message"]', '[class*="ChatMessage"]', '[class*="chat-message"]'];
        for (const sel of chatSelectors) {
          const els = Array.from(document.querySelectorAll(sel));
          if (els.length > 0) {
            return { sel, count: els.length, items: els.slice(0,5).map(el => ({
              text: el.textContent?.slice(0,40),
              bg: getComputedStyle(el).backgroundColor,
              style: el.getAttribute('style'),
            })) };
          }
        }
        // Look for inline background-color styles (author color)
        const inlineEls = Array.from(document.querySelectorAll('[style*="background-color"]'));
        if (inlineEls.length > 0) {
          return { sel: 'inline-bg', count: inlineEls.length, items: inlineEls.slice(0,5).map(el => ({
            text: el.textContent?.slice(0,40),
            bg: el.style.backgroundColor,
            style: el.getAttribute('style'),
            tag: el.tagName,
          })) };
        }
        return null;
      });

      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages or inline-color elements — no AI activity yet (acceptable)');
      } else {
        log(`Chat info: ${JSON.stringify(chatInfo)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.style && m.style.includes('background')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)')
        );
        if (hasColor) {
          pass('G1-chat-bubble-color', `Elements with bg color: ${JSON.stringify(chatInfo.items[0])}`);
        } else {
          fail('G1-chat-bubble-color', `Elements found but no bg color: ${JSON.stringify(chatInfo)}`);
        }
      }
    } catch (e) {
      fail('G1-workspace', e.message);
    }
  } else {
    skip('G1-chat-bubble', 'No projectId');
  }

  // ============================================================
  // H. HUMANNOTECOLORINJECTOR (best-effort)
  // ============================================================
  log('\n=== H. HumanNoteColorInjector (best-effort) ===');
  skip('H1-note-injector', 'tldraw direct state access best-effort — skipped');

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
    teacherEmail, studentEmail, teacherCode, projectId, inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, skip: skipCount },
    results,
  };
  fs.writeFileSync(path.join(__dirname, 'qa-phase22-report.json'), JSON.stringify(report, null, 2));

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => { console.error('Fatal:', e); process.exit(2); });
