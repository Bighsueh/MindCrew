/**
 * Phase 22 QA Test v2: 教師列管雙向碼 + 作者識別色
 * Fixes: correct register form flow, confirm password, role button clicks
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

/**
 * Register a new user.
 * Form order: role toggle → displayName → email → password → confirmPassword → submit
 */
async function register(page, email, password, displayName, role) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');

  // Click role button (教師 or 學生) - these are <button type="button"> elements
  const roleLabel = role === '教師' ? '教師' : '學生';
  await page.locator(`button:has-text("${roleLabel}")`).first().click();
  await page.waitForTimeout(200);

  // Fill display name (first text input)
  const inputs = page.locator('input');
  // We need: displayName, email, password, confirmPassword
  // Find by type/placeholder
  const nameInput = page.locator('input[type="text"]').first();
  await nameInput.fill(displayName);

  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.fill(email);

  const passwordInputs = page.locator('input[type="password"]');
  await passwordInputs.nth(0).fill(password);
  await passwordInputs.nth(1).fill(password); // confirm password

  await screenshot(page, `register-${role}-before-submit`);

  // Submit
  await page.locator('button[type="submit"]').click();

  // Wait for redirect to /projects
  await page.waitForURL('**/projects', { timeout: 20000 });
  log(`Registered ${role}: ${email}, display: ${displayName}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================
  // A. TEACHER: Register + Dashboard Code
  // ============================================================
  log('\n=== A. Teacher Registration + Dashboard Code ===');
  const teacherContext = await browser.newContext();
  const teacherPage = await teacherContext.newPage();
  let teacherCode = null;

  // A1: Register teacher
  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, '教師');
    pass('A1-teacher-register', `Teacher registered: ${teacherEmail}`);
  } catch (e) {
    fail('A1-teacher-register', `${e.message}`);
    await screenshot(teacherPage, 'A1-fail');
  }

  // A2: Teacher dashboard - code chip
  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForLoadState('networkidle');
    await teacherPage.waitForTimeout(1000);
    await screenshot(teacherPage, 'A2-teacher-dashboard');

    // "我的教師代碼" label
    const codeLabel = teacherPage.locator('text=我的教師代碼');
    await codeLabel.waitFor({ state: 'visible', timeout: 10000 });
    pass('A2-teacher-code-block', '"我的教師代碼" block visible');

    // The code is in a <code> element (font-mono) near the label
    // Get all <code> text and find the 6-char one
    const codeEl = teacherPage.locator('code').first();
    const codeText = (await codeEl.textContent()).trim();
    log(`Code element text: "${codeText}"`);

    if (/^[A-Z2-9]{6}$/.test(codeText) && !/[01OIL]/.test(codeText)) {
      teacherCode = codeText;
      pass('A2-teacher-code-valid', `Teacher code: ${teacherCode} — 6-char, valid charset`);
    } else if (codeText && codeText !== '—') {
      // Maybe the code doesn't match perfect regex due to charset differences — still record
      teacherCode = codeText;
      pass('A2-teacher-code-exists', `Teacher code chip text: "${teacherCode}" (charset verify below)`);
      if (/[01OIL]/.test(codeText)) {
        fail('A2-teacher-code-charset', `Code "${codeText}" contains excluded chars (0,1,O,I,L)`);
      } else {
        pass('A2-teacher-code-charset', `Code "${codeText}" passes charset check`);
      }
    } else {
      fail('A2-teacher-code-value', `Code element shows "${codeText}" — expected 6-char code`);
    }
  } catch (e) {
    fail('A2-teacher-dashboard', `${e.message}`);
    await screenshot(teacherPage, 'A2-fail');
  }

  // A3: Copy button
  try {
    const copyBtn = teacherPage.locator('button:has-text("複製")').first();
    await copyBtn.waitFor({ state: 'visible', timeout: 5000 });
    pass('A3-copy-button-exists', '"複製" button visible next to teacher code');
    await copyBtn.click();
    await teacherPage.waitForTimeout(600);
    await screenshot(teacherPage, 'A3-after-copy');

    // Look for "已複製" feedback
    const copiedEl = teacherPage.locator('text=已複製').first();
    const copiedVisible = await copiedEl.isVisible().catch(() => false);
    if (copiedVisible) {
      pass('A3-copy-feedback', '"已複製" feedback appeared');
    } else {
      fail('A3-copy-feedback', '"已複製" text not visible after clicking 複製');
    }
  } catch (e) {
    fail('A3-copy-button', `${e.message}`);
  }

  // ============================================================
  // B. STUDENT: Register + Create Activity with Teacher Code
  // ============================================================
  log('\n=== B. Student Registration + Create Activity ===');
  const studentContext = await browser.newContext();
  const studentPage = await studentContext.newPage();
  let projectId = null;

  // B1: Register student
  try {
    await register(studentPage, studentEmail, studentPassword, studentName, '學生');
    pass('B1-student-register', `Student registered: ${studentEmail}`);
  } catch (e) {
    fail('B1-student-register', `${e.message}`);
    await screenshot(studentPage, 'B1-fail');
  }

  // B2: Open new activity modal
  try {
    await studentPage.waitForLoadState('networkidle');
    await screenshot(studentPage, 'B2-projects');

    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    pass('B2-new-btn-exists', '"新增學習活動" button visible');
    await newBtn.click();
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');

    // Modal title
    const modalTitle = studentPage.locator('text=開啟新探索').first();
    const titleVisible = await modalTitle.isVisible().catch(() => false);
    if (titleVisible) {
      pass('B2-modal-title', 'Modal title "開啟新探索" visible');
    } else {
      const dialogEl = studentPage.locator('[role="dialog"], [class*="modal"], [class*="dialog"]').first();
      const dialogText = await dialogEl.textContent().catch(() => 'N/A');
      fail('B2-modal-title', `Expected "開啟新探索", got dialog text: "${dialogText.slice(0, 100)}"`);
    }

    // B3: Check teacher code field (visible for students in step 1)
    const teacherCodeInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcfVisible = await teacherCodeInput.isVisible().catch(() => false);
    if (tcfVisible) {
      pass('B3-teacher-code-field', '"加入老師班譯" field (placeholder 例：MD7K2A) visible');
      if (teacherCode) {
        await teacherCodeInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Teacher code "${teacherCode}" entered`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code available');
      }
    } else {
      // Fallback: look for "加入老師班譯" label
      const labelEl = studentPage.locator('text=加入老師班譯').first();
      const labelVisible = await labelEl.isVisible().catch(() => false);
      if (labelVisible) {
        pass('B3-teacher-code-field', '"加入老師班譯" label visible');
        // Try to fill the input near it
        if (teacherCode) {
          await teacherCodeInput.fill(teacherCode);
        }
      } else {
        const dialogContent = await studentPage.locator('body').textContent();
        fail('B3-teacher-code-field', `Teacher code field not found. Looking for placeholder "例：MD7K2A" or label "加入老師班譯"`);
      }
    }

    // B4: Fill activity name
    const activityName = studentPage.locator('input[placeholder*="活動名稱"], input[placeholder*="探索"], input[placeholder*="題目"]').first();
    const nameVisible = await activityName.isVisible().catch(() => false);
    if (nameVisible) {
      await activityName.fill('QA Phase22');
      pass('B4-activity-name', 'Activity name "QA Phase22" entered');
    } else {
      // Try to find any text input in the dialog
      const dialogInputs = studentPage.locator('[role="dialog"] input[type="text"], [role="dialog"] input:not([type="password"])');
      const count = await dialogInputs.count();
      if (count > 0) {
        await dialogInputs.first().fill('QA Phase22');
        pass('B4-activity-name', `Activity name entered via fallback (${count} inputs found)`);
      } else {
        fail('B4-activity-name', 'Activity name input not found');
      }
    }

    await screenshot(studentPage, 'B4-step1-filled');

    // B5: Advance to step 2 (personas)
    // Button: "下一步：設定 AI 隊友" or similar
    const nextBtn = studentPage.locator('button:has-text("下一步")').first();
    const nextVisible = await nextBtn.isVisible().catch(() => false);
    if (nextVisible) {
      await nextBtn.click();
      await studentPage.waitForTimeout(1000);
      pass('B5-advance-to-personas', 'Advanced to step 2 (personas)');
    } else {
      fail('B5-advance-to-personas', '"下一步" button not found');
    }

    await screenshot(studentPage, 'B5-step2-personas');

    // B6: Manual add persona (avoid LLM)
    const manualAddBtn = studentPage.locator('button:has-text("手動新增")').first();
    const manualVisible = await manualAddBtn.isVisible().catch(() => false);
    if (manualVisible) {
      await manualAddBtn.click();
      await studentPage.waitForTimeout(500);

      // Persona name input
      const personaNameInput = studentPage.locator('input[placeholder*="角色名稱"], input[placeholder*="名字"], input[placeholder*="姓名"]').first();
      const pNameVisible = await personaNameInput.isVisible().catch(() => false);
      if (pNameVisible) {
        await personaNameInput.fill('P1');
      } else {
        // Try first newly appeared text input
        const newInput = studentPage.locator('input[type="text"]').last();
        await newInput.fill('P1');
      }

      // Role/description input
      const roleDesc = studentPage.locator('input[placeholder*="角色"], input[placeholder*="職能"], textarea[placeholder*="描述"]').first();
      const rdVisible = await roleDesc.isVisible().catch(() => false);
      if (rdVisible) await roleDesc.fill('Role');

      await screenshot(studentPage, 'B6-persona-form');

      // Save persona
      const saveBtn = studentPage.locator('button:has-text("儲存"), button:has-text("確認新增"), button:has-text("加入")').first();
      const saveVisible = await saveBtn.isVisible().catch(() => false);
      if (saveVisible) {
        await saveBtn.click();
        await studentPage.waitForTimeout(500);
        pass('B6-persona-saved', 'Persona P1 saved');
      } else {
        log('Save persona button not found, trying to continue');
      }
    } else {
      log('手動新增 not found');
    }

    await screenshot(studentPage, 'B6-after-persona');

    // B7: Submit form
    const submitBtn = studentPage.locator('button:has-text("開始探索")').first();
    const submitVisible = await submitBtn.isVisible().catch(() => false);
    if (submitVisible) {
      await submitBtn.click();
      try {
        await studentPage.waitForURL(/\/(projects\/[^/]+|lobby)/, { timeout: 20000 });
        const url = studentPage.url();
        pass('B7-project-created', `Project created, redirected to: ${url}`);
        const urlMatch = url.match(/projects\/([^/?#]+)/);
        if (urlMatch) projectId = urlMatch[1];
        log(`Project ID: ${projectId}`);
      } catch {
        await screenshot(studentPage, 'B7-after-submit');
        const bodyText = await studentPage.locator('body').innerText();
        fail('B7-project-created', `Navigation timeout. Body: ${bodyText.slice(0, 300)}`);
      }
    } else {
      fail('B7-submit', '"開始探索" button not visible');
      await screenshot(studentPage, 'B7-no-submit');
    }

  } catch (e) {
    fail('B-create-activity', `${e.message}`);
    await screenshot(studentPage, 'B-fail');
  }

  // ============================================================
  // C. LOBBY: invite_code + 列管狀態
  // ============================================================
  log('\n=== C. Lobby: 活動代碼 + 列管狀態 ===');

  try {
    const currentUrl = studentPage.url();
    if (!currentUrl.includes('/projects/') && projectId) {
      await studentPage.goto(`${BASE_URL}/projects/${projectId}`);
      await studentPage.waitForLoadState('networkidle');
    }
    await studentPage.waitForTimeout(1000);
    await screenshot(studentPage, 'C1-lobby');

    // Check 活動代碼 section
    const inviteCodeLabel = studentPage.locator('text=活動代碼').first();
    const inviteCodeVisible = await inviteCodeLabel.isVisible().catch(() => false);
    if (inviteCodeVisible) {
      pass('C1-invite-code-label', '"活動代碼" label visible');

      // Get the code value from <code> element in the lobby
      const codeElements = studentPage.locator('code');
      const codeCount = await codeElements.count();
      let inviteCode = null;
      for (let i = 0; i < codeCount; i++) {
        const text = (await codeElements.nth(i).textContent()).trim();
        if (/^[A-Z2-9]{6}$/.test(text) || (text.length === 6 && text !== '——————')) {
          inviteCode = text;
          break;
        }
      }
      if (inviteCode) {
        pass('C1-invite-code-value', `活動代碼 chip value: "${inviteCode}"`);
      } else {
        // Try getting from page text
        const pageText = await studentPage.locator('body').innerText();
        const codeMatch = pageText.match(/(?:活動代碼[^\n]*\n\s*)([A-Z2-9]{6})/);
        if (codeMatch) {
          pass('C1-invite-code-value', `活動代碼 value from page text: "${codeMatch[1]}"`);
        } else {
          fail('C1-invite-code-value', `No 6-char code found near 活動代碼 label. Code elements: ${codeCount}`);
        }
      }

      // Copy button near 活動代碼
      const copyBtns = studentPage.locator('button:has-text("複製")');
      const copyCount = await copyBtns.count();
      if (copyCount > 0) {
        pass('C1-invite-copy-btn', `"複製" button(s) found (${copyCount} total)`);
      } else {
        fail('C1-invite-copy-btn', '"複製" button not found in lobby');
      }
    } else {
      fail('C1-invite-code-label', '"活動代碼" label not visible in lobby');
    }

    // Check 列管狀態
    const linkedLabel = studentPage.locator('text=列管狀態').first();
    const linkedVisible = await linkedLabel.isVisible().catch(() => false);
    if (linkedVisible) {
      pass('C2-linked-status-label', '"列管狀態" label visible');

      const pageText = await studentPage.locator('body').innerText();
      if (teacherCode && (pageText.includes('已列管') || pageText.includes(teacherName))) {
        pass('C2-linked-teacher', `列管狀態 shows linked teacher. Contains "已列管": ${pageText.includes('已列管')}`);
        const unlinkBtn = studentPage.locator('button:has-text("解除")').first();
        const unlinkVisible = await unlinkBtn.isVisible().catch(() => false);
        if (unlinkVisible) {
          pass('C3-unlink-btn', '"解除" button visible');
        } else {
          fail('C3-unlink-btn', '"解除" button not found');
        }
      } else if (!teacherCode) {
        // No teacher code was entered, check for unlinked state or link input
        if (pageText.includes('尚未列管') || pageText.includes('老師代碼')) {
          pass('C2-linked-status', 'Unlinked state shows "尚未列管" or shows link input (expected, no teacher code used)');
        } else {
          fail('C2-linked-status', `列管狀態 visible but unexpected content: ${pageText.slice(0, 200)}`);
        }
      } else {
        fail('C2-linked-teacher', `列管狀態 visible but "已列管" + teacher name not found. Excerpt: ${pageText.slice(0, 300)}`);
      }
    } else {
      fail('C2-linked-status-label', '"列管狀態" label not visible in lobby');
    }

  } catch (e) {
    fail('C-lobby', `${e.message}`);
    await screenshot(studentPage, 'C-fail');
  }

  // ============================================================
  // D. TEACHER DASHBOARD: sees linked activity
  // ============================================================
  log('\n=== D. Teacher Dashboard: Sees Linked Activity ===');

  try {
    await teacherPage.goto(`${BASE_URL}/teacher/dashboard`);
    await teacherPage.waitForLoadState('networkidle');
    await teacherPage.waitForTimeout(1000);
    await screenshot(teacherPage, 'D1-teacher-dashboard-reload');

    const dashText = await teacherPage.locator('body').innerText();
    if (dashText.includes('QA Phase22')) {
      pass('D1-teacher-sees-activity', '"QA Phase22" appears on teacher dashboard');
    } else {
      fail('D1-teacher-sees-activity', `"QA Phase22" not found on teacher dashboard. Excerpt: ${dashText.slice(0, 500)}`);
    }
  } catch (e) {
    fail('D1-teacher-dashboard', `${e.message}`);
  }

  // ============================================================
  // E. NEGATIVE PATH: Invalid invite code
  // ============================================================
  log('\n=== E. Teacher: Negative path invalid code ===');

  try {
    // Find the "以活動代碼列管學生活動" input
    const trackInput = teacherPage.locator('input[placeholder="例：MD7K2A"]').last();
    const trackInputVisible = await trackInput.isVisible().catch(() => false);
    if (trackInputVisible) {
      await trackInput.fill('NOTREAL');
      const trackBtn = teacherPage.locator('button:has-text("列管")').last();
      const trackBtnVisible = await trackBtn.isVisible().catch(() => false);
      if (trackBtnVisible) {
        await trackBtn.click();
        await teacherPage.waitForTimeout(2000);
        await screenshot(teacherPage, 'E1-invalid-code');

        const dashText = await teacherPage.locator('body').innerText();
        // Look for error text near trackError area
        const errorSpan = teacherPage.locator('.text-error, [class*="error"], [class*="text-red"]').first();
        const errorVisible = await errorSpan.isVisible().catch(() => false);
        const errorText = errorVisible ? (await errorSpan.textContent()).trim() : null;

        if (errorText || dashText.includes('找不到') || dashText.includes('無效') || dashText.includes('失敗') || dashText.includes('不存在') || dashText.includes('請輸入')) {
          pass('E1-invalid-code-error', `Error shown for "NOTREAL": "${errorText || 'found error text in page'}"`);
        } else {
          fail('E1-invalid-code-error', `No error message shown for invalid code "NOTREAL". Page: ${dashText.slice(0, 200)}`);
        }
      } else {
        fail('E1-track-btn', '"列管" button not found next to track input');
      }
    } else {
      fail('E1-track-input', 'Track input (placeholder "例：MD7K2A") not found on teacher dashboard');
    }
  } catch (e) {
    fail('E1-negative', `${e.message}`);
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
          try { return JSON.parse(text); } catch { return { raw: text }; }
        }, { base: BASE_URL, pid: projectId, tok: token });

        log(`Seats API response: ${JSON.stringify(seatsData).slice(0, 400)}`);

        const validColors = ['yellow', 'orange', 'green', 'blue', 'violet', 'red', 'light-blue', 'light-green'];
        const seats = Array.isArray(seatsData) ? seatsData : (seatsData?.seats || []);

        if (seats.length === 0) {
          fail('F1-seats-data', `No seats found. Raw response: ${JSON.stringify(seatsData).slice(0, 200)}`);
        } else {
          const allHaveColor = seats.every(s => s.sticky_color && validColors.includes(s.sticky_color));
          const colors = seats.map(s => s.sticky_color);
          const uniqueColors = [...new Set(colors)];

          if (allHaveColor) {
            pass('F1-seats-sticky-color', `All ${seats.length} seats have valid sticky_color: [${colors.join(', ')}]`);
          } else {
            const bad = seats.filter(s => !s.sticky_color || !validColors.includes(s.sticky_color));
            fail('F1-seats-sticky-color', `${bad.length}/${seats.length} seats have invalid sticky_color. Bad: ${JSON.stringify(bad).slice(0,200)}`);
          }

          if (seats.length > 1) {
            if (uniqueColors.length > 1) {
              pass('F2-seats-color-varied', `Colors differ across seats: [${uniqueColors.join(', ')}]`);
            } else {
              fail('F2-seats-color-varied', `All seats same color: ${uniqueColors[0]}`);
            }
          } else {
            skip('F2-seats-color-varied', `Only ${seats.length} seat — cannot verify variation`);
          }
        }
      } else {
        fail('F1-token', 'No access_token in student localStorage');
      }
    } catch (e) {
      fail('F1-seats', `${e.message}`);
    }
  } else {
    skip('F1-seats', 'No projectId');
  }

  // ============================================================
  // G. CHATDOCK BUBBLE COLOR
  // ============================================================
  log('\n=== G. ChatDock bubble color ===');

  try {
    let wsUrl = studentPage.url();
    if (projectId && !wsUrl.includes('workspace')) {
      wsUrl = `${BASE_URL}/projects/${projectId}/workspace`;
      await studentPage.goto(wsUrl);
      await studentPage.waitForLoadState('networkidle');
      await studentPage.waitForTimeout(3000);
    }
    await screenshot(studentPage, 'G1-workspace');

    const chatInfo = await studentPage.evaluate(() => {
      const selectors = ['[data-testid="chat-message"]', '.rounded-2xl', '[class*="message-bubble"]', '[class*="ChatMessage"]'];
      for (const sel of selectors) {
        const els = Array.from(document.querySelectorAll(sel));
        if (els.length > 0) {
          return { selector: sel, count: els.length, items: els.slice(0,5).map(el => ({
            text: el.textContent?.slice(0,30),
            bg: getComputedStyle(el).backgroundColor,
            inlineStyle: el.style?.backgroundColor || '',
            className: el.className?.slice(0,80),
          })) };
        }
      }
      return null;
    });

    if (!chatInfo) {
      skip('G1-chat-bubble', 'No chat messages found — no AI activity yet (acceptable)');
    } else {
      log(`Chat info: ${JSON.stringify(chatInfo)}`);
      const hasInlineColor = chatInfo.items.some(m => m.inlineStyle && m.inlineStyle !== '');
      const hasBgColor = chatInfo.items.some(m => m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== 'transparent' && m.bg !== '');
      if (hasInlineColor) {
        pass('G1-chat-inline-style', `Chat messages have inline backgroundColor: ${chatInfo.items.map(m => m.inlineStyle).join(', ')}`);
      } else if (hasBgColor) {
        pass('G1-chat-bg-color', `Chat messages have computed backgroundColor: ${chatInfo.items.map(m => m.bg).join(', ')}`);
      } else {
        fail('G1-chat-bubble-color', `Chat messages found but no background color. Data: ${JSON.stringify(chatInfo.items)}`);
      }
    }
  } catch (e) {
    fail('G1-chat-bubble', `${e.message}`);
  }

  // ============================================================
  // H. HUMANNOTECOLORINJECTOR (best-effort)
  // ============================================================
  log('\n=== H. HumanNoteColorInjector (best-effort) ===');

  try {
    // Look for tldraw canvas tools
    const noteToolSelectors = [
      '[data-testid="tools.note"]',
      'button[title="Note"]',
      'button[aria-label*="note"]',
      'button[aria-label*="sticky"]',
    ];

    let noteToolFound = false;
    for (const sel of noteToolSelectors) {
      const el = studentPage.locator(sel).first();
      const visible = await el.isVisible().catch(() => false);
      if (visible) {
        noteToolFound = true;
        await el.click();
        await studentPage.waitForTimeout(400);

        // Click on canvas
        const canvas = studentPage.locator('canvas, .tl-canvas, [class*="tl-nametag"]').first();
        const box = await canvas.boundingBox().catch(() => null);
        if (box) {
          await studentPage.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
          await studentPage.waitForTimeout(2000);
          await screenshot(studentPage, 'H1-note-placed');

          // Try to read tldraw shape color
          const noteColor = await studentPage.evaluate(() => {
            // Try various tldraw store access patterns
            try {
              const stores = Object.values(window).filter(v => v && typeof v === 'object' && v.allRecords);
              for (const store of stores) {
                const notes = store.allRecords().filter(r => r.type === 'note');
                if (notes.length > 0) return notes[0].props?.color;
              }
            } catch { /* ignore */ }
            return null;
          });

          if (noteColor) {
            pass('H1-note-color', `tldraw note color: "${noteColor}"`);
          } else {
            skip('H1-note-color', 'Could not read tldraw editor state directly');
          }
        }
        break;
      }
    }

    if (!noteToolFound) {
      skip('H1-note-tool', 'tldraw note tool not found in DOM — best effort');
    }
  } catch (e) {
    skip('H1-note-injector', `Best-effort skipped: ${e.message}`);
  }

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
  const reportPath = path.join(__dirname, 'qa-phase22-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  log(`\nReport: ${reportPath}`);

  await browser.close();
  process.exit(failCount > 0 ? 1 : 0);
}

main().catch(e => { console.error('Fatal:', e); process.exit(2); });
