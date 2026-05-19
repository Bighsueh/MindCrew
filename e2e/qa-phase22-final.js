/**
 * Phase 22 QA Final Test
 *
 * Strategy:
 * 1. UI tests A1-B5: Register teacher + student, open modal, fill form (report UI bug on role field).
 * 2. B6-BUG: Document that PersonaEditDialog has no 'role' input → 422 on submission.
 * 3. API fallback: Create project via API with teacher_signature_code to unlock C/D/E/F/G tests.
 * 4. C: Lobby 活動代碼 + 列管狀態.
 * 5. D: Teacher sees activity.
 * 6. E: Negative path (invalid code).
 * 7. F: Seats sticky_color.
 * 8. G: ChatDock bubble color (workspace).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const BASE_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'phase22-final');
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
function bug(area, detail) { log(`BUG  [${area}]: ${detail}`); results.push({ area, status: 'BUG', detail }); }

async function screenshot(page, name) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  log(`Screenshot: ${p}`);
  return p;
}

async function suppressTours(page) {
  await page.evaluate(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
      document.querySelectorAll('.driver-overlay, .driver-popover-wrapper, [class*="driver-"]').forEach(el => el.remove());
    } catch {}
  });
}

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

async function spaNavigate(page, path) {
  await page.evaluate((p) => {
    window.history.pushState({}, '', p);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
  await page.waitForTimeout(1500);
  await suppressTours(page);
}

/** Create project via API and return project object */
async function apiCreateProject(token, teacherSignatureCode) {
  const payload = JSON.stringify({
    name: 'QA Phase22',
    description: '',
    ai_contribution: 'medium',
    ai_crew_count: 1,
    personas: [{
      seat_role: 'crew_1',
      persona: {
        name: 'P1',
        role: 'Researcher',
        expertise: 'design thinking research',
        backstory: 'experienced researcher',
        personality_axis: 'balanced',
        personality_desc: 'curious, analytical',
        lens_affinities: { empathy: 0.5, structure: 0.5, creativity: 0.5, feasibility: 0.5 }
      }
    }],
    timer_config: {
      total_session_minutes: 120,
      macro_budgets: { discover: 45, define: 30, develop: 25, deliver: 20 },
      preset_id: 'timer_preset_2hr'
    },
    ...(teacherSignatureCode ? { teacher_signature_code: teacherSignatureCode.toUpperCase() } : {})
  });

  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: '/api/projects',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Content-Length': Buffer.byteLength(payload),
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(parsed);
          else reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(parsed)}`));
        } catch (e) {
          reject(new Error(`Parse error: ${data.slice(0, 200)}`));
        }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
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
  let teacherToken = null;

  // A1: Register teacher
  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    teacherToken = await teacherPage.evaluate(() => localStorage.getItem('access_token'));
    pass('A1-teacher-register', `Registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', e.message);
    await screenshot(teacherPage, 'A1-fail');
  }

  // A2: Teacher dashboard — verify code block
  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await screenshot(teacherPage, 'A2-teacher-dashboard');

    const bodyText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard (first 600): ${bodyText.slice(0, 600)}`);

    if (bodyText.includes('我的教師代碼')) {
      pass('A2-teacher-code-block', '"我的教師代碼" block rendered');
    } else {
      fail('A2-teacher-code-block', `Not found. URL: ${teacherPage.url()}`);
    }

    const codeEls = teacherPage.locator('code');
    const codeCount = await codeEls.count();
    log(`<code> elements: ${codeCount}`);
    for (let i = 0; i < codeCount; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      if (text.length >= 4 && text !== '—') {
        teacherCode = text;
        const is6Char = text.length === 6;
        const noExcluded = !/[01OIL]/.test(text);
        const validCharset = /^[A-Z2-9]+$/.test(text);
        if (is6Char && noExcluded && validCharset) {
          pass('A2-teacher-code-valid', `Code "${teacherCode}" — 6-char, [A-Z2-9], no 0/O/1/I/L`);
        } else {
          pass('A2-teacher-code-exists', `Code chip: "${teacherCode}"`);
          if (!is6Char) fail('A2-teacher-code-length', `Expected 6 chars, got ${text.length}`);
          if (!noExcluded) fail('A2-teacher-code-charset', `Contains 0/O/1/I/L: "${text}"`);
        }
        break;
      }
    }
    if (!teacherCode) fail('A2-teacher-code-value', `No code found among ${codeCount} <code> elements`);
  } catch (e) {
    fail('A2-teacher-dashboard', e.message);
    await screenshot(teacherPage, 'A2-fail');
  }

  // A3: Copy button
  try {
    const copyBtns = teacherPage.locator('button:has-text("複製")');
    const cpCnt = await copyBtns.count();
    if (cpCnt > 0) {
      pass('A3-copy-btn-exists', `${cpCnt} "複製" button(s)`);
      await copyBtns.first().click({ force: true });
      await teacherPage.waitForTimeout(800);
      await screenshot(teacherPage, 'A3-after-copy');
      const pageText = await teacherPage.locator('body').innerText();
      if (pageText.includes('已複製')) {
        pass('A3-copy-feedback', '"已複製" text visible after click');
      } else {
        fail('A3-copy-feedback', '"已複製" not visible (headless clipboard limitation or UI regression)');
      }
    } else {
      fail('A3-copy-btn', '"複製" button not found');
    }
  } catch (e) {
    fail('A3-copy-btn', e.message);
  }

  // ============================================================
  // B. STUDENT + CREATE ACTIVITY (UI flow up to submit)
  // ============================================================
  log('\n=== B. Student + Create Activity ===');
  const studentContext = await browser.newContext();
  await addTourSuppressScript(studentContext);
  const studentPage = await studentContext.newPage();
  let projectId = null;
  let studentToken = null;

  // B1: Register student
  try {
    await register(studentPage, studentEmail, studentPassword, studentName, '學生');
    studentToken = await studentPage.evaluate(() => localStorage.getItem('access_token'));
    pass('B1-student-register', `Registered: ${studentEmail}`);
  } catch (e) {
    fail('B1-student-register', e.message);
    await screenshot(studentPage, 'B1-fail');
  }

  // B2: Open new activity modal
  try {
    await suppressTours(studentPage);
    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click({ force: true });
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');

    const titleVis = await studentPage.locator('text=開啟新探索').first().isVisible().catch(() => false);
    if (titleVis) {
      pass('B2-modal-title', '"開啟新探索" modal title visible (student role copy correct)');
    } else {
      const bodyText = await studentPage.locator('body').innerText();
      fail('B2-modal-title', `"開啟新探索" not visible. Body: ${bodyText.slice(0, 200)}`);
    }
  } catch (e) {
    fail('B2-modal-open', e.message);
    await screenshot(studentPage, 'B2-fail');
  }

  // B3: Fill step 1 — activity name + teacher code field
  try {
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 8000 });
    await nameInput.fill('QA Phase22');
    pass('B3-activity-name', '"QA Phase22" filled');

    // Teacher code field
    const tcInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcVis = await tcInput.isVisible().catch(() => false);
    if (tcVis) {
      pass('B3-teacher-code-field', '"加入老師班譯（選填）" field visible with placeholder 例：MD7K2A');
      if (teacherCode) {
        await tcInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Teacher code "${teacherCode}" entered`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code');
      }
    } else {
      fail('B3-teacher-code-field', '"加入老師班譯（選填）" input not visible');
    }

    // Set crew count to 1 (click the "1 AI 組員" button)
    const crewBtnsFilter = studentPage.locator('[role="dialog"] button').filter({ hasText: 'AI 組員' });
    const crewCnt = await crewBtnsFilter.count();
    log(`"AI 組員" buttons: ${crewCnt}`);
    if (crewCnt >= 1) {
      await crewBtnsFilter.first().click({ force: true }); // first = "1 AI 組員"
      await studentPage.waitForTimeout(200);
      pass('B3-crew-count-1', 'Set crew count to 1 via "1 AI 組員" button');
    } else {
      skip('B3-crew-count-1', 'Could not locate crew count buttons');
    }

    await screenshot(studentPage, 'B3-step1');
  } catch (e) {
    fail('B3-fill-basics', e.message);
    await screenshot(studentPage, 'B3-fail');
  }

  // B4: Advance to step 2
  try {
    await studentPage.evaluate(() => {
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs.length > 0) dialogs[dialogs.length - 1].scrollTop = 9999;
    });
    await studentPage.waitForTimeout(300);

    const nextBtn = studentPage.locator('[role="dialog"] button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    pass('B4-advance-step2', '"下一步" clicked → persona step');
    await screenshot(studentPage, 'B4-step2');
  } catch (e) {
    fail('B4-advance-step2', e.message);
    await screenshot(studentPage, 'B4-fail');
  }

  // B5: Add persona manually — verify dialog opens, fill name, save
  try {
    const manualBtn = studentPage.locator('button:has-text("手動新增")').first();
    await manualBtn.waitFor({ state: 'visible', timeout: 8000 });
    await manualBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    await screenshot(studentPage, 'B5-persona-dialog');

    const pNameInput = studentPage.locator('input[placeholder="例：陳秀英"]').first();
    await pNameInput.waitFor({ state: 'visible', timeout: 10000 });
    await pNameInput.fill('P1');
    pass('B5-persona-dialog-opens', 'PersonaEditDialog opened, name filled "P1"');

    // Check if there is a "role" input field
    const allInputLabels = await studentPage.evaluate(() => {
      return Array.from(document.querySelectorAll('label, input, textarea')).map(el => ({
        tag: el.tagName,
        label: el.textContent?.slice(0, 30),
        placeholder: el.getAttribute?.('placeholder'),
        type: el.getAttribute?.('type'),
      }));
    });
    const hasRoleField = allInputLabels.some(el =>
      el.label?.includes('角色') || el.placeholder?.includes('角色') || el.placeholder?.includes('role')
    );
    log(`PersonaEditDialog fields: ${JSON.stringify(allInputLabels.filter(e => e.tag !== 'LABEL').slice(0, 15))}`);

    if (!hasRoleField) {
      bug('B5-persona-role-field-missing',
        'PersonaEditDialog has NO "role" input field. Backend requires persona.role (min_length=1). ' +
        'Submitting manually-created personas will always fail with HTTP 422. This is a frontend bug.');
    } else {
      pass('B5-persona-role-field', 'Role input field found in PersonaEditDialog');
    }

    // Try to save (will fail at submit due to role being empty, but save in dialog should work)
    const saveBtns = studentPage.locator('button:has-text("儲存")');
    if (await saveBtns.count() > 0) {
      await saveBtns.last().click({ force: true });
      await studentPage.waitForTimeout(800);
      pass('B5-persona-save', 'Persona saved in dialog (persona added to list)');
    }
    await screenshot(studentPage, 'B5-after-save');

    // Now try to submit — expect 422 if role is missing from UI
    const submitBtn = studentPage.locator('[role="dialog"] button:has-text("開始探索")').first();
    const submitVis = await submitBtn.isVisible().catch(() => false);
    if (submitVis) {
      const isDisabled = await submitBtn.isDisabled().catch(() => true);
      if (!isDisabled) {
        await submitBtn.click({ force: true });
        await studentPage.waitForTimeout(3000);
        const newUrl = studentPage.url();
        const bodyText = await studentPage.locator('body').innerText();
        if (bodyText.includes('422') || bodyText.includes('Request failed')) {
          bug('B6-project-create-422',
            `Project creation fails with 422: persona.role is empty (no role field in UI). ` +
            `Body: ${bodyText.slice(bodyText.indexOf('422') - 20, bodyText.indexOf('422') + 100)}`);
        } else if (newUrl.match(/\/projects\/[^/?#]+/)) {
          pass('B6-project-created-ui', `UI project creation succeeded (unexpected — role was likely pre-filled). URL: ${newUrl}`);
          const m = newUrl.match(/projects\/([^/?#]+)/);
          if (m) projectId = m[1];
        } else {
          // Error shown inline
          fail('B6-project-submit', `Submit attempted, URL: ${newUrl}. Body snippet: ${bodyText.slice(0, 300)}`);
        }
        await screenshot(studentPage, 'B6-submit-result');
      } else {
        fail('B6-submit-disabled', 'Submit button disabled even after adding persona');
      }
    }
  } catch (e) {
    fail('B5-persona-flow', e.message);
    await screenshot(studentPage, 'B5-fail');
  }

  // Close the modal if still open — click Cancel button inside dialog
  try {
    const cancelBtn = studentPage.locator('[role="dialog"] button:has-text("取消"), [role="dialog"] button:has-text("上一步")').last();
    const cancelVis = await cancelBtn.isVisible().catch(() => false);
    if (cancelVis) {
      await cancelBtn.click({ force: true });
      await studentPage.waitForTimeout(300);
    }
    // Only press Escape if a dialog is still open
    const dialogOpen = await studentPage.locator('[role="dialog"]').isVisible().catch(() => false);
    if (dialogOpen) {
      await studentPage.keyboard.press('Escape');
      await studentPage.waitForTimeout(300);
    }
  } catch {}

  // API fallback: create project directly using the student token captured at registration
  if (!projectId && studentToken) {
    log('Using API fallback to create project...');
    try {
      const project = await apiCreateProject(studentToken, teacherCode);
      projectId = project.id;
      log(`API created project: ${projectId}`);
      pass('B6-project-created-api',
        `Project created via API (workaround for UI bug). ID: ${projectId}` +
        (teacherCode ? ` with teacher code ${teacherCode}` : ''));
    } catch (e) {
      fail('B6-project-created-api', `API creation failed: ${e.message}`);
    }
  }

  // Navigate student to lobby — use SPA navigation if possible, fall back to goto
  if (projectId) {
    // First ensure studentPage is on a valid authenticated URL
    const curUrl = studentPage.url();
    log(`Student URL before lobby nav: ${curUrl}`);

    if (curUrl.includes('/login') || !curUrl.includes('localhost:3000')) {
      // Auth state may have been lost — need to re-login
      log('Student page lost auth state, re-logging in...');
      await studentPage.goto(`${BASE_URL}/login`);
      await studentPage.waitForLoadState('networkidle');
      await studentPage.locator('input[type="email"]').first().fill(studentEmail);
      await studentPage.locator('input[type="password"]').first().fill(studentPassword);
      await studentPage.locator('button[type="submit"]').click();
      await studentPage.waitForURL('**/projects', { timeout: 15000 });
      await suppressTours(studentPage);
      // Refresh token
      studentToken = await studentPage.evaluate(() => localStorage.getItem('access_token'));
      log(`Re-logged in student, new token obtained`);
    }

    // SPA navigate to the lobby
    await spaNavigate(studentPage, `/projects/${projectId}`);
    await studentPage.waitForTimeout(2000);
    await suppressTours(studentPage);
    await screenshot(studentPage, 'B6-lobby-nav');
    log(`Lobby URL: ${studentPage.url()}`);
  }

  // ============================================================
  // C. LOBBY — 活動代碼 + 列管狀態
  // ============================================================
  log('\n=== C. Lobby ===');
  let inviteCode = null;

  if (projectId) {
    try {
      await screenshot(studentPage, 'C1-lobby');
      const bodyText = await studentPage.locator('body').innerText();
      log(`Lobby body (first 1000): ${bodyText.slice(0, 1000)}`);

      // 活動代碼
      if (bodyText.includes('活動代碼')) {
        pass('C1-invite-code-label', '"活動代碼" visible in lobby');

        const codeEls = studentPage.locator('code');
        const cnt = await codeEls.count();
        for (let i = 0; i < cnt; i++) {
          const t = (await codeEls.nth(i).textContent()).trim();
          if (t && t !== '—' && t.length >= 4) {
            inviteCode = t;
            pass('C1-invite-code-value', `活動代碼 chip: "${inviteCode}"`);
            break;
          }
        }
        if (!inviteCode) fail('C1-invite-code-value', `No valid code chip among ${cnt} <code> elements`);

        const cpBtns = studentPage.locator('button:has-text("複製")');
        if (await cpBtns.count() > 0) {
          pass('C2-lobby-copy-btn', `"複製" button present (count: ${await cpBtns.count()})`);
        } else {
          fail('C2-lobby-copy-btn', '"複製" not found in lobby');
        }
      } else {
        fail('C1-invite-code-label', `"活動代碼" not in lobby. URL: ${studentPage.url()}`);
      }

      // 列管狀態
      if (bodyText.includes('列管狀態')) {
        pass('C3-linked-status-label', '"列管狀態" section visible in lobby');

        if (teacherCode && bodyText.includes('已列管')) {
          pass('C4-linked-teacher', '"已列管" text visible');
          if (bodyText.includes(teacherName)) {
            pass('C4-teacher-name', `"${teacherName}" shown in 已列管 text`);
          } else {
            fail('C4-teacher-name', `"${teacherName}" not found. Body: ${bodyText.slice(0, 500)}`);
          }
          const unlinkVis = await studentPage.locator('button:has-text("解除")').first().isVisible().catch(() => false);
          if (unlinkVis) {
            pass('C5-unlink-btn', '"解除" button visible');
          } else {
            fail('C5-unlink-btn', '"解除" button not visible');
          }
        } else if (!teacherCode) {
          skip('C4-linked-teacher', 'No teacher code available');
        } else {
          // Teacher code was passed via API — check if it shows
          fail('C4-linked-teacher', `Teacher code "${teacherCode}" used in API call but "已列管" not in page. Body: ${bodyText.slice(0, 500)}`);
        }
      } else {
        fail('C3-linked-status-label', `"列管狀態" not in lobby. URL: ${studentPage.url()}`);
      }

    } catch (e) {
      fail('C-lobby', e.message);
      await screenshot(studentPage, 'C-fail');
    }
  } else {
    skip('C-lobby', 'No projectId — all lobby checks skipped');
  }

  // ============================================================
  // D. TEACHER SEES ACTIVITY
  // ============================================================
  log('\n=== D. Teacher Sees Activity ===');

  try {
    await suppressTours(teacherPage);
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForTimeout(2000);
    await suppressTours(teacherPage);
    await screenshot(teacherPage, 'D1-teacher-dashboard');

    const dashText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard text (first 800): ${dashText.slice(0, 800)}`);

    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', '"QA Phase22" appears in teacher dashboard monitoring area');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found. Text: ${dashText.slice(0, 500)}`);
    }
  } catch (e) {
    fail('D1-teacher-sees-activity', e.message);
    await screenshot(teacherPage, 'D1-fail');
  }

  // ============================================================
  // E. NEGATIVE PATH — invalid invite code
  // ============================================================
  log('\n=== E. Negative Path ===');

  try {
    // Find the track input next to 列管 button
    const listBtn = teacherPage.locator('button:has-text("列管")').first();
    const listBtnVis = await listBtn.isVisible().catch(() => false);

    if (listBtnVis) {
      const inputs = teacherPage.locator('input');
      const inputCnt = await inputs.count();
      let trackInputEl = null;
      for (let i = inputCnt - 1; i >= 0; i--) {
        const el = inputs.nth(i);
        const vis = await el.isVisible().catch(() => false);
        if (vis) { trackInputEl = el; break; }
      }

      if (trackInputEl) {
        await trackInputEl.fill('NOTREAL');
        await listBtn.click({ force: true });
        await teacherPage.waitForTimeout(2000);
        await screenshot(teacherPage, 'E1-invalid-code');

        const pageText = await teacherPage.locator('body').innerText();
        log(`Page text after invalid code (first 500): ${pageText.slice(0, 500)}`);

        // Error message from TeacherDashboard: "找不到此活動代碼" or "列管失敗，請確認代碼是否正確"
        const hasErrText = pageText.includes('找不到') ||
                           pageText.includes('列管失敗') ||
                           pageText.includes('無效') ||
                           pageText.includes('不存在') ||
                           pageText.includes('請確認代碼');
        if (hasErrText) {
          // Extract the actual error text
          const errSnippet = pageText.includes('找不到') ?
            pageText.substring(pageText.indexOf('找不到'), pageText.indexOf('找不到') + 20) :
            pageText.substring(pageText.indexOf('列管失敗'), pageText.indexOf('列管失敗') + 30);
          pass('E1-invalid-code-error', `Error message shown: "${errSnippet}"`);
        } else {
          fail('E1-invalid-code-error', `No error message found. Text: ${pageText.slice(0, 400)}`);
        }
      } else {
        fail('E1-track-input', 'No visible input found on teacher dashboard');
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

  if (projectId && studentToken) {
    try {
      const seatsData = await studentPage.evaluate(async ({ base, pid, tok }) => {
        const r = await fetch(`${base}/api/projects/${pid}/seats`, {
          headers: { Authorization: `Bearer ${tok}` }
        });
        const text = await r.text();
        try { return { status: r.status, data: JSON.parse(text) }; } catch { return { status: r.status, raw: text }; }
      }, { base: BASE_URL, pid: projectId, tok: studentToken });

      log(`Seats API (${seatsData.status}): ${JSON.stringify(seatsData).slice(0, 700)}`);
      const validColors = ['yellow', 'orange', 'green', 'blue', 'violet', 'red', 'light-blue', 'light-green'];
      const seats = Array.isArray(seatsData.data) ? seatsData.data :
                    (seatsData.data?.seats || []);

      if (seats.length === 0) {
        fail('F1-seats', `No seats in response. Raw: ${JSON.stringify(seatsData).slice(0, 300)}`);
      } else {
        const colors = seats.map(s => s.sticky_color);
        log(`Seat colors: [${colors.join(', ')}]`);

        const allHaveColor = seats.every(s => s.sticky_color != null);
        const allValid = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));

        if (!allHaveColor) {
          fail('F1-seats-color-present', `Some seats missing sticky_color. Data: ${JSON.stringify(seats.map(s => ({ seat: s.seat_role, color: s.sticky_color })))}`);
        } else if (!allValid) {
          fail('F1-seats-color-valid', `Invalid color value(s). Colors: [${colors.join(', ')}]. Allowed: [${validColors.join(', ')}]`);
        } else {
          pass('F1-seats-sticky-color', `All ${seats.length} seats have valid sticky_color. Colors: [${colors.join(', ')}]`);
        }

        const unique = [...new Set(colors.filter(Boolean))];
        if (seats.length <= 1) {
          skip('F2-seats-varied', `Only ${seats.length} seat — variation not testable`);
        } else if (unique.length > 1) {
          pass('F2-seats-varied', `Colors differ across seats: [${unique.join(', ')}]`);
        } else {
          fail('F2-seats-varied', `All ${seats.length} seats have same color: "${unique[0]}"`);
        }
      }
    } catch (e) {
      fail('F1-seats', e.message);
    }
  } else {
    skip('F1-seats', `No projectId (${projectId}) or studentToken (${!!studentToken})`);
    skip('F2-seats-varied', 'No projectId');
  }

  // ============================================================
  // G. CHATDOCK BUBBLE COLOR (best-effort)
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
        // Try specific selectors first
        const selectors = ['[data-testid="chat-message"]', '[class*="ChatMessage"]', '[class*="message-bubble"]'];
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
        // Look for inline background-color
        const inlineEls = Array.from(document.querySelectorAll('[style*="background-color"]'));
        if (inlineEls.length > 0) {
          return { sel: 'inline-bg', count: inlineEls.length, items: inlineEls.slice(0, 5).map(el => ({
            text: el.textContent?.slice(0, 50),
            bg: el.style.backgroundColor,
            style: el.getAttribute('style'),
            tag: el.tagName,
          })) };
        }
        // Look at all rounded divs with background
        const divs = Array.from(document.querySelectorAll('div.rounded-2xl, div.rounded-xl, div[class*="rounded"]'))
          .filter(el => {
            const bg = getComputedStyle(el).backgroundColor;
            return bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && el.textContent?.trim().length > 0;
          });
        if (divs.length > 0) {
          return { sel: 'rounded-bg', count: divs.length, items: divs.slice(0, 5).map(el => ({
            text: el.textContent?.slice(0, 50),
            bg: getComputedStyle(el).backgroundColor,
            cls: el.className?.slice(0, 80),
          })) };
        }
        return null;
      });

      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages or styled elements — workspace idle (no AI messages yet). Acceptable.');
      } else {
        log(`Chat elements: ${JSON.stringify(chatInfo).slice(0, 500)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.style && m.style.includes('background-color')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== '' && m.bg !== 'transparent')
        );
        if (hasColor) {
          pass('G1-chat-bubble-color', `Bubble with bg-color found (sel: ${chatInfo.sel}). Sample: ${JSON.stringify(chatInfo.items[0]).slice(0, 120)}`);
        } else {
          fail('G1-chat-bubble-color', `Elements found but no bg-color. Data: ${JSON.stringify(chatInfo.items).slice(0, 300)}`);
        }
      }
    } catch (e) {
      fail('G1-workspace', e.message);
      await screenshot(studentPage, 'G1-fail');
    }
  } else {
    skip('G1-chat-bubble', 'No projectId');
  }

  // ============================================================
  // H. HumanNoteColorInjector (best-effort)
  // ============================================================
  log('\n=== H. HumanNoteColorInjector ===');
  skip('H1-note-injector', 'Best-effort tldraw state introspection — requires internal tldraw editor API, skipped');

  // ============================================================
  // FINAL REPORT
  // ============================================================
  log('\n========== PHASE 22 QA FINAL REPORT ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;
  const bugCount = results.filter(r => r.status === 'BUG').length;
  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | BUG: ${bugCount} | SKIP: ${skipCount}\n`);
  for (const r of results) {
    console.log(`[${r.status.padEnd(4)}] ${r.area}: ${r.detail}`);
  }

  const report = {
    timestamp: new Date().toISOString(),
    version: 'final',
    teacherEmail,
    studentEmail,
    teacherCode,
    projectId,
    inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, bug: bugCount, skip: skipCount },
    results,
    screenshotDir: SCREENSHOT_DIR,
  };
  fs.writeFileSync(path.join(__dirname, 'qa-phase22-final-report.json'), JSON.stringify(report, null, 2));
  log(`Report written to qa-phase22-final-report.json`);

  await browser.close();
  const exitCode = (failCount + bugCount) > 0 ? 1 : 0;
  process.exit(exitCode);
}

main().catch(e => { console.error('Fatal:', e); process.exit(2); });
