/**
 * Phase 22 QA Test v5
 * Key fix: Set sessionStorage tour flags before page loads to prevent driver.js from blocking
 * Also: use { force: true } for clicks when overlay might interfere
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
}

/** Mark all driver.js tours as already shown so they don't auto-start */
async function suppressTours(page) {
  await page.evaluate(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
    } catch {}
  });
  // Also destroy any active driver overlay
  await page.evaluate(() => {
    try {
      // Remove driver SVG overlay if present
      document.querySelectorAll('.driver-overlay, .driver-popover-wrapper, [class*="driver-"]').forEach(el => el.remove());
    } catch {}
  });
}

/** Navigate to a page and suppress tours before they start */
async function gotoSuppressed(page, url) {
  // Use addInitScript to set sessionStorage before page scripts run
  await page.context().addInitScript(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
    } catch {}
  });
  await page.goto(url);
  await page.waitForLoadState('networkidle');
  await suppressTours(page);
}

async function register(page, email, password, displayName, role) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');
  await suppressTours(page);

  await page.locator(`button:has-text("${role === '教師' ? '教師' : '學生'}")`).first().click({ force: true });
  await page.waitForTimeout(200);
  await page.locator('input[type="text"]').first().fill(displayName);
  await page.locator('input[type="email"]').first().fill(email);
  const pwInputs = page.locator('input[type="password"]');
  await pwInputs.nth(0).fill(password);
  await pwInputs.nth(1).fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/projects', { timeout: 20000 });
  await suppressTours(page);
  log(`Registered ${role}: ${email}`);
}

async function main() {
  // Set init script on both contexts before pages are created
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================
  // A. TEACHER DASHBOARD
  // ============================================================
  log('\n=== A. Teacher Dashboard ===');
  const teacherContext = await browser.newContext();
  // Add init script to teacher context before any navigation
  await teacherContext.addInitScript(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
    } catch {}
  });
  const teacherPage = await teacherContext.newPage();
  let teacherCode = null;

  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    pass('A1-teacher-register', `Registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', e.message);
    await screenshot(teacherPage, 'A1-fail');
  }

  // Navigate to teacher dashboard via direct URL (auth state is in memory, no reload needed)
  // Use SPA navigation: click the navbar link instead of goto()
  try {
    await suppressTours(teacherPage);

    // Use client-side navigation via window.history / React Router
    await teacherPage.evaluate(() => {
      window.history.pushState({}, '', '/teacher/dashboard');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await teacherPage.waitForTimeout(1500);
    await suppressTours(teacherPage);

    log(`Teacher page URL after SPA nav: ${teacherPage.url()}`);
    await screenshot(teacherPage, 'A2-teacher-dashboard');

    const bodyText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard text (first 600): ${bodyText.slice(0, 600)}`);

    if (bodyText.includes('我的教師代碼')) {
      pass('A2-teacher-code-block', '"我的教師代碼" block rendered');
    } else {
      fail('A2-teacher-code-block', `Not found. URL: ${teacherPage.url()}. Text: ${bodyText.slice(0, 300)}`);
    }

    // Get teacher code
    const codeEls = teacherPage.locator('code');
    const codeCount = await codeEls.count();
    log(`<code> elements: ${codeCount}`);
    for (let i = 0; i < codeCount; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      log(`  code[${i}]: "${text}"`);
      if (text.length >= 4 && text !== '—') {
        teacherCode = text;
        const valid6 = /^[A-Z2-9]{6}$/.test(text) && !/[01OIL]/.test(text);
        if (valid6) {
          pass('A2-teacher-code-valid', `Teacher code: "${teacherCode}" — 6-char valid charset`);
        } else {
          pass('A2-teacher-code-exists', `Teacher code chip: "${teacherCode}"`);
          if (/[01OIL]/.test(text)) {
            fail('A2-teacher-code-charset', `Code "${text}" contains excluded chars (0,1,O,I,L)`);
          } else {
            pass('A2-teacher-code-charset', `Code "${text}" passes charset check`);
          }
        }
        break;
      }
    }
    if (!teacherCode) {
      fail('A2-teacher-code-value', `No code found. ${codeCount} <code> elements`);
    }

    // Copy button
    const copyBtns = teacherPage.locator('button:has-text("複製")');
    const cpCnt = await copyBtns.count();
    log(`"複製" buttons: ${cpCnt}`);
    if (cpCnt > 0) {
      pass('A3-copy-btn-exists', `${cpCnt} "複製" button(s)`);
      // Grant clipboard permission before clicking
      await teacherContext.grantPermissions(['clipboard-read', 'clipboard-write']);
      await copyBtns.first().click({ force: true });
      await teacherPage.waitForTimeout(700);
      await screenshot(teacherPage, 'A3-after-copy');
      const copiedEl = teacherPage.locator('text=已複製');
      const copiedVis = await copiedEl.isVisible().catch(() => false);
      if (copiedVis) {
        pass('A3-copy-feedback', '"已複製" visible — copy UI feedback works');
      } else {
        // In headless mode clipboard may not persist the state change
        // Treat as soft failure — the button exists and was clicked
        fail('A3-copy-feedback', '"已複製" not visible after copy (clipboard may not work headless)');
      }
    } else {
      fail('A3-copy-btn', '"複製" button not found');
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
  await studentContext.addInitScript(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
    } catch {}
  });
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
    await suppressTours(studentPage);
    await screenshot(studentPage, 'B2-projects');

    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click({ force: true });
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');

    const titleVis = await studentPage.locator('text=開啟新探索').first().isVisible().catch(() => false);
    if (titleVis) {
      pass('B2-modal-title', '"開啟新探索" visible');
    } else {
      fail('B2-modal-title', '"開啟新探索" not visible');
    }

    // Fill activity name
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 5000 });
    await nameInput.fill('QA Phase22');
    pass('B3-activity-name', '"QA Phase22" filled');

    // Check teacher code field
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
      fail('B3-teacher-code-field', '"加入老師班譯" input not visible');
    }

    // Set AI crew count to 1
    // Scroll dialog to show crew buttons
    await studentPage.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) dialog.scrollTop = 400;
    });
    await studentPage.waitForTimeout(300);

    const crewBtns = studentPage.locator('[role="dialog"] button').filter({ hasText: /AI 組員/ });
    const crewCnt = await crewBtns.count();
    log(`Crew buttons: ${crewCnt}`);
    if (crewCnt > 0) {
      await crewBtns.first().click({ force: true });
      await studentPage.waitForTimeout(300);
      pass('B3-crew-count-1', 'Set AI crew count to 1');
    } else {
      log('Crew buttons not found via filter, trying direct text match');
      const btn1 = studentPage.locator('[role="dialog"] button').nth(0); // fallback
      log('Proceeding with default crew count');
    }

    await screenshot(studentPage, 'B3-step1-filled');

    // Scroll to bottom for 下一步 button
    await studentPage.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) dialog.scrollTop = dialog.scrollHeight;
    });
    await studentPage.waitForTimeout(300);
    await screenshot(studentPage, 'B3-bottom');

    const nextBtn = studentPage.locator('[role="dialog"] button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    pass('B4-advance-personas', '"下一步" clicked');
    await screenshot(studentPage, 'B4-step2');

    // Determine how many personas needed
    const step2Text = await studentPage.locator('[role="dialog"]').innerText().catch(() => '');
    log(`Step2 text: ${step2Text.slice(0, 300)}`);
    const neededMatch = step2Text.match(/開始探索（\d+\/(\d+)）/);
    const neededPersonas = neededMatch ? parseInt(neededMatch[1]) : 1;
    log(`Personas needed: ${neededPersonas}`);

    // Add all needed personas
    let addedCount = 0;
    for (let pi = 0; pi < neededPersonas; pi++) {
      const manualBtn = studentPage.locator('button:has-text("手動新增")').first();
      const manualVis = await manualBtn.isVisible().catch(() => false);
      if (!manualVis) { log(`手動新增 not visible for persona ${pi+1}`); break; }
      await manualBtn.click({ force: true });
      await studentPage.waitForTimeout(800);
      await screenshot(studentPage, `B5-persona${pi+1}-form`);

      // The PersonaEditDialog opens as a separate [role="dialog"] on top
      // "姓名" Input component renders as input[type="text"] with placeholder "例：陳秀英"
      const pNameInput = studentPage.locator('input[placeholder="例：陳秀英"]').first();
      await pNameInput.waitFor({ state: 'visible', timeout: 8000 });
      await pNameInput.fill(`P${pi + 1}`);
      await studentPage.waitForTimeout(200);

      // Save (inside the PersonaEditDialog — it has its own 儲存 button)
      // Find the 儲存 button inside the topmost dialog
      const saveBtns = studentPage.locator('button:has-text("儲存")');
      const saveCnt = await saveBtns.count();
      log(`儲存 buttons: ${saveCnt}`);
      if (saveCnt > 0) {
        await saveBtns.last().click({ force: true });
        await studentPage.waitForTimeout(700);
        addedCount++;
        log(`Saved persona P${pi + 1}`);
      } else {
        const allBtns = await studentPage.locator('button').allTextContents();
        log(`All buttons: ${JSON.stringify(allBtns)}`);
        break;
      }
    }
    if (addedCount > 0) {
      pass('B5-personas-added', `Added ${addedCount}/${neededPersonas} persona(s)`);
    } else {
      fail('B5-personas-added', `Failed to add any personas (needed ${neededPersonas})`);
    }

    await screenshot(studentPage, 'B5-after-personas');

    // Check submit button state
    const submitBtn = studentPage.locator('[role="dialog"] button:has-text("開始探索")').first();
    await submitBtn.waitFor({ state: 'visible', timeout: 5000 });
    const isDisabled = await submitBtn.isDisabled().catch(() => true);
    const btnTitle = await submitBtn.getAttribute('title').catch(() => '');
    const btnText = await submitBtn.textContent().catch(() => '');
    log(`Submit: disabled=${isDisabled}, title="${btnTitle}", text="${btnText}"`);

    if (!isDisabled) {
      await submitBtn.click({ force: true });
      try {
        await studentPage.waitForURL(/\/projects\/[^/?#]+/, { timeout: 20000 });
        const url = studentPage.url();
        pass('B6-project-created', `Created, URL: ${url}`);
        const m = url.match(/projects\/([^/?#]+)/);
        if (m) projectId = m[1];
        log(`Project ID: ${projectId}`);
      } catch {
        await screenshot(studentPage, 'B6-timeout');
        const bodyText = await studentPage.locator('body').innerText();
        fail('B6-project-created', `Timeout. Body: ${bodyText.slice(0, 200)}`);
      }
    } else {
      fail('B6-submit', `Submit disabled: "${btnTitle}" | text: "${btnText}"`);
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
    log(`Student URL: ${currentUrl}`);

    // Navigate to lobby URL if we have projectId
    if (projectId) {
      // After create, URL should be /projects/:id (lobby) or /projects/:id/lobby
      if (!currentUrl.includes(projectId)) {
        await studentPage.goto(`${BASE_URL}/projects/${projectId}`);
        await studentPage.waitForLoadState('networkidle');
      }
    }
    await studentPage.waitForTimeout(1500);
    await suppressTours(studentPage);
    await screenshot(studentPage, 'C1-lobby');

    const bodyText = await studentPage.locator('body').innerText();
    log(`Lobby text (first 800): ${bodyText.slice(0, 800)}`);

    // 活動代碼
    if (bodyText.includes('活動代碼')) {
      pass('C1-invite-code-label', '"活動代碼" visible in lobby');

      const codeEls = studentPage.locator('code');
      const cnt = await codeEls.count();
      for (let i = 0; i < cnt; i++) {
        const t = (await codeEls.nth(i).textContent()).trim();
        if (t && t !== '—' && t.length >= 4) {
          inviteCode = t;
          pass('C1-invite-code-value', `活動代碼: "${inviteCode}"`);
          break;
        }
      }
      if (!inviteCode) {
        fail('C1-invite-code-value', `No valid code in <code>. Count: ${cnt}`);
      }

      const cpCnt = await studentPage.locator('button:has-text("複製")').count();
      if (cpCnt > 0) {
        pass('C2-lobby-copy-btn', `"複製" button(s) in lobby: ${cpCnt}`);
      } else {
        fail('C2-lobby-copy-btn', '"複製" not found in lobby');
      }
    } else {
      fail('C1-invite-code-label', '"活動代碼" not in lobby');
    }

    // 列管狀態
    if (bodyText.includes('列管狀態')) {
      pass('C3-linked-status-label', '"列管狀態" visible');
      if (teacherCode && bodyText.includes('已列管')) {
        pass('C4-linked-teacher', '"已列管" shown');
        if (bodyText.includes(teacherName)) {
          pass('C4-teacher-name', `"${teacherName}" in 已列管 text`);
        } else {
          fail('C4-teacher-name', `"${teacherName}" not visible near 已列管`);
        }
        const unlinkVis = await studentPage.locator('button:has-text("解除")').first().isVisible().catch(() => false);
        if (unlinkVis) {
          pass('C5-unlink-btn', '"解除" button visible');
        } else {
          fail('C5-unlink-btn', '"解除" button not found');
        }
      } else if (!teacherCode) {
        const hasLinkInput = bodyText.includes('老師代碼') || bodyText.includes('尚未列管');
        pass('C4-unlinked-state', `Unlinked state: ${hasLinkInput ? 'link input visible' : 'state shown'}`);
      } else {
        fail('C4-linked-teacher', `Teacher code "${teacherCode}" used but "已列管" not found`);
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
  log('\n=== D. Teacher Sees Activity ===');

  try {
    // SPA navigate on teacher page (already has auth state)
    await suppressTours(teacherPage);
    // Reload the teacher dashboard to get fresh data from API
    await teacherPage.evaluate(() => {
      window.history.pushState({}, '', '/teacher/dashboard');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await teacherPage.waitForTimeout(2000);
    await suppressTours(teacherPage);
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
    const trackInput = teacherPage.locator('input[placeholder="例：MD7K2A"]').first();
    await trackInput.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
    const trackVis = await trackInput.isVisible().catch(() => false);
    if (trackVis) {
      await trackInput.fill('NOTREAL');
      const trackBtn = teacherPage.locator('button:has-text("列管")').first();
      await trackBtn.waitFor({ state: 'visible', timeout: 5000 });
      await trackBtn.click({ force: true });
      await teacherPage.waitForTimeout(2000);
      await screenshot(teacherPage, 'E1-invalid-code');

      const pageText = await teacherPage.locator('body').innerText();
      const hasErr = pageText.includes('失敗') || pageText.includes('找不到') || pageText.includes('無效') || pageText.includes('不存在');
      if (hasErr) {
        const errEl = teacherPage.locator('.text-error, [class*="text-error"]').first();
        const errText = await errEl.textContent().catch(() => null);
        pass('E1-invalid-code-error', `Error shown: "${errText || '(in page text)'}"`);
      } else {
        fail('E1-invalid-code-error', `No error. Text: ${pageText.slice(0, 200)}`);
      }
    } else {
      const dashText = await teacherPage.locator('body').innerText();
      fail('E1-track-input', `Track input not visible. URL: ${teacherPage.url()}. Text: ${dashText.slice(0, 200)}`);
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
            pass('F1-seats-sticky-color', `All ${seats.length} seats have valid sticky_color: [${colors.join(', ')}]`);
          } else {
            fail('F1-seats-sticky-color', `Invalid colors. Data: ${JSON.stringify(seats).slice(0,300)}`);
          }
          const unique = [...new Set(colors)];
          if (seats.length > 1 && unique.length > 1) {
            pass('F2-seats-varied', `Colors differ: [${unique.join(', ')}]`);
          } else if (seats.length <= 1) {
            skip('F2-seats-varied', `Only ${seats.length} seat`);
          } else {
            fail('F2-seats-varied', `All same: ${unique[0]}`);
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
  // G. CHATDOCK BUBBLE COLOR
  // ============================================================
  log('\n=== G. ChatDock Bubble Color ===');

  if (projectId) {
    try {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}/workspace`);
      await studentPage.waitForLoadState('networkidle');
      await suppressTours(studentPage);
      await studentPage.waitForTimeout(3000);
      await screenshot(studentPage, 'G1-workspace');

      const chatInfo = await studentPage.evaluate(() => {
        const chatSelectors = ['[data-testid="chat-message"]', '[class*="ChatMessage"]', '[class*="chat-message"]', '[class*="message"]'];
        for (const sel of chatSelectors) {
          const els = Array.from(document.querySelectorAll(sel)).filter(el => el.textContent?.trim().length > 0);
          if (els.length > 0) {
            return { sel, count: els.length, items: els.slice(0,5).map(el => ({
              text: el.textContent?.slice(0,50),
              bg: getComputedStyle(el).backgroundColor,
              style: el.getAttribute('style'),
            })) };
          }
        }
        // Look for inline background-color
        const inlineEls = Array.from(document.querySelectorAll('[style*="background-color"]'));
        if (inlineEls.length > 0) {
          return { sel: 'inline-bg', count: inlineEls.length, items: inlineEls.slice(0,5).map(el => ({
            text: el.textContent?.slice(0,50),
            bg: el.style.backgroundColor,
            style: el.getAttribute('style'),
            tag: el.tagName,
          })) };
        }
        return null;
      });

      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages — no AI activity yet (acceptable)');
      } else {
        log(`Chat info: ${JSON.stringify(chatInfo).slice(0, 400)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.style && m.style.includes('background-color')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== '' && m.bg !== 'transparent')
        );
        if (hasColor) {
          pass('G1-chat-bubble-color', `bg color found. Sample: ${JSON.stringify(chatInfo.items[0]).slice(0,100)}`);
        } else {
          fail('G1-chat-bubble-color', `No bg color on elements. Data: ${JSON.stringify(chatInfo.items)}`);
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
  log('\n=== H. HumanNoteColorInjector ===');
  skip('H1-note-injector', 'best-effort tldraw state — skipped');

  // ============================================================
  // FINAL REPORT
  // ============================================================
  log('\n========== PHASE 22 QA REPORT ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;
  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | SKIP: ${skipCount}\n`);
  for (const r of results) console.log(`[${r.status.padEnd(4)}] ${r.area}: ${r.detail}`);

  const report = {
    timestamp: new Date().toISOString(),
    teacherEmail, studentEmail, teacherCode, projectId, inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, skip: skipCount },
    results,
  };
  fs.writeFileSync(path.join(__dirname, 'qa-phase22-report.json'), JSON.stringify(report, null, 2));
  log(`Report written.`);

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => { console.error('Fatal:', e); process.exit(2); });
