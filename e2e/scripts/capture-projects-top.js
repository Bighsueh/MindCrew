const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  try {
    // Login
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    await emailInput.fill('teacher@test.com');
    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.fill('teacher123');
    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();
    await page.waitForURL((url) => !url.toString().includes('/login'), { timeout: 10000 });
    await page.waitForTimeout(1500);

    await page.goto('http://localhost:3000/projects', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Capture viewport-only (top of page showing stats + search)
    await page.screenshot({
      path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/phase9-projects-top.png',
      fullPage: false,
      clip: { x: 0, y: 0, width: 1440, height: 500 },
    });

    console.log('Top section screenshot saved.');
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
