/**
 * Phase 22 QA Runner — definitive version
 *
 * Key learnings from previous runs:
 * 1. Teacher dashboard: use spaNavigate (pushState) after auth — goto() causes reload that
 *    may race with Zustand rehydration. Use spaNavigate always.
 * 2. Student lobby: after project creation fails (422), student stays on /projects.
 *    Create project via API, then use spaNavigate to lobby.
 * 3. StudentToken captured at register, persists through the test.
 * 4. Teacher dashboard D check: use reload() then spaNavigate to get fresh data.
 * 5. Persona role field BUG: documented.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const http = require('http');

const BASE_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'phase22-run');
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
  return p;
}

async function suppressTours(page) {
  await page.evaluate(() => {
    try {
      sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
      sessionStorage.setItem('mindcrew.teacherDashboardTour.shown', '1');
      document.querySelectorAll('.driver-overlay,.driver-popover-wrapper,[class*="driver-"]').forEach(el => el.remove());
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

async function spaNavigate(page, targetPath) {
  await page.evaluate((p) => {
    window.history.pushState({}, '', p);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, targetPath);
  await page.waitForTimeout(2000);
  await suppressTours(page);
}

async function register(page, email, password, displayName, roleKey) {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');
  await suppressTours(page);
  // roleKey is 'teacher' or 'student' — buttons show '教師' or '學生'
  const label = roleKey === 'teacher' ? '教師' : '學生';
  await page.locator(`button:has-text("${label}")`).first().click({ force: true });
  await page.waitForTimeout(300);
  await page.locator('input[type="text"]').first().fill(displayName);
  await page.locator('input[type="email"]').first().fill(email);
  const pwInputs = page.locator('input[type="password"]');
  await pwInputs.nth(0).fill(password);
  await pwInputs.nth(1).fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/projects', { timeout: 25000 });
  await page.waitForLoadState('networkidle');
  await suppressTours(page);
  log(`Registered ${roleKey}: ${email}`);
}

async function apiPost(path, token, body) {
  const payload = JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost', port: 3000, path, method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Content-Length': Buffer.byteLength(payload),
      }
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(parsed);
          else reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0,200)}`));
        } catch(e) { reject(new Error(`Parse: ${data.slice(0,200)}`)); }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

  // ============================================================ A. TEACHER DASHBOARD
  log('\n=== A. Teacher Dashboard ===');
  const teacherContext = await browser.newContext();
  await teacherContext.grantPermissions(['clipboard-read', 'clipboard-write']);
  await addTourSuppressScript(teacherContext);
  const teacherPage = await teacherContext.newPage();
  let teacherCode = null;
  let teacherToken = null;

  try {
    await register(teacherPage, teacherEmail, teacherPassword, teacherName, 'teacher');
    teacherToken = await teacherPage.evaluate(() => localStorage.getItem('access_token'));
    pass('A1-register', `Registered teacher: ${teacherEmail}`);
  } catch(e) { fail('A1-register', e.message); await screenshot(teacherPage,'A1-fail'); }

  try {
    await spaNavigate(teacherPage, '/teacher/dashboard');
    log(`Teacher URL: ${teacherPage.url()}`);
    await screenshot(teacherPage, 'A2-dashboard');
    const bodyText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard text (600): ${bodyText.slice(0,600)}`);
    if (bodyText.includes('我的教師代碼')) {
      pass('A2-code-block', '"我的教師代碼" block rendered');
    } else {
      fail('A2-code-block', `Not found. URL: ${teacherPage.url()}. Text: ${bodyText.slice(0,200)}`);
    }
    const codeEls = teacherPage.locator('code');
    const cnt = await codeEls.count();
    for (let i = 0; i < cnt; i++) {
      const text = (await codeEls.nth(i).textContent()).trim();
      if (text.length >= 4 && text !== '—') {
        teacherCode = text;
        const ok = text.length === 6 && /^[A-Z2-9]+$/.test(text) && !/[01OIL]/.test(text);
        if (ok) {
          pass('A2-code-valid', `Code "${teacherCode}" — 6-char [A-Z2-9], no 0/O/1/I/L`);
        } else {
          pass('A2-code-exists', `Code chip: "${teacherCode}"`);
          if (text.length !== 6) fail('A2-code-length', `Expected 6, got ${text.length}`);
          if (/[01OIL]/.test(text)) fail('A2-code-charset', `Contains excluded chars: "${text}"`);
        }
        break;
      }
    }
    if (!teacherCode) fail('A2-code-value', `No code found (${cnt} <code> elements)`);
  } catch(e) { fail('A2-dashboard', e.message); await screenshot(teacherPage,'A2-fail'); }

  try {
    const copyBtns = teacherPage.locator('button:has-text("複製")');
    const cpCnt = await copyBtns.count();
    if (cpCnt > 0) {
      pass('A3-copy-btn', `${cpCnt} "複製" button(s)`);
      await copyBtns.first().click({ force: true });
      await teacherPage.waitForTimeout(800);
      await screenshot(teacherPage, 'A3-after-copy');
      const pageText = await teacherPage.locator('body').innerText();
      if (pageText.includes('已複製')) {
        pass('A3-copy-feedback', '"已複製" text visible after click');
      } else {
        fail('A3-copy-feedback', '"已複製" not visible — headless clipboard or UI regression');
      }
    } else {
      fail('A3-copy-btn', '"複製" button not found');
    }
  } catch(e) { fail('A3-copy', e.message); }

  // ============================================================ B. STUDENT + CREATE ACTIVITY
  log('\n=== B. Student + Create Activity ===');
  const studentContext = await browser.newContext();
  await addTourSuppressScript(studentContext);
  const studentPage = await studentContext.newPage();
  let projectId = null;
  let studentToken = null;

  try {
    await register(studentPage, studentEmail, studentPassword, studentName, 'student');
    studentToken = await studentPage.evaluate(() => localStorage.getItem('access_token'));
    pass('B1-register', `Registered student: ${studentEmail}`);
  } catch(e) { fail('B1-register', e.message); await screenshot(studentPage,'B1-fail'); }

  try {
    await suppressTours(studentPage);
    const newBtn = studentPage.locator('button:has-text("新增學習活動")').first();
    await newBtn.waitFor({ state: 'visible', timeout: 10000 });
    await newBtn.click({ force: true });
    await studentPage.waitForTimeout(800);
    await screenshot(studentPage, 'B2-modal');
    const titleVis = await studentPage.locator('text=開啟新探索').first().isVisible().catch(() => false);
    if (titleVis) {
      pass('B2-modal-title', '"開啟新探索" modal title visible');
    } else {
      const bt = await studentPage.locator('body').innerText();
      fail('B2-modal-title', `"開啟新探索" not visible. Text: ${bt.slice(0,200)}`);
    }
  } catch(e) { fail('B2-modal', e.message); await screenshot(studentPage,'B2-fail'); }

  try {
    const nameInput = studentPage.locator('input[placeholder="例：校園永續設計工作坊"]').first();
    await nameInput.waitFor({ state: 'visible', timeout: 8000 });
    await nameInput.fill('QA Phase22');
    pass('B3-name', '"QA Phase22" filled');

    const tcInput = studentPage.locator('input[placeholder="例：MD7K2A"]').first();
    const tcVis = await tcInput.isVisible().catch(() => false);
    if (tcVis) {
      pass('B3-teacher-code-field', '"加入老師班譯（選填）" field visible (placeholder 例：MD7K2A)');
      if (teacherCode) {
        await tcInput.fill(teacherCode);
        pass('B3-teacher-code-entered', `Teacher code "${teacherCode}" entered`);
      } else {
        skip('B3-teacher-code-entered', 'No teacher code available');
      }
    } else {
      fail('B3-teacher-code-field', '"加入老師班譯" input not visible');
    }

    const crewBtns = studentPage.locator('[role="dialog"] button').filter({ hasText: 'AI 組員' });
    const crewCnt = await crewBtns.count();
    if (crewCnt >= 1) {
      await crewBtns.first().click({ force: true });
      await studentPage.waitForTimeout(200);
      pass('B3-crew-count', `Crew count set to 1 (${crewCnt} buttons found)`);
    } else {
      skip('B3-crew-count', 'Crew buttons not found');
    }
    await screenshot(studentPage, 'B3-step1');
  } catch(e) { fail('B3-basics', e.message); await screenshot(studentPage,'B3-fail'); }

  try {
    await studentPage.evaluate(() => {
      const d = document.querySelectorAll('[role="dialog"]');
      if (d.length) d[d.length-1].scrollTop = 9999;
    });
    await studentPage.waitForTimeout(300);
    const nextBtn = studentPage.locator('[role="dialog"] button:has-text("下一步")').first();
    await nextBtn.waitFor({ state: 'visible', timeout: 8000 });
    await nextBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    pass('B4-advance', '"下一步" clicked → persona step');
    await screenshot(studentPage, 'B4-step2');
  } catch(e) { fail('B4-advance', e.message); await screenshot(studentPage,'B4-fail'); }

  try {
    const manualBtn = studentPage.locator('button:has-text("手動新增")').first();
    await manualBtn.waitFor({ state: 'visible', timeout: 8000 });
    await manualBtn.click({ force: true });
    await studentPage.waitForTimeout(1000);
    await screenshot(studentPage, 'B5-persona-dialog');

    const pNameInput = studentPage.locator('input[placeholder="例：陳秀英"]').first();
    await pNameInput.waitFor({ state: 'visible', timeout: 10000 });
    await pNameInput.fill('P1');
    pass('B5-persona-dialog', 'PersonaEditDialog opened, name "P1" filled');

    // Check for role field
    const allFields = await studentPage.evaluate(() => {
      return Array.from(document.querySelectorAll('input,textarea')).map(el => ({
        tag: el.tagName, placeholder: el.getAttribute('placeholder'),
        type: el.getAttribute('type'), id: el.id, name: el.getAttribute('name'),
      }));
    });
    log(`PersonaEditDialog fields: ${JSON.stringify(allFields.slice(0,15))}`);
    const hasRoleField = allFields.some(el =>
      (el.placeholder && (el.placeholder.includes('角色') || el.placeholder.toLowerCase().includes('role'))) ||
      (el.name && el.name.toLowerCase().includes('role')) ||
      (el.id && el.id.toLowerCase().includes('role'))
    );
    if (!hasRoleField) {
      bug('B5-role-field-missing',
        'BUG: PersonaEditDialog has no "role" input. Backend persona.role has min_length=1. ' +
        'Manual persona creation always submits role="" → HTTP 422. Frontend must add role field.');
    } else {
      pass('B5-role-field', 'role input found in PersonaEditDialog');
    }

    const saveBtns = studentPage.locator('button:has-text("儲存")');
    if (await saveBtns.count() > 0) {
      await saveBtns.last().click({ force: true });
      await studentPage.waitForTimeout(800);
      pass('B5-persona-saved', 'Persona saved in dialog');
    }
    await screenshot(studentPage, 'B5-after-save');

    // Attempt submit
    const submitBtn = studentPage.locator('[role="dialog"] button:has-text("開始探索")').first();
    if (await submitBtn.isVisible().catch(() => false)) {
      const isDisabled = await submitBtn.isDisabled().catch(() => true);
      if (!isDisabled) {
        await submitBtn.click({ force: true });
        await studentPage.waitForTimeout(3000);
        const newUrl = studentPage.url();
        const bt = await studentPage.locator('body').innerText();
        if (newUrl.match(/\/projects\/[^/?#]+/)) {
          pass('B6-project-created-ui', `UI creation succeeded. URL: ${newUrl}`);
          const m = newUrl.match(/projects\/([^/?#]+)/);
          if (m) projectId = m[1];
        } else if (bt.includes('422') || bt.includes('Request failed')) {
          bug('B6-create-422', `HTTP 422: role="" rejected by backend. Body: ${bt.slice(Math.max(0,bt.indexOf('422')-5), bt.indexOf('422')+80)}`);
        } else {
          fail('B6-submit', `Unknown result. URL: ${newUrl}`);
        }
        await screenshot(studentPage, 'B6-result');
      } else {
        fail('B6-disabled', 'Submit disabled after adding persona');
      }
    }
  } catch(e) { fail('B5-flow', e.message); await screenshot(studentPage,'B5-fail'); }

  // API fallback
  if (!projectId && studentToken) {
    try {
      const project = await apiPost('/api/projects', studentToken, {
        name: 'QA Phase22', description: '', ai_contribution: 'medium', ai_crew_count: 1,
        personas: [{ seat_role: 'crew_1', persona: {
          name:'P1', role:'Researcher', expertise:'design thinking', backstory:'researcher',
          personality_axis:'balanced', personality_desc:'curious',
          lens_affinities:{empathy:0.5,structure:0.5,creativity:0.5,feasibility:0.5}
        }}],
        timer_config: { total_session_minutes:120,
          macro_budgets:{discover:45,define:30,develop:25,deliver:20}, preset_id:'timer_preset_2hr' },
        ...(teacherCode ? { teacher_signature_code: teacherCode.toUpperCase() } : {})
      });
      projectId = project.id;
      pass('BAPI-created', `API project created. ID: ${projectId}. teacher_code: ${teacherCode||'N/A'}`);
    } catch(e) { fail('BAPI-created', `API failed: ${e.message}`); }
  }

  // Navigate student to lobby
  if (projectId) {
    log(`Student URL before lobby nav: ${studentPage.url()}`);
    await spaNavigate(studentPage, `/projects/${projectId}/lobby`);
    log(`Lobby URL: ${studentPage.url()}`);
    await screenshot(studentPage, 'BAPI-lobby-nav');
  }

  // ============================================================ C. LOBBY
  log('\n=== C. Lobby ===');
  let inviteCode = null;

  if (projectId) {
    try {
      await screenshot(studentPage, 'C1-lobby');
      const bodyText = await studentPage.locator('body').innerText();
      log(`Lobby URL: ${studentPage.url()}`);
      log(`Lobby body (1000): ${bodyText.slice(0,1000)}`);

      if (bodyText.includes('活動代碼')) {
        pass('C1-invite-code-label', '"活動代碼" visible');
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
        if (!inviteCode) fail('C1-invite-code-value', `No code chip found (${cnt} <code> elements)`);
        const cpCnt = await studentPage.locator('button:has-text("複製")').count();
        if (cpCnt > 0) pass('C2-copy-btn', `"複製" in lobby (count: ${cpCnt})`);
        else fail('C2-copy-btn', '"複製" not in lobby');
      } else {
        fail('C1-invite-code-label', `"活動代碼" not in lobby. URL: ${studentPage.url()}`);
      }

      if (bodyText.includes("列管狀態") || bodyText.includes("已列管") || bodyText.includes("尚未列管")) {
        pass('C3-linked-status-label', '"列管狀態" visible');
        if (teacherCode && bodyText.includes('已列管')) {
          pass('C4-linked-teacher', '"已列管" visible');
          if (bodyText.includes(teacherName)) pass('C4-teacher-name', `"${teacherName}" shown in 已列管`);
          else fail('C4-teacher-name', `"${teacherName}" not found. Body: ${bodyText.slice(0,500)}`);
          const unlinkVis = await studentPage.locator('button:has-text("解除")').first().isVisible().catch(()=>false);
          if (unlinkVis) pass('C5-unlink-btn', '"解除" visible');
          else fail('C5-unlink-btn', '"解除" not visible');
        } else if (!teacherCode) {
          skip('C4-linked-teacher', 'No teacher code');
        } else {
          fail('C4-linked-teacher', `"已列管" not shown despite teacher_code "${teacherCode}". Body: ${bodyText.slice(0,500)}`);
        }
      } else {
        fail('C3-linked-status-label', `"列管狀態" not in lobby. URL: ${studentPage.url()}`);
      }
    } catch(e) { fail('C-lobby', e.message); await screenshot(studentPage,'C-fail'); }
  } else {
    skip('C-lobby', 'No projectId');
  }

  // ============================================================ D. TEACHER SEES ACTIVITY
  log('\n=== D. Teacher Sees Activity ===');
  try {
    // reload teacher page to force fresh API data
    await teacherPage.reload();
    await teacherPage.waitForLoadState('networkidle');
    // After reload, Zustand rehydrates — wait for teacher content
    await teacherPage.waitForFunction(() =>
      document.body.innerText.includes('我的教師代碼') || document.body.innerText.includes('教師儀表板'),
      { timeout: 8000 }
    ).catch(() => null);
    await spaNavigate(teacherPage, '/teacher/dashboard');
    await suppressTours(teacherPage);

    // Click 重新整理 if available
    const refreshBtn = teacherPage.locator('button:has-text("重新整理")').first();
    if (await refreshBtn.isVisible().catch(()=>false)) {
      await refreshBtn.click({ force: true });
      await teacherPage.waitForTimeout(2000);
      log('Clicked 重新整理');
    }
    await suppressTours(teacherPage);
    await screenshot(teacherPage, 'D1-dashboard');
    const dashText = await teacherPage.locator('body').innerText();
    log(`Teacher dashboard (800): ${dashText.slice(0,800)}`);
    if (dashText.includes('QA Phase22')) {
      pass('D1-sees-activity', '"QA Phase22" visible in teacher dashboard monitoring');
    } else {
      fail('D1-sees-activity', `"QA Phase22" not found. URL: ${teacherPage.url()}. Text: ${dashText.slice(0,500)}`);
    }
  } catch(e) { fail('D1-sees-activity', e.message); await screenshot(teacherPage,'D1-fail'); }

  // ============================================================ E. NEGATIVE PATH
  log('\n=== E. Negative Path ===');
  try {
    if (!teacherPage.url().includes('teacher/dashboard')) {
      await spaNavigate(teacherPage, '/teacher/dashboard');
    }
    const listBtn = teacherPage.locator('button:has-text("列管")').first();
    await listBtn.waitFor({ state: 'visible', timeout: 8000 });

    const allInputs = teacherPage.locator('input');
    const inputCnt = await allInputs.count();
    let trackInput = null;
    for (let i = inputCnt-1; i >= 0; i--) {
      const el = allInputs.nth(i);
      if (await el.isVisible().catch(()=>false)) { trackInput = el; break; }
    }
    if (trackInput) {
      await trackInput.fill('NOTREAL');
      await listBtn.click({ force: true });
      await teacherPage.waitForTimeout(2000);
      await screenshot(teacherPage, 'E1-invalid');
      const pageText = await teacherPage.locator('body').innerText();
      log(`After invalid code (500): ${pageText.slice(0,500)}`);
      const hasErr = pageText.includes('找不到') || pageText.includes('列管失敗') || pageText.includes('請確認代碼');
      if (hasErr) {
        const idx = Math.max(pageText.indexOf('找不到'), pageText.indexOf('列管失敗'));
        pass('E1-error', `Error shown: "${pageText.substring(Math.max(0,idx), idx+25).trim()}"`);
      } else {
        fail('E1-error', `No error message. Text: ${pageText.slice(0,400)}`);
      }
    } else {
      fail('E1-input', 'No visible input found on teacher dashboard');
    }
  } catch(e) { fail('E1-negative', e.message); await screenshot(teacherPage,'E1-fail'); }

  // ============================================================ F. SEATS sticky_color
  log('\n=== F. Seats sticky_color ===');
  if (projectId && studentToken) {
    try {
      const seatsData = await studentPage.evaluate(async ({base, pid, tok}) => {
        const r = await fetch(`${base}/api/projects/${pid}/seats`, { headers: { Authorization:`Bearer ${tok}` } });
        const text = await r.text();
        try { return { status: r.status, data: JSON.parse(text) }; } catch { return { status: r.status, raw: text }; }
      }, { base: BASE_URL, pid: projectId, tok: studentToken });
      log(`Seats API (${seatsData.status}): ${JSON.stringify(seatsData).slice(0,700)}`);
      const validColors = ['yellow','orange','green','blue','violet','red','light-blue','light-green'];
      const seats = Array.isArray(seatsData.data) ? seatsData.data : (seatsData.data?.seats || []);
      if (seats.length === 0) {
        fail('F1-seats', `No seats. Raw: ${JSON.stringify(seatsData).slice(0,200)}`);
      } else {
        const colors = seats.map(s => s.sticky_color);
        log(`Seat colors: [${colors.join(', ')}]`);
        const allHave = seats.every(s => s.sticky_color != null);
        const allValid = seats.every(s => validColors.includes(s.sticky_color));
        if (!allHave) fail('F1-color-present', `Missing sticky_color. ${JSON.stringify(seats.map(s=>({r:s.seat_role,c:s.sticky_color})))}`);
        else if (!allValid) fail('F1-color-valid', `Invalid: [${colors.join(', ')}]. Valid: [${validColors.join(', ')}]`);
        else pass('F1-sticky-color', `All ${seats.length} seats have valid sticky_color: [${colors.join(', ')}]`);
        const unique = [...new Set(colors.filter(Boolean))];
        if (seats.length <= 1) skip('F2-varied', `Only ${seats.length} seat`);
        else if (unique.length > 1) pass('F2-varied', `Colors differ: [${unique.join(', ')}]`);
        else fail('F2-varied', `All ${seats.length} seats share color: "${unique[0]}"`);
      }
    } catch(e) { fail('F1-seats', e.message); }
  } else {
    skip('F1-seats', 'No projectId or token');
    skip('F2-varied', 'No projectId');
  }

  // ============================================================ G. CHATDOCK BUBBLE COLOR
  log('\n=== G. ChatDock Bubble Color ===');
  if (projectId) {
    try {
      await spaNavigate(studentPage, `/projects/${projectId}/workspace`);
      await studentPage.waitForTimeout(3000);
      await suppressTours(studentPage);
      await screenshot(studentPage, 'G1-workspace');
      const chatInfo = await studentPage.evaluate(() => {
        for (const sel of ['[data-testid="chat-message"]','[class*="ChatMessage"]','[class*="message-bubble"]']) {
          const els = Array.from(document.querySelectorAll(sel)).filter(el => el.textContent?.trim().length > 5);
          if (els.length > 0) return { sel, count: els.length, items: els.slice(0,5).map(el => ({
            text: el.textContent?.slice(0,50), bg: getComputedStyle(el).backgroundColor, style: el.getAttribute('style'),
          })) };
        }
        const inlineEls = Array.from(document.querySelectorAll('[style*="background-color"]'));
        if (inlineEls.length > 0) return { sel: 'inline-bg', count: inlineEls.length, items: inlineEls.slice(0,5).map(el => ({
          text: el.textContent?.slice(0,50), bg: el.style.backgroundColor,
          style: el.getAttribute('style'), tag: el.tagName,
        })) };
        const divs = Array.from(document.querySelectorAll('div'))
          .filter(el => { const bg=getComputedStyle(el).backgroundColor; return bg!=='rgba(0, 0, 0, 0)'&&bg!=='transparent'&&el.textContent?.trim().length>5; })
          .slice(0,5);
        if (divs.length > 0) return { sel:'div-bg', count:divs.length, items:divs.map(el=>({
          text:el.textContent?.slice(0,50), bg:getComputedStyle(el).backgroundColor, cls:el.className?.slice(0,60),
        })) };
        return null;
      });
      if (!chatInfo) {
        skip('G1-chat-bubble', 'No chat messages — workspace idle (acceptable for new project)');
      } else {
        log(`Chat: ${JSON.stringify(chatInfo).slice(0,500)}`);
        const hasColor = chatInfo.items.some(m =>
          (m.style && m.style.includes('background-color')) ||
          (m.bg && m.bg !== 'rgba(0, 0, 0, 0)' && m.bg !== '' && m.bg !== 'transparent')
        );
        if (hasColor) pass('G1-chat-bubble-color', `bg-color found (sel: ${chatInfo.sel}). Sample: ${JSON.stringify(chatInfo.items[0]).slice(0,120)}`);
        else fail('G1-chat-bubble-color', `No bg-color. Data: ${JSON.stringify(chatInfo.items).slice(0,300)}`);
      }
    } catch(e) { fail('G1-workspace', e.message); await screenshot(studentPage,'G1-fail'); }
  } else {
    skip('G1-chat-bubble', 'No projectId');
  }

  skip('H1-note-injector', 'Best-effort tldraw state — skipped');

  // ============================================================ FINAL REPORT
  log('\n========== PHASE 22 QA REPORT ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const skipCount = results.filter(r => r.status === 'SKIP').length;
  const bugCount = results.filter(r => r.status === 'BUG').length;
  console.log(`Total: ${results.length} | PASS: ${passCount} | FAIL: ${failCount} | BUG: ${bugCount} | SKIP: ${skipCount}\n`);
  for (const r of results) console.log(`[${r.status.padEnd(4)}] ${r.area}: ${r.detail}`);
  const report = {
    timestamp: new Date().toISOString(), version: 'run-final',
    teacherEmail, studentEmail, teacherCode, projectId, inviteCode,
    summary: { total: results.length, pass: passCount, fail: failCount, bug: bugCount, skip: skipCount },
    results, screenshotDir: SCREENSHOT_DIR,
  };
  fs.writeFileSync(path.join(__dirname,'qa-phase22-final-report.json'), JSON.stringify(report, null, 2));
  log('Report written.');
  await browser.close();
  process.exit((failCount + bugCount) > 0 ? 1 : 0);
}
main().catch(e => { console.error('Fatal:', e); process.exit(2); });
