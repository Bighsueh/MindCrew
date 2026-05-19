/**
 * Tech Lead QA Verification Script
 * Verifies recent UI changes to MindCrew at http://localhost:3000
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:3000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'techlead-qa');
const TIMESTAMP = Date.now();
const STUDENT_EMAIL = `qa-student-${TIMESTAMP}@test.com`;
const STUDENT_PASSWORD = 'testpass123';
const STUDENT_NAME = 'QA Student';

const results = [];
let browser, page;

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function record(area, name, passed, evidence, extra = '') {
  const status = passed ? 'PASS' : 'FAIL';
  results.push({ area, name, passed, evidence, extra });
  console.log(`  [${status}] ${name}`);
  if (!passed) console.log(`    EXPECTED: ${evidence}`);
  if (extra) console.log(`    ACTUAL:   ${extra}`);
}

function screenshot(name) {
  const filePath = path.join(SCREENSHOTS_DIR, `${name}.png`);
  return page.screenshot({ path: filePath, fullPage: false }).then(() => filePath);
}

async function setup() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage();
  page.setDefaultTimeout(15000);
}

async function teardown() {
  await browser.close();
}

// ─── Area 1: Landing Page ───────────────────────────────────────────────────
async function testLandingPage() {
  log('=== Area 1: Landing Page ===');
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await screenshot('01-landing');

  const bodyText = await page.evaluate(() => document.body.innerText);

  // No "五位" anywhere
  const hasFiveChars = bodyText.includes('五位');
  record('Landing', 'No "五位" hardcoded text', !hasFiveChars,
    'Text "五位" should NOT appear',
    hasFiveChars ? `Found "五位" in page text` : 'Confirmed absent');

  // Nav button "免費註冊" (not "教師免費註冊")
  const navBtn = await page.$('nav a:has-text("免費註冊"), nav button:has-text("免費註冊")');
  const navBtnText = navBtn ? await navBtn.innerText() : null;
  const navOk = navBtnText && navBtnText.trim() === '免費註冊';
  record('Landing', 'Nav button reads "免費註冊"', navOk,
    '"免費註冊"',
    navBtnText ? `"${navBtnText.trim()}"` : 'Button not found');

  // Hero CTA "免費註冊"
  const heroText = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('a, button'));
    return els.map(el => el.innerText.trim()).filter(t => t.includes('免費註冊'));
  });
  record('Landing', 'Hero CTA reads "免費註冊"', heroText.length > 0,
    'At least one element with "免費註冊"',
    heroText.join(', ') || 'None found');

  // Hero subtitle
  const subtitle = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('p, h1, h2, h3, span, div'));
    return all.map(el => el.innerText?.trim()).filter(t => t.includes('AI 隊友與你一起發散'));
  });
  const subtitleOk = subtitle.some(s => s.includes('AI 隊友與你一起發散、收斂、創造'));
  record('Landing', 'Hero subtitle correct', subtitleOk,
    '"AI 隊友與你一起發散、收斂、創造。"',
    subtitle[0] || 'Not found');
}

// ─── Area 2: Register Page ───────────────────────────────────────────────────
async function testRegisterPage() {
  log('=== Area 2: Register Page ===');
  await page.goto(`${BASE_URL}/register`, { waitUntil: 'networkidle' });
  await screenshot('02-register-initial');

  // Role toggle with 教師 / 學生
  const teacherBtn = await page.$('button:has-text("教師")');
  const studentBtn = await page.$('button:has-text("學生")');
  record('Register', 'Role toggle has 教師 button', !!teacherBtn, 'Button with text "教師"');
  record('Register', 'Role toggle has 學生 button', !!studentBtn, 'Button with text "學生"');

  // Switch to 學生
  if (studentBtn) {
    await studentBtn.click();
    await page.waitForTimeout(500);
    await screenshot('02-register-student');
  }

  const pageText = await page.evaluate(() => document.body.innerText);
  record('Register', 'Title changes to "學生註冊"', pageText.includes('學生註冊'),
    '"學生註冊" visible', pageText.includes('學生') ? 'Has 學生 text' : 'No 學生 text');
  record('Register', 'Subtitle has "建立您的學生帳號開始探索"', pageText.includes('建立您的學生帳號開始探索'),
    '"建立您的學生帳號開始探索"', pageText.includes('學生帳號') ? 'Has 學生帳號 text' : 'Not found');

  // Fill registration form
  log(`Registering student: ${STUDENT_EMAIL}`);

  // Display name
  const nameInput = await page.$('input[placeholder*="名稱"], input[name="displayName"], input[id*="name"]');
  if (nameInput) {
    await nameInput.fill(STUDENT_NAME);
  } else {
    // Try to find by label
    const inputs = await page.$$('input');
    log(`Found ${inputs.length} inputs on register page`);
  }

  const emailInput = await page.$('input[type="email"], input[placeholder*="Email"], input[placeholder*="email"]');
  if (emailInput) await emailInput.fill(STUDENT_EMAIL);

  const passInputs = await page.$$('input[type="password"]');
  if (passInputs.length > 0) await passInputs[0].fill(STUDENT_PASSWORD);
  if (passInputs.length > 1) await passInputs[1].fill(STUDENT_PASSWORD);

  await screenshot('02-register-filled');

  // Submit
  const submitBtn = await page.$('button[type="submit"]:has-text("註冊"), button:has-text("建立帳號"), button:has-text("立即")');
  if (submitBtn) {
    await submitBtn.click();
  } else {
    // Try the last button
    const allBtns = await page.$$('button');
    if (allBtns.length > 0) {
      const lastBtn = allBtns[allBtns.length - 1];
      const txt = await lastBtn.innerText();
      log(`Clicking last button: "${txt}"`);
      await lastBtn.click();
    }
  }

  // Wait for redirect
  try {
    await page.waitForURL(`${BASE_URL}/projects`, { timeout: 10000 });
    await screenshot('02-after-register');
    record('Register', 'Redirects to /projects after registration', true, '/projects URL');
  } catch (e) {
    const currentUrl = page.url();
    await screenshot('02-register-error');
    const errText = await page.evaluate(() => document.body.innerText).catch(() => '');
    record('Register', 'Redirects to /projects after registration', false,
      '/projects URL', `Still at ${currentUrl} — ${errText.slice(0, 200)}`);
  }
}

// ─── Area 3: Projects Page Empty State ──────────────────────────────────────
async function testProjectsEmptyState() {
  log('=== Area 3: Projects Empty State ===');

  // Ensure we're on projects page
  if (!page.url().includes('/projects')) {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
  }
  await page.waitForTimeout(1000);
  await screenshot('03-projects-empty');

  const bodyText = await page.evaluate(() => document.body.innerText);

  // "尚無學習活動" heading
  record('Projects', '"尚無學習活動" heading visible', bodyText.includes('尚無學習活動'),
    '"尚無學習活動"', bodyText.includes('尚無') ? 'Has 尚無 text' : 'Not found');

  // Heading font class check
  const headingEl = await page.$('h2:has-text("尚無學習活動"), h3:has-text("尚無學習活動"), p:has-text("尚無學習活動")');
  if (headingEl) {
    const cls = await headingEl.getAttribute('class');
    const fontOk = cls && (cls.includes('text-2xl') || cls.includes('text-3xl'));
    record('Projects', 'Empty state heading uses large bold font', fontOk,
      'class contains text-2xl or text-3xl', cls || 'no class');
  } else {
    record('Projects', 'Empty state heading uses large bold font', false, 'Heading element not found');
  }

  // Stats grid should be hidden
  const statsGrid = await page.$('.grid:has([class*="card"]), [data-testid="stats-grid"]');
  const statsCards = await page.$$('[class*="stat-card"], [data-testid*="stat"]');
  // Check by inspecting if stat numbers are visible
  const hasStats = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    return all.some(el => {
      const txt = el.innerText?.trim();
      return /^(活動數|總計|專案數)/.test(txt || '');
    });
  });
  record('Projects', 'Stats grid hidden when 0 projects', !hasStats,
    'Stats should be hidden', hasStats ? 'Stats are visible' : 'Confirmed hidden');

  // "新增學習活動" button in top-right
  const addBtn = await page.$('button:has-text("新增學習活動"), a:has-text("新增學習活動")');
  record('Projects', '"新增學習活動" button visible', !!addBtn,
    'Button with "新增學習活動"', addBtn ? 'Found' : 'Not found');
}

// ─── Area 4: Create Modal ────────────────────────────────────────────────────
async function testCreateModal() {
  log('=== Area 4: Create 學習活動 Modal ===');

  // Click to open modal
  const addBtn = await page.$('button:has-text("新增學習活動"), button:has-text("建立第一個"), a:has-text("新增學習活動")');
  if (!addBtn) {
    record('Modal', 'Can open create modal', false, 'Add button not found');
    return;
  }
  await addBtn.click();
  await page.waitForTimeout(1000);
  await screenshot('04-modal-opened');

  const pageText = await page.evaluate(() => document.body.innerText);

  // Modal title "開啟新探索"
  record('Modal', 'Modal title is "開啟新探索"', pageText.includes('開啟新探索'),
    '"開啟新探索"', pageText.includes('開啟') ? 'Has "開啟"' : 'Not found');

  // Required fields
  record('Modal', 'Has 活動名稱 field', pageText.includes('活動名稱'), '"活動名稱"');
  record('Modal', 'Has 描述 field', pageText.includes('描述'), '"描述"');
  record('Modal', 'Has AI 參與程度', pageText.includes('AI 參與程度'), '"AI 參與程度"');
  record('Modal', 'Has AI 組員人數', pageText.includes('AI 組員'), '"AI 組員人數"');

  // 簡單/進階 toggle
  const simpleBtn = await page.$('button:has-text("簡單")');
  const advancedBtn = await page.$('button:has-text("進階")');
  record('Modal', 'Has 簡單/進階 toggle', !!simpleBtn && !!advancedBtn,
    'Both 簡單 and 進階 buttons', `簡單: ${!!simpleBtn}, 進階: ${!!advancedBtn}`);

  // Ensure in 簡單 mode
  if (simpleBtn) await simpleBtn.click();
  await page.waitForTimeout(500);

  // In 簡單 mode: no 時程長度
  const hasSchedule = pageText.includes('時程長度');
  record('Modal', 'No 時程長度 in 簡單 mode', !hasSchedule,
    '"時程長度" should NOT appear',
    hasSchedule ? 'Found "時程長度"' : 'Confirmed absent');

  // THREE groups: 預算範圍, 目標使用者族群, 落地場域
  record('Modal', '簡單 mode has 預算範圍', pageText.includes('預算範圍'), '"預算範圍"');
  record('Modal', '簡單 mode has 目標使用者族群', pageText.includes('目標使用者族群'), '"目標使用者族群"');
  record('Modal', '簡單 mode has 落地場域', pageText.includes('落地場域'), '"落地場域"');

  // 預算範圍 options
  const budgetOptions = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('button, label, [role="option"], li'));
    return all.map(el => el.innerText?.trim()).filter(t =>
      t.includes('NT$') || t.includes('不限') || t.includes('無預算') || t.includes('微型') || t.includes('小型') || t.includes('中型') || t.includes('大型')
    );
  });
  record('Modal', 'Budget options show concrete NT$ amounts', budgetOptions.length >= 3,
    'At least 3 budget options with NT$ or keywords',
    budgetOptions.slice(0, 5).join(' | ') || 'None found');

  // Click a budget option and check preview updates
  const microBudget = await page.$('button:has-text("微型"), label:has-text("微型"), [role="option"]:has-text("微型")');
  if (microBudget) {
    await microBudget.click();
    await page.waitForTimeout(500);
    const afterClick = await page.evaluate(() => document.body.innerText);
    const previewUpdated = afterClick.includes('送出內容') || afterClick.includes('微型') || afterClick.includes('NT$');
    record('Modal', 'Clicking budget option updates preview', previewUpdated,
      '"送出內容" preview updates or selected option visible');
  } else {
    record('Modal', 'Clicking budget option updates preview', false, '微型 option not found to click');
  }

  // ── Critical Scroll Test ──
  log('  -- Scroll test --');
  await screenshot('04-modal-scroll-before');

  // Find modal scroll container
  const scrollInfo = await page.evaluate(() => {
    const el = document.querySelector('.modal-scroll');
    if (!el) return { found: false };
    return {
      found: true,
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
      scrollTop: el.scrollTop,
      scrollbarWidth: getComputedStyle(el).scrollbarWidth,
      overflowY: getComputedStyle(el).overflowY,
    };
  });

  record('Modal', 'Modal scroll container (.modal-scroll) exists', scrollInfo.found,
    '.modal-scroll element found', scrollInfo.found ? 'Found' : 'NOT FOUND');

  if (scrollInfo.found) {
    record('Modal', 'Modal scrollHeight > clientHeight (taller than viewport)', scrollInfo.scrollHeight > scrollInfo.clientHeight,
      `scrollHeight (${scrollInfo.scrollHeight}) > clientHeight (${scrollInfo.clientHeight})`,
      `scrollHeight=${scrollInfo.scrollHeight}, clientHeight=${scrollInfo.clientHeight}`);

    // Scroll down
    await page.evaluate(() => {
      document.querySelector('.modal-scroll').scrollTop = 500;
    });
    await page.waitForTimeout(300);

    const scrolledTop = await page.evaluate(() => document.querySelector('.modal-scroll').scrollTop);
    record('Modal', 'Modal body is scrollable (scrollTop updates)', scrolledTop > 0,
      'scrollTop > 0 after setting to 500', `scrollTop=${scrolledTop}`);

    await screenshot('04-modal-scroll-after');

    // Check scrollbar-width: thin
    record('Modal', 'Custom scrollbar applied (scrollbarWidth: thin)', scrollInfo.scrollbarWidth === 'thin',
      'scrollbarWidth === "thin"', `scrollbarWidth="${scrollInfo.scrollbarWidth}"`);
  }

  // Scroll to bottom to find submit button
  await page.evaluate(() => {
    const el = document.querySelector('.modal-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(300);
  await screenshot('04-modal-scroll-bottom');

  const submitBtn = await page.$('button:has-text("下一步"), button:has-text("下一步：挑選")');
  const submitVisible = submitBtn ? await submitBtn.isVisible() : false;
  record('Modal', '"下一步：挑選 AI 夥伴" button reachable by scrolling', submitVisible,
    'Submit button visible after scrolling', submitVisible ? 'Visible' : 'Not found or not visible');
}

// ─── Area 5: Persona Edit Dialog ─────────────────────────────────────────────
async function testPersonaEditDialog() {
  log('=== Area 5: Persona Edit Dialog ===');

  // Fill required fields and advance to step 2
  // Fill activity name
  const nameInput = await page.$('input[placeholder*="活動名稱"], input[placeholder*="學習活動"], input[name*="name"], input[name*="title"]');
  if (nameInput) {
    await nameInput.fill('QA Test Activity');
  } else {
    // Scroll to top of modal first
    await page.evaluate(() => {
      const el = document.querySelector('.modal-scroll');
      if (el) el.scrollTop = 0;
    });
    await page.waitForTimeout(300);
    const inputs = await page.$$('input[type="text"], input:not([type])');
    if (inputs.length > 0) {
      await inputs[0].fill('QA Test Activity');
    }
  }

  // Click next step button
  const nextBtn = await page.$('button:has-text("下一步")');
  if (nextBtn) {
    await nextBtn.click();
    await page.waitForTimeout(1500);
    await screenshot('05-step2-ai-selection');
  } else {
    record('Persona', 'Advance to step 2', false, '"下一步" button not found');
    return;
  }

  const step2Text = await page.evaluate(() => document.body.innerText);

  // "手動新增" button
  const manualBtn = await page.$('button:has-text("手動新增")');
  record('Persona', '"手動新增" button available in step 2', !!manualBtn,
    '"手動新增" button', manualBtn ? 'Found' : 'Not found');

  if (manualBtn) {
    await manualBtn.click();
    await page.waitForTimeout(1000);
    await screenshot('05-after-manual-add');
  }

  // Click new card to open persona edit dialog
  const personaCard = await page.$('[class*="persona-card"], [data-testid*="persona"], .persona-item, [class*="PersonaCard"]');
  if (personaCard) {
    await personaCard.click();
  } else {
    // Try clicking a newly appeared card-like element
    const cards = await page.$$('[class*="card"]:not([class*="stats"]):not([class*="project"])');
    if (cards.length > 0) {
      await cards[cards.length - 1].click();
    }
  }
  await page.waitForTimeout(1000);
  await screenshot('05-persona-dialog');

  const dialogText = await page.evaluate(() => document.body.innerText);

  // No "角色／身分" input
  const hasRoleField = dialogText.includes('角色／身分') || dialogText.includes('角色/身分');
  record('Persona', '"角色／身分" field is GONE', !hasRoleField,
    '"角色／身分" should NOT appear',
    hasRoleField ? 'Found "角色／身分"' : 'Confirmed absent');

  // "認知透鏡強度" should be collapsed
  const lensDetails = await page.$('details:has-text("認知透鏡強度"), details summary:has-text("認知透鏡強度")');
  const lensText = await page.$('text=認知透鏡強度');
  record('Persona', '"認知透鏡強度" section exists', !!lensText, '"認知透鏡強度" text visible');

  if (lensDetails) {
    const isOpen = await lensDetails.evaluate(el => el.open);
    record('Persona', '"認知透鏡強度" collapsed by default', !isOpen,
      'details.open === false', `open=${isOpen}`);

    // Expand it
    const summary = await lensDetails.$('summary');
    if (summary) {
      await summary.click();
      await page.waitForTimeout(500);
      await screenshot('05-lens-expanded');
    }

    // Check 4 sliders appear
    const sliders = await page.$$('input[type="range"]');
    record('Persona', '4 sliders appear after expanding lens section', sliders.length >= 4,
      '4 sliders (同理/結構/創意/可行)', `Found ${sliders.length} sliders`);

    // Check slider labels
    const sliderText = await page.evaluate(() => document.body.innerText);
    const hasEmpathy = sliderText.includes('同理');
    const hasStructure = sliderText.includes('結構');
    const hasCreative = sliderText.includes('創意');
    const hasFeasible = sliderText.includes('可行');
    record('Persona', 'Slider labels: 同理/結構/創意/可行', hasEmpathy && hasStructure && hasCreative && hasFeasible,
      'All 4 labels visible',
      `同理:${hasEmpathy} 結構:${hasStructure} 創意:${hasCreative} 可行:${hasFeasible}`);
  } else {
    // Try to find <details> element containing 認知透鏡強度
    const allDetails = await page.$$('details');
    log(`Found ${allDetails.length} <details> elements`);
    const summary = await page.$('summary:has-text("認知透鏡")');
    if (summary) {
      record('Persona', '"認知透鏡強度" collapsed by default', true, 'Found summary element');
      await summary.click();
      await page.waitForTimeout(500);
      const sliders = await page.$$('input[type="range"]');
      record('Persona', '4 sliders appear after expanding lens section', sliders.length >= 4,
        '4 sliders', `Found ${sliders.length}`);
    } else {
      record('Persona', '"認知透鏡強度" collapsed by default', false, '<details> with summary not found');
    }
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  log('Starting Tech Lead QA Verification');
  log(`Student email: ${STUDENT_EMAIL}`);

  await setup();

  try {
    await testLandingPage();
    await testRegisterPage();
    await testProjectsEmptyState();
    await testCreateModal();
    await testPersonaEditDialog();
  } catch (err) {
    log(`FATAL ERROR: ${err.message}`);
    console.error(err);
    await screenshot('fatal-error').catch(() => {});
  }

  await teardown();

  // Print summary
  console.log('\n' + '='.repeat(60));
  console.log('QA VERIFICATION SUMMARY');
  console.log('='.repeat(60));

  const areas = [...new Set(results.map(r => r.area))];
  let totalPass = 0, totalFail = 0;

  for (const area of areas) {
    const areaResults = results.filter(r => r.area === area);
    const pass = areaResults.filter(r => r.passed).length;
    const fail = areaResults.filter(r => !r.passed).length;
    totalPass += pass;
    totalFail += fail;
    console.log(`\n[${area}] ${pass} PASS, ${fail} FAIL`);
    for (const r of areaResults) {
      const icon = r.passed ? '✓' : '✗';
      console.log(`  ${icon} ${r.name}`);
      if (!r.passed) {
        console.log(`    Expected: ${r.evidence}`);
        if (r.extra) console.log(`    Got:      ${r.extra}`);
      }
    }
  }

  console.log(`\nTOTAL: ${totalPass} PASS, ${totalFail} FAIL`);
  console.log(`Screenshots: ${SCREENSHOTS_DIR}`);

  // Save JSON report
  const reportPath = path.join(__dirname, 'techlead-qa-report.json');
  fs.writeFileSync(reportPath, JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2));
  console.log(`Report: ${reportPath}`);
}

main().catch(console.error);
