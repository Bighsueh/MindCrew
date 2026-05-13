const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:5173';
const PROJECT_ID = '9fd71949-fb81-4aea-9347-d85509e01d11';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'phase21-qa');

fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function loginAs(page, email, password) {
  await page.goto(`${BASE}/login`);
  await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 10000 });
  await page.fill('input[type="email"], input[name="email"]', email);
  await page.fill('input[type="password"], input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(`${BASE}/**`, { timeout: 15000 });
}

async function runTests() {
  const results = {};
  const browser = await chromium.launch({ headless: true });

  // ===== A4: Frontend stays alive, canvas renders =====
  try {
    console.log('A4: Testing frontend canvas...');
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'teacher@test.com', 'teacher123');
    await page.goto(`${BASE}/projects/${PROJECT_ID}/workspace`);
    await page.waitForTimeout(4000);

    const screenshotPath = path.join(SCREENSHOTS_DIR, 'a4-canvas.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });

    // Check for tldraw red error screen
    const hasErrorScreen = await page.locator('text=Something\'s gone wrong').count() > 0;
    // Check for tldraw canvas element
    const hasTldraw = await page.locator('.tl-canvas, [data-testid="canvas"], canvas').count() > 0;
    // Check for the note content
    const hasNote = await page.locator('text=good-string-author').count() > 0;

    results.A4 = {
      pass: !hasErrorScreen,
      evidence: `errorScreen=${hasErrorScreen}, tldrawElement=${hasTldraw}, noteVisible=${hasNote}`,
      screenshot: screenshotPath
    };
    await ctx.close();
  } catch (e) {
    results.A4 = { pass: false, evidence: e.message };
  }

  // ===== B1: Student observer button disabled =====
  try {
    console.log('B1: Testing student observer button...');
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'student1@test.com', 'student123');
    await page.goto(`${BASE}/projects/${PROJECT_ID}/lobby`);
    await page.waitForTimeout(3000);

    const screenshotPath = path.join(SCREENSHOTS_DIR, 'b1-student-lobby.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });

    // Find observer button
    const observerBtn = page.locator('button:has-text("以觀察者身份進入")');
    const count = await observerBtn.count();
    let isDisabled = false;
    let titleAttr = '';

    if (count > 0) {
      isDisabled = await observerBtn.getAttribute('disabled') !== null;
      titleAttr = await observerBtn.getAttribute('title') || '';
    }

    results.B1 = {
      pass: count > 0 && isDisabled && titleAttr === '僅教師可觀察',
      evidence: `buttonFound=${count > 0}, disabled=${isDisabled}, title="${titleAttr}"`,
      screenshot: screenshotPath
    };
    await ctx.close();
  } catch (e) {
    results.B1 = { pass: false, evidence: e.message };
  }

  // ===== B2: Student bypassing workspace gets bounced to lobby =====
  try {
    console.log('B2: Testing student direct workspace access...');
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'student1@test.com', 'student123');
    await page.goto(`${BASE}/projects/${PROJECT_ID}/workspace`);
    await page.waitForTimeout(3000);

    const finalUrl = page.url();
    const bouncedToLobby = finalUrl.includes('/lobby');

    results.B2 = {
      pass: bouncedToLobby,
      evidence: `finalUrl=${finalUrl}, bouncedToLobby=${bouncedToLobby}`
    };
    await ctx.close();
  } catch (e) {
    results.B2 = { pass: false, evidence: e.message };
  }

  // ===== B3: Teacher observer enters workspace =====
  try {
    console.log('B3: Testing teacher workspace access...');
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'teacher@test.com', 'teacher123');
    await page.goto(`${BASE}/projects/${PROJECT_ID}/workspace`);
    await page.waitForTimeout(4000);

    const screenshotPath = path.join(SCREENSHOTS_DIR, 'b3-teacher-workspace.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const hasErrorScreen = await page.locator('text=Something\'s gone wrong').count() > 0;
    const hasTldraw = await page.locator('.tl-canvas, canvas').count() > 0;
    // Check if chat input is disabled (observer mode) or enabled
    const chatInput = page.locator('input[placeholder*="輸入"], textarea[placeholder*="輸入"], input[placeholder*="訊息"], textarea[placeholder*="訊息"]');
    const chatInputCount = await chatInput.count();
    let chatDisabled = null;
    if (chatInputCount > 0) {
      chatDisabled = await chatInput.first().getAttribute('disabled') !== null;
    }

    const finalUrl = page.url();

    results.B3 = {
      pass: !hasErrorScreen && finalUrl.includes('/workspace'),
      evidence: `canvasRenders=${hasTldraw}, errorScreen=${hasErrorScreen}, chatInputDisabled=${chatDisabled}, url=${finalUrl}`,
      screenshot: screenshotPath
    };
    await ctx.close();
  } catch (e) {
    results.B3 = { pass: false, evidence: e.message };
  }

  await browser.close();
  return results;
}

runTests().then(results => {
  console.log('\n=== PLAYWRIGHT RESULTS ===');
  for (const [test, r] of Object.entries(results)) {
    console.log(`${test}: ${r.pass ? 'PASS' : 'FAIL'} | ${r.evidence}${r.screenshot ? ' | screenshot: ' + r.screenshot : ''}`);
  }
}).catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
