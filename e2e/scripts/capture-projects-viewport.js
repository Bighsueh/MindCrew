const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  try {
    // Login
    console.log('Logging in...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });

    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first();
    await emailInput.fill('teacher@test.com');

    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.fill('teacher123');

    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    await page.waitForURL((url) => !url.toString().includes('/login'), { timeout: 10000 });
    await page.waitForTimeout(1500);

    // Navigate to projects
    console.log('Navigating to projects...');
    await page.goto('http://localhost:3000/projects', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Log the page title and key elements visible
    const title = await page.title();
    console.log('Page title:', title);

    // Check for key UI elements
    const elements = await page.evaluate(() => {
      const checks = {
        searchBar: !!document.querySelector('input[type="search"], input[placeholder*="search" i], input[placeholder*="搜尋" i]'),
        filterChips: document.querySelectorAll('[class*="chip"], [class*="filter"], [class*="tag"]').length,
        stats: document.querySelectorAll('[class*="stat"], [class*="dashboard"], [class*="count"]').length,
        cards: document.querySelectorAll('[class*="card"], [class*="project"]').length,
        headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.textContent?.trim()).filter(Boolean),
      };
      return checks;
    });
    console.log('UI elements found:', JSON.stringify(elements, null, 2));

    // Viewport screenshot (above the fold)
    await page.screenshot({
      path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/phase9-projects-viewport.png',
      fullPage: false,
    });

    console.log('Viewport screenshot saved.');

    // Print page HTML structure for debugging
    const bodyHTML = await page.evaluate(() => {
      return document.body.innerHTML.substring(0, 3000);
    });
    console.log('\nPage HTML (first 3000 chars):\n', bodyHTML);

  } catch (err) {
    console.error('Error:', err.message);
    await page.screenshot({
      path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/phase9-projects-error.png',
      fullPage: true,
    });
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
