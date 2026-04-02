const { chromium } = require('playwright');

async function main() {
  const TOKEN = process.argv[2];
  const PID = process.argv[3];
  const BASE_URL = 'http://localhost:8000';
  const FRONTEND_URL = 'http://localhost:5173';
  const EMAIL = 'teacher@test.com';
  const PASSWORD = 'teacher123';

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  await page.goto(`${FRONTEND_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input[type="email"], input[name="email"]', EMAIL);
  await page.fill('input[type="password"], input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  try { await page.waitForURL(/\/(lobby|projects|dashboard|workspace)/, { timeout: 10000 }); } catch {}

  await page.goto(`${FRONTEND_URL}/workspace/${PID}`);
  await page.waitForLoadState('networkidle');
  console.log('Workspace opened, waiting for agents...');

  for (let t = 15; t <= 60; t += 15) {
    await new Promise(r => setTimeout(r, 15000));
    const resp = await fetch(`${BASE_URL}/api/projects/${PID}/messages?limit=50`, {
      headers: { 'Authorization': `Bearer ${TOKEN}` }
    });
    const d = await resp.json();
    const msgs = d.messages || [];
    const senders = [...new Set(msgs.map(m => m.sender_name))];
    console.log(`t=${t}s: ${msgs.length} msgs, senders=[${senders.join(', ')}]`);
    
    const sr = await fetch(`${BASE_URL}/api/projects/${PID}/stage`, {
      headers: { 'Authorization': `Bearer ${TOKEN}` }
    });
    const st = await sr.json();
    console.log(`  Stage: ${st.current_stage}, micro_phase: ${st.current_micro_phase}`);
  }

  await browser.close();
}
main().catch(e => { console.error(e); process.exit(1); });
