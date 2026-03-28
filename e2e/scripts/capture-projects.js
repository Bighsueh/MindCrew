const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  try {
    // Step 1: Navigate to login page
    console.log('Navigating to login page...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);

    // Step 2: Fill in credentials
    console.log('Filling in credentials...');
    // Try common input selectors
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="Email" i]').first();
    await emailInput.fill('teacher@test.com');

    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.fill('teacher123');

    // Step 3: Submit login form
    console.log('Submitting login form...');
    const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in"), button:has-text("登入"), button:has-text("登錄")').first();
    await submitBtn.click();

    // Step 4: Wait for navigation after login
    console.log('Waiting for post-login navigation...');
    await page.waitForURL((url) => !url.toString().includes('/login'), { timeout: 10000 });
    await page.waitForTimeout(1500);

    // Step 5: Navigate to projects page
    console.log('Navigating to projects page...');
    await page.goto('http://localhost:3000/projects', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Step 6: Capture full-page screenshot
    const screenshotPath = '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/phase9-projects.png';
    console.log(`Taking screenshot: ${screenshotPath}`);
    await page.screenshot({
      path: screenshotPath,
      fullPage: true,
    });

    console.log('Screenshot saved successfully.');
    console.log('Current URL:', page.url());
  } catch (err) {
    console.error('Error:', err.message);

    // Capture error screenshot for debugging
    const debugPath = '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/phase9-projects-debug.png';
    await page.screenshot({ path: debugPath, fullPage: true });
    console.log(`Debug screenshot saved to: ${debugPath}`);
    console.log('Current URL at error:', page.url());
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
