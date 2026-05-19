/**
 * Phase 22 QA Test v6
 * Fixes from v5:
 * - PersonaEditDialog detection: check for 'input[placeholder="例：陳秀英"]' in any dialog
 * - After manual add, persona form opens as a new modal (topmost [role="dialog"])
 * - Correctly parse submit button text for canSubmit check
 * - Properly wait for project creation and navigation
 * - Fixed 已複製 detection (uses Check icon, text may be separate)
 * - Negative path: properly check error text
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'phase22-v6');
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

/** Mark all driver.js tours as already shown so they don't auto-start */
async function suppressTours(page) {
  await page.evaluate(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
      // Remove any driver overlay that snuck in
      document.querySelectorAll('.driver-overlay, .driver-popover-wrapper, [class*="driver-"]').forEach(el => el.remove());
    } catch {}
  });
}

/** Add init script to context so it runs before page scripts on every navigation */
async function addTourSuppressScript(context) {
  await context.addInitScript(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
    } catch {}
  });
}

async function register(page, email, password, displayName, role) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');
  await suppressTours(page);

  // Click role button
  const roleLabel = role === '教師' ? '教師' : '學生';
  await page.locator(`button:has-text("${roleLabel}")`).first().click({ force: true });
  await page.waitForTimeout(200);
  await page.locator('input[type="text"]').first().fill(displayName);
  await page.locator('input[type="email"]').first().fill(email);
  const pwInputs = page.locator('input[type="password"]');
  await pwInputs.nth(0).fill(password);
  await pwInputs.nth(1).fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/projects', { timeout: 25000 });
  await suppressTours(page);
  log(`Registered ${role}: ${email}`);
}

/** SPA navigate using pushState + popstate */
async function spaNavigate(page, path) {
  await page.evaluate((p) => {
    window.history.pushState({}, '', p);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
  await page.waitForTimeout(1500);
  await suppressTours(page);
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================
  // A. TEACHER DASHBOARD
  // ============================================================
  log('\n=== A. Teacher Dashboard ===');
  const teacherContext = await browser.newContext();
  await teacherContext.grantPermissions(['clipboard-read', 'clipboard-write']);
  await addTourSuppressScript(teacherContext);
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

  // A2: Navigate to teacher dashboard and verify code block
  try {
    await spaNavigate(teacherPage, '/teacher/dashboard');
    log(`Teacher URL: ${teacherPage.url()}`);
    await screenshot(teacherPage, 'A2-teacher-dashboard');

    const bodyText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard body (first 600): ${bodyText.slice(0, 600)}`);

    if (bodyText.includes('我的教師代碼')) {
      pass('A2-teacher-code-block', '"我的教師代碼" block rendered');
    } else {
      fail('A2-teacher-code-block', `Not found. URL: ${teacherPage.url()}. Text: ${bodyText.slice(0, 300)}`);
    }

    // Get teacher code from <code> elements
    const codeEls = teacherPage.locator('code');
    const codeCount = await codeEls.count();
    log(`<code> elements found: ${codeCount}`);
    for (let i = 0; i < codeCount; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      log(`  code[${i}]: "${text}"`);
      if (text.length >= 4 && text !== '—') {
        teacherCode = text;
        // Check charset: uppercase A-Z + digits 2-9, no 0/O/1/I/L
        const is6Char = text.length === 6;
        const noExcluded = !/[01OIL]/.test(text);
        const upperAlphaNum = /^[A-Z2-9]+$/.test(text);
        if (is6Char && noExcluded && upperAlphaNum) {
          pass('A2-teacher-code-valid', `Teacher code: "${teacherCode}" — 6-char, valid charset [A-Z2-9], no 0/O/1/I/L`);
        } else {
          pass('A2-teacher-code-exists', `Teacher code chip: "${teacherCode}"`);
          if (!is6Char) fail('A2-teacher-code-length', `Expected 6 chars, got ${text.length}`);
          if (!noExcluded) fail('A2-teacher-code-charset', `Contains excluded chars (0,1,O,I,L): "${text}"`);
          if (!upperAlphaNum) fail('A2-teacher-code-format', `Not [A-Z2-9]: "${text}"`);
        }
        break;
      }
    }
    if (!teacherCode) {
      fail('A2-teacher-code-value', `No valid code found among ${codeCount} <code> elements`);
    }
  } catch (e) {
    fail('A2-teacher-dashboard', e.message);
    await screenshot(teacherPage, 'A2-fail');
  }

  // A3: Copy button click and feedback
  try {
    const copyBtns = teacherPage.locator('button:has-text("複製"), button').filter({ hasText: '複製' });
    const cpCnt = await copyBtns.count();
    log(`"複製" buttons: ${cpCnt}`);
    if (cpCnt > 0) {
      pass('A3-copy-btn-exists', `${cpCnt} "複製" button(s) present`);
      await copyBtns.first().click({ force: true });
      await teacherPage.waitForTimeout(800);
      await screenshot(teacherPage, 'A3-after-copy');

      // Check for "已複製" text — it's a text node in a button (icon + text)
      const pageText = await teacherPage.locator('body').innerText();
      if (pageText.includes('已複製')) {
        pass('A3-copy-feedback', '"已複製" text visible after copy click');
      } else {
        // The component uses Check icon + "已複製" text in the button, may fade quickly
        fail('A3-copy-feedback', '"已複製" not visible after copy click (may be headless clipboard issue or fast fade)');
      }
    } else {
      fail('A3-copy-btn', '"複製" button not found on teacher dashboard');
    }
  } catch (e) {
    fail('A3-copy-btn', e.message);
  }

  // ============================================================
  // B. STUDENT + CREATE ACTIVITY
  // ============================================================
  log('\n=== B. Student + Create Activity ===');
  const studentContext = await browser.newContext();
  await addTourSuppressScript(studentContext);
  const studentPage = await studentContext.newPage();
  let projectId = null;

  // B1: Register student
  try {
    await register(studentPage, studentEmail, studentPassword, studentName, '학생');
    pass('B1-student-register', `Registered: ${studentEmail}`);
  } catch (e) {
    // Try English "학생" failed — retry with Korean string not applicable. The role is 學生
    try {
      await register(studentPage, studentEmail, studentPassword, studentName, '學生');
      pass('B1-student-register', `Registered: ${studentEmail}`);
    } catch (e2) {
      fail('B1-student-register', e2.message);
      await screenshot(studentPage, 'B1-fail');
    }
  }

  // B2: Open "新增學習活動" modal
  try {
    await suppressTours(studentPage);
    await screenshot(studentPage, 'B2-projects');

    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click({ force: true });
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');

    const titleVis = await studentPage.locator('text=開啟新探索').first().isVisible().catch(() => false);
    if (titleVis) {
      pass('B2-modal-title', '"開啟新探索" modal title visible');
    } else {
      // May render as 建立新學習活動 if role detection fails
      const bodyText = await studentPage.locator('body').innerText();
      fail('B2-modal-title', `"開啟新探索" not visible. Page text: ${bodyText.slice(0, 200)}`);
    }
  } catch (e) {
    fail('B2-modal-open', e.message);
    await screenshot(studentPage, 'B2-fail');
  }

  // B3: Fill step 1 basics
  try {
    // Activity name
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 8000 });
    await nameInput.fill('QA Phase22');
    pass('B3-activity-name', '"QA Phase22" filled');

    // Teacher code field (only for students)
    const tcInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcVis = await tcInput.isVisible().catch(() => false);
    if (tcVis) {
      pass('B3-teacher-code-field', '"加入老師班譯" input visible (placeholder: 例：MD7K2A)');
      if (teacherCode) {
        await tcInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Teacher code "${teacherCode}" entered`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code available');
      }
    } else {
      fail('B3-teacher-code-field', '"加入老師班譯（選填）" input not visible — check if user is detected as student');
    }

    // Set AI crew count to 1 by clicking the "1" button
    const crewBtn1 = studentPage.locator('[role="dialog"] button').filter({ hasText: /^1$/ }).first();
    const crewBtn1Vis = await crewBtn1.isVisible().catch(() => false);
    if (crewBtn1Vis) {
      await crewBtn1.click({ force: true });
      await studentPage.waitForTimeout(300);
      pass('B3-crew-count-1', 'Crew count set to 1');
    } else {
      // Try by text content "1\nAI 組員"
      const allBtns = await studentPage.locator('[role="dialog"] button').allTextContents();
      log(`All dialog buttons: ${JSON.stringify(allBtns)}`);
      // Fallback: click first number button area
      const numBtns = studentPage.locator('[role="dialog"] button').filter({ hasText: 'AI 組員' });
      const numCnt = await numBtns.count();
      if (numCnt > 0) {
        await numBtns.first().click({ force: true });
        pass('B3-crew-count-1', `Clicked first AI 組員 button (${numCnt} found)`);
      } else {
        skip('B3-crew-count-1', 'Could not find crew count button, using default');
      }
    }

    await screenshot(studentPage, 'B3-step1-filled');
  } catch (e) {
    fail('B3-fill-step1', e.message);
    await screenshot(studentPage, 'B3-fail');
  }

  // B4: Advance to step 2 (personas)
  try {
    // Scroll to bottom of dialog to find 下一步 button
    await studentPage.evaluate(() => {
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs.length > 0) dialogs[dialogs.length - 1].scrollTop = 9999;
    });
    await studentPage.waitForTimeout(300);
    await screenshot(studentPage, 'B3-bottom');

    const nextBtn = studentPage.locator('[role="dialog"] button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    pass('B4-advance-personas', '"下一步" clicked → step 2');
    await screenshot(studentPage, 'B4-step2');
  } catch (e) {
    fail('B4-advance-step2', e.message);
    await screenshot(studentPage, 'B4-fail');
  }

  // B5: Add persona manually
  try {
    const step2Text = await studentPage.locator('[role="dialog"]').first().innerText().catch(() => '');
    log(`Step2 dialog text: ${step2Text.slice(0, 300)}`);

    // Determine aiCrewCount from submit button text e.g. "開始探索（0/1）"
    const submitBtnText = await studentPage.locator('[role="dialog"] button:has-text("開始探索")').first().textContent().catch(() => '');
    log(`Submit button text: "${submitBtnText}"`);
    const neededMatch = submitBtnText.match(/\d+\/(\d+)/);
    const neededPersonas = neededMatch ? parseInt(neededMatch[1]) : 1;
    log(`Personas needed: ${neededPersonas}`);

    let addedCount = 0;
    for (let pi = 0; pi < neededPersonas; pi++) {
      // Click 手動新增
      const manualBtn = studentPage.locator('button:has-text("手動新增")').first();
      await manualBtn.waitFor({ state: 'visible', timeout: 8000 });
      await manualBtn.click({ force: true });
      await studentPage.waitForTimeout(1000);
      await screenshot(studentPage, `B5-persona${pi + 1}-dialog`);

      // PersonaEditDialog opens as a NEW [role="dialog"] stacked on top
      // Wait for the persona name input
      const pNameInput = studentPage.locator('input[placeholder="例：陳秀英"]').first();
      await pNameInput.waitFor({ state: 'visible', timeout: 10000 });
      await pNameInput.fill(`P${pi + 1}`);
      await studentPage.waitForTimeout(200);
      log(`Filled persona name P${pi + 1}`);

      // Click 儲存 button — use the last visible 儲存 to get the one in the top dialog
      const saveBtns = studentPage.locator('button:has-text("儲存")');
      const saveCnt = await saveBtns.count();
      log(`儲存 buttons visible: ${saveCnt}`);

      if (saveCnt > 0) {
        // Click the last 儲存 (innermost dialog)
        await saveBtns.last().click({ force: true });
        await studentPage.waitForTimeout(800);
        addedCount++;
        log(`Saved persona P${pi + 1}`);
        await screenshot(studentPage, `B5-persona${pi + 1}-saved`);
      } else {
        const allBtns = await studentPage.locator('button').allTextContents();
        log(`All buttons: ${JSON.stringify(allBtns)}`);
        fail(`B5-persona${pi + 1}-save`, '儲存 button not found');
        break;
      }
    }

    if (addedCount === neededPersonas) {
      pass('B5-personas-added', `Added ${addedCount}/${neededPersonas} persona(s) manually`);
    } else if (addedCount > 0) {
      fail('B5-personas-added', `Only added ${addedCount}/${neededPersonas} personas`);
    } else {
      fail('B5-personas-added', `Failed to add any personas (needed ${neededPersonas})`);
    }

    await screenshot(studentPage, 'B5-after-personas');
  } catch (e) {
    fail('B5-personas', e.message);
    await screenshot(studentPage, 'B5-fail');
  }

  // B6: Submit to create project
  try {
    const submitBtn = studentPage.locator('[role="dialog"] button:has-text("開始探索")').first();
    await submitBtn.waitFor({ state: 'visible', timeout: 8000 });
    const isDisabled = await submitBtn.isDisabled().catch(() => true);
    const btnText = await submitBtn.textContent().catch(() => '');
    log(`Submit button: disabled=${isDisabled}, text="${btnText}"`);

    if (!isDisabled) {
      await submitBtn.click({ force: true });
      try {
        // Wait for URL to change to /projects/:id (lobby)
        await studentPage.waitForURL(/\/projects\/[^/?#]+/, { timeout: 25000 });
        const url = studentPage.url();
        pass('B6-project-created', `Project created, URL: ${url}`);
        const m = url.match(/projects\/([^/?#]+)/);
        if (m) projectId = m[1];
        log(`Project ID: ${projectId}`);
        await screenshot(studentPage, 'B6-after-create');
      } catch {
        await screenshot(studentPage, 'B6-timeout');
        const bodyText = await studentPage.locator('body').innerText();
        fail('B6-project-created', `Navigation timeout. Current URL: ${studentPage.url()}. Body: ${bodyText.slice(0, 300)}`);
      }
    } else {
      // Try to get more info about why disabled
      const dialogText = await studentPage.locator('[role="dialog"]').first().innerText().catch(() => '');
      fail('B6-submit-disabled', `Submit disabled. Dialog: ${dialogText.slice(0, 300)}`);
      await screenshot(studentPage, 'B6-disabled');
    }
  } catch (e) {
    fail('B6-submit', e.message);
    await screenshot(studentPage, 'B6-fail');
  }

  // ============================================================
  // C. LOBBY — invite_code + linked teacher
  // ============================================================
  log('\n=== C. Lobby ===');
  let inviteCode = null;

  try {
    const currentUrl = studentPage.url();
    log(`Student URL after create: ${currentUrl}`);

    // Wait for lobby to fully load
    await studentPage.waitForTimeout(2000);
    await suppressTours(studentPage);
    await screenshot(studentPage, 'C1-lobby');

    const bodyText = await studentPage.locator('body').innerText();
    log(`Lobby body (first 1000): ${bodyText.slice(0, 1000)}`);

    // 活動代碼 block
    if (bodyText.includes('活動代碼')) {
      pass('C1-invite-code-label', '"活動代碼" visible in lobby');

      // Find the code chip
      const codeEls = studentPage.locator('code');
      const cnt = await codeEls.count();
      log(`<code> elements in lobby: ${cnt}`);
      for (let i = 0; i < cnt; i++) {
        const t = (await codeEls.nth(i).textContent()).trim();
        log(`  lobby code[${i}]: "${t}"`);
        if (t && t !== '—' && t.length >= 4) {
          inviteCode = t;
          pass('C1-invite-code-value', `活動代碼: "${inviteCode}"`);
          break;
        }
      }
      if (!inviteCode) {
        fail('C1-invite-code-value', `No valid code found among ${cnt} <code> elements`);
      }

      // 複製 button for invite code
      const cpBtns = studentPage.locator('button:has-text("複製")');
      const cpCnt = await cpBtns.count();
      if (cpCnt > 0) {
        pass('C2-lobby-copy-btn', `"複製" button present in lobby (count: ${cpCnt})`);
      } else {
        fail('C2-lobby-copy-btn', '"複製" button not found in lobby');
      }
    } else {
      fail('C1-invite-code-label', `"活動代碼" not found in lobby. URL: ${currentUrl}`);
    }

    // 列管狀態 block
    if (bodyText.includes('列管狀態')) {
      pass('C3-linked-status-label', '"列管狀態" visible in lobby');

      if (teacherCode && bodyText.includes('已列管')) {
        pass('C4-linked-teacher', '"已列管" text visible (teacher code was submitted during creation)');
        if (bodyText.includes(teacherName)) {
          pass('C4-teacher-name', `"${teacherName}" visible in 已列管 text`);
        } else {
          fail('C4-teacher-name', `"${teacherName}" not visible. Body: ${bodyText.slice(0, 400)}`);
        }
        const unlinkBtn = studentPage.locator('button:has-text("解除")');
        const unlinkVis = await unlinkBtn.first().isVisible().catch(() => false);
        if (unlinkVis) {
          pass('C5-unlink-btn', '"解除" button visible');
        } else {
          fail('C5-unlink-btn', '"解除" button not visible');
        }
      } else if (!teacherCode) {
        skip('C4-linked-teacher', 'No teacher code was available — skip linked teacher checks');
      } else {
        // Teacher code was entered but 已列管 not shown
        fail('C4-linked-teacher', `Teacher code "${teacherCode}" used but "已列管" not in page. Text: ${bodyText.slice(0, 400)}`);
      }
    } else {
      fail('C3-linked-status-label', `"列管狀態" not in lobby. URL: ${currentUrl}`);
    }

  } catch (e) {
    fail('C-lobby', e.message);
    await screenshot(studentPage, 'C-fail');
  }

  // ============================================================
  // D. TEACHER SEES THE ACTIVITY
  // ============================================================
  log('\n=== D. Teacher Sees Activity ===');

  try {
    // Navigate teacher page back to dashboard
    await suppressTours(teacherPage);
    await spaNavigate(teacherPage, '/teacher/dashboard');
    await teacherPage.waitForTimeout(2000);
    await suppressTours(teacherPage);
    await screenshot(teacherPage, 'D1-teacher-dashboard-reload');

    const dashText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard after reload (first 600): ${dashText.slice(0, 600)}`);

    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', '"QA Phase22" appears on teacher dashboard monitoring area');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found. Text: ${dashText.slice(0, 500)}`);
    }
  } catch (e) {
    fail('D1-teacher-sees-activity', e.message);
    await screenshot(teacherPage, 'D1-fail');
  }

  // ============================================================
  // E. NEGATIVE PATH — invalid invite code on teacher dashboard
  // ============================================================
  log('\n=== E. Negative Path ===');

  try {
    // The teacher dashboard has an input with placeholder for 活動代碼
    // Looking at TeacherDashboard code: Input with placeholder based on context
    // The track input is in "以活動代碼列管學生活動" section
    // From the source: trackCode state, no specific placeholder set — uses Input default
    // Let's look for the input near the 列管 button
    const trackInput = teacherPage.locator('input').filter({ hasNot: teacherPage.locator('input[type="password"]') }).last();

    // Better: locate by the surrounding section
    const trackSection = teacherPage.locator('body');
    const trackInputByLabel = teacherPage.locator('input').nth(-1); // last input on page

    // From source: the input is a plain Input component next to a Button "列管"
    // Let's find it near 列管 button
    const listBtn = teacherPage.locator('button:has-text("列管")').first();
    const listBtnVis = await listBtn.isVisible().catch(() => false);

    if (listBtnVis) {
      // Find input closest to the 列管 button area
      const inputs = teacherPage.locator('input[type="text"], input:not([type])');
      const inputCnt = await inputs.count();
      log(`Inputs on teacher dashboard: ${inputCnt}`);

      // From source code: <Input value={trackCode} onChange=... placeholder not explicitly set>
      // It'll be the last or only non-hidden input near the 列管 button
      let trackInputEl = null;
      for (let i = inputCnt - 1; i >= 0; i--) {
        const el = inputs.nth(i);
        const vis = await el.isVisible().catch(() => false);
        if (vis) { trackInputEl = el; break; }
      }

      if (trackInputEl) {
        await trackInputEl.scrollIntoViewIfNeeded();
        await trackInputEl.fill('NOTREAL');
        log('Filled "NOTREAL" into track input');
        await listBtn.click({ force: true });
        await teacherPage.waitForTimeout(2000);
        await screenshot(teacherPage, 'E1-invalid-code');

        const pageText = await teacherPage.locator('body').innerText();
        log(`Page text after invalid code: ${pageText.slice(0, 400)}`);

        // The error message from TeacherDashboard: trackError state renders as text
        // handleTrackActivity: setTrackError(detail ?? '列管失敗，請確認代碼是否正確')
        const hasErr = pageText.includes('列管失敗') ||
                       pageText.includes('找不到') ||
                       pageText.includes('無效') ||
                       pageText.includes('不存在') ||
                       pageText.includes('請確認');
        if (hasErr) {
          // Extract error text
          const errSpan = teacherPage.locator('.text-error, [class*="text-error"], [class*="text-red"]').first();
          const errText = await errSpan.textContent().catch(() => null);
          pass('E1-invalid-code-error', `Error shown: "${errText || '(in page body)'}" `);
        } else {
          fail('E1-invalid-code-error', `No recognizable error. Text: ${pageText.slice(0, 400)}`);
        }
      } else {
        fail('E1-track-input', `No visible input found. Buttons: ${await teacherPage.locator('button').allTextContents()}`);
      }
    } else {
      fail('E1-track-btn', '"列管" button not visible on teacher dashboard');
    }
  } catch (e) {
    fail('E1-negative', e.message);
    await screenshot(teacherPage, 'E1-fail');
  }

  // ============================================================
  // F. SEATS sticky_color
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
          try { return { status: r.status, data: JSON.parse(text) }; } catch { return { status: r.status, raw: text }; }
        }, { base: BASE_URL, pid: projectId, tok: token });

        log(`Seats API response: ${JSON.stringify(seatsData).slice(0, 600)}`);
        const validColors = ['yellow', 'orange', 'green', 'blue', 'violet', 'red', 'light-blue', 'light-green'];
        const seats = Array.isArray(seatsData.data) ? seatsData.data :
                      (seatsData.data?.seats || []);

        if (seats.length === 0) {
          fail('F1-seats', `No seats returned. Raw: ${JSON.stringify(seatsData).slice(0, 300)}`);
        } else {
          const colors = seats.map(s => s.sticky_color);
          const allHaveColor = seats.every(s => s.sticky_color != null);
          const allValid = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));

          if (!allHaveColor) {
            fail('F1-seats-sticky-color-present', `Some seats missing sticky_color. Data: ${JSON.stringify(seats).slice(0, 300)}`);
          } else if (!allValid) {
            fail('F1-seats-sticky-color-valid', `Invalid color values. Colors: [${colors.join(', ')}]. Valid: [${validColors.join(', ')}]`);
          } else {
            pass('F1-seats-sticky-color', `All ${seats.length} seats have valid sticky_color: [${colors.join(', ')}]`);
          }

          const unique = [...new Set(colors)];
          if (seats.length <= 1) {
            skip('F2-seats-varied', `Only ${seats.length} seat — variation test not applicable`);
          } else if (unique.length > 1) {
            pass('F2-seats-varied', `Colors differ across seats: [${unique.join(', ')}]`);
          } else {
            fail('F2-seats-varied', `All ${seats.length} seats have same color: "${unique[0]}"`);
          }
        }
      } else {
        fail('F1-token', 'No access_token in localStorage');
      }
    } catch (e) {
      fail('F1-seats', e.message);
    }
  } else {
    skip('F1-seats', 'No projectId — skipping seats check');
    skip('F2-seats-varied', 'No projectId');
  }

  // ============================================================
  // G. CHATDOCK BUBBLE COLOR
  // ============================================================
  log('\n=== G. ChatDock Bubble Color ===');

  if (projectId) {
    try {
      // Navigate to workspace
      await studentPage.goto(`${BASE_URL}/projects/${projectId}/workspace`);
      await studentPage.waitForLoadState('networkidle');
      await suppressTours(studentPage);
      await studentPage.waitForTimeout(3000);
      await screenshot(studentPage, 'G1-workspace');

      const chatInfo = await studentPage.evaluate(() => {
        // Try multiple selectors to find chat messages
        const selectors = [
          '[data-testid="chat-message"]',
          '[class*="ChatMessage"]',
          '[class*="chat-message"]',
          '.chat-bubble',
        ];
        for (const sel of selectors) {
          const els = Array.from(document.querySelectorAll(sel)).filter(el => el.textContent?.trim().length > 0);
          if (els.length > 0) {
            return { sel, count: els.length, items: els.slice(0, 5).map(el => ({
              text: el.textContent?.slice(0, 50),
              bg: getComputedStyle(el).backgroundColor,
              style: el.getAttribute('style'),
            })) };
          }
        }
        // Look for elements with inline background-color style
        const inlineEls = Array.from(document.querySelectorAll('[style*="background-color"]'));
        if (inlineEls.length > 0) {
          return { sel: 'inline-bg', count: inlineEls.length, items: inlineEls.slice(0, 5).map(el => ({
            text: el.textContent?.slice(0, 50),
            bg: el.style.backgroundColor,
            style: el.getAttribute('style'),
            tag: el.tagName,
          })) };
        }
        return null;
      });

      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages or styled elements — no AI activity yet (acceptable)');
      } else {
        log(`Chat info: ${JSON.stringify(chatInfo).slice(0, 500)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.style && m.style.includes('background-color')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== '' && m.bg !== 'transparent')
        );
        if (hasColor) {
          pass('G1-chat-bubble-color', `Bubble bg-color found. Sample[0]: ${JSON.stringify(chatInfo.items[0]).slice(0, 120)}`);
        } else {
          fail('G1-chat-bubble-color', `No bg-color on message elements. Data: ${JSON.stringify(chatInfo.items).slice(0, 300)}`);
        }
      }
    } catch (e) {
      fail('G1-workspace-nav', e.message);
      await screenshot(studentPage, 'G1-fail');
    }
  } else {
    skip('G1-chat-bubble', 'No projectId — skipping workspace check');
  }

  // ============================================================
  // H. HumanNoteColorInjector (best-effort)
  // ============================================================
  log('\n=== H. HumanNoteColorInjector ===');
  skip('H1-note-injector', 'Best-effort tldraw state introspection — skipped (requires tldraw editor API)');

  // ============================================================
  // FINAL REPORT
  // ============================================================
  log('\n========== PHASE 22 QA REPORT (v6) ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;
  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | SKIP: ${skipCount}\n`);
  for (const r of results) {
    console.log(`[${r.status.padEnd(4)}] ${r.area}: ${r.detail}`);
  }

  const report = {
    timestamp: new Date().toISOString(),
    version: 'v6',
    teacherEmail,
    studentEmail,
    teacherCode,
    projectId,
    inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, skip: skipCount },
    results,
    screenshotDir: SCREENSHOT_DIR,
  };
  fs.writeFileSync(path.join(__dirname, 'qa-phase22-v6-report.json'), JSON.stringify(report, null, 2));
  log(`Report written to qa-phase22-v6-report.json`);

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => { console.error('Fatal error:', e); process.exit(2); });
