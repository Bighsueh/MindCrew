/**
 * Investigate P1 modal structure
 */
const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  // Login
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
  await page.locator('input[type="email"]').first().fill('teacher@test.com');
  await page.locator('input[type="password"]').first().fill('teacher123');
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/(projects|dashboard)/, { timeout: 15000 });
  await page.waitForTimeout(1000);

  // Clear storage to suppress tours
  await page.evaluate(() => {
    localStorage.setItem('mindcrew.firstrun.projects', '1');
    sessionStorage.setItem('mindcrew.projectsTour.shown', '1');
  });

  await page.goto('http://localhost:5173/projects', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Remove overlays
  await page.evaluate(() => {
    document.body.classList.remove('driver-active', 'driver-fade');
    document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element').forEach(e => e.remove());
  });

  // Screenshot before clicking button
  await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-before-click.png' });

  // Get all buttons
  const buttons = await page.locator('button').allTextContents();
  console.log('Buttons on projects page:', buttons);

  // Click 新增專案
  const newBtn = page.locator('button:has-text("新增專案"), button:has-text("建立"), button:has-text("Create")').first();
  await newBtn.click();
  await page.waitForTimeout(2000);

  // Screenshot after clicking
  await page.screenshot({ path: '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots/p1-modal-open.png' });

  // Get modal HTML structure
  const modalHtml = await page.evaluate(() => {
    const modal = document.querySelector('[class*="modal"], [class*="dialog"], [role="dialog"], .fixed.inset-0');
    if (modal) return modal.innerHTML.substring(0, 3000);
    return 'No modal found';
  });
  console.log('\nModal HTML:', modalHtml.substring(0, 2000));

  // Get all inputs in modal
  const inputs = await page.evaluate(() => {
    const allInputs = document.querySelectorAll('input, textarea');
    return Array.from(allInputs).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      name: i.name,
      id: i.id,
      class: i.className.substring(0, 50),
      visible: i.offsetParent !== null
    }));
  });
  console.log('\nAll inputs:', JSON.stringify(inputs, null, 2));

  // Check if modal backdrop is present
  const hasBackdrop = await page.evaluate(() => {
    const backdrop = document.querySelector('[aria-hidden="true"][class*="inset-0"]');
    return backdrop ? backdrop.className : 'no backdrop';
  });
  console.log('\nBackdrop:', hasBackdrop);

  await browser.close();
}

main().catch(console.error);
