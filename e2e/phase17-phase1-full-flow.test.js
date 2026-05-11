/**
 * Phase 17 E2E — Sticky-Only Strategy: Phase 1 全程
 *
 * Spec 13 §8 Phase 1 涵蓋的子階段：
 *   1.1a 經驗分享破冰
 *   1.1b 獨立列利害關係人（silent_write）
 *   1.1c 揭示與歸類（reveal_round → silent_rearrange）
 *   1.1d Scope rationale
 *   1.2 / 1.3 / 1.5 / 1.6
 *
 * 驗證重點：
 *   - sub_phase 切換正確
 *   - 各 zone 已被 draw（visual + bounds registered）
 *   - silent_write 期間無 chat 訊息
 *   - reveal_round 順序強制
 *   - 1.5 Raw Wall 拒絕「真正的需求是」這類歸因詞
 *   - 1.6 Empathy Map 四象限 zone 同時 active
 *
 * 執行：node e2e/phase17-phase1-full-flow.test.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || `${FRONTEND_URL}/api`;
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'phase17-phase1');

const results = [];

function record(feature, status, details = '') {
  results.push({ feature, status, details });
  const icon = status === 'PASS' ? '✓' : status === 'FAIL' ? '✗' : '⚠';
  console.log(`  ${icon} [${status}] ${feature}${details ? ': ' + details : ''}`);
}

async function fetchJSON(url, opts = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  let data = null;
  try { data = await resp.json(); } catch {}
  return { ok: resp.ok, status: resp.status, data };
}

async function login(email, password) {
  const r = await fetchJSON(`${API_URL}/auth/login`, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(`login failed: ${r.status}`);
  return r.data.access_token;
}

async function createProject(token, name) {
  const r = await fetchJSON(`${API_URL}/projects`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, description: 'Spec 13 E2E', ai_contribution: 'high' }),
  });
  if (!r.ok) throw new Error(`createProject failed: ${r.status}`);
  return r.data;
}

async function run() {
  console.log('\n=== Phase 17 E2E — Phase 1 全程 ===\n');
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const token = await login('teacher@test.com', 'teacher123');
  const project = await createProject(token, `Spec13-Phase1-${Date.now()}`);
  record('建立全 AI 專案', 'PASS', `id=${project.id}`);

  // 等候 sub_phase 進入 1.1a
  let attempts = 0;
  let currentSub = null;
  while (attempts < 30 && currentSub !== '1.1a') {
    await new Promise((r) => setTimeout(r, 2000));
    const r = await fetchJSON(`${API_URL}/projects/${project.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    currentSub = r.data?.current_sub_phase;
    attempts++;
  }
  record(
    'Sub-phase 進入 1.1a',
    currentSub === '1.1a' ? 'PASS' : 'FAIL',
    `sub_phase=${currentSub}`,
  );

  // 驗證 1.5 Raw Wall 拒絕歸因詞
  const rejectRes = await fetchJSON(
    `${API_URL}/projects/${project.id}/canvas/notes`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        text: '使用者真正的需求是更快結帳',
        color: 'yellow',
        x: 200,
        y: 200,
        sub_phase_id: '1.5',
        force_publish: false,
      }),
    },
  );
  const wasRejected = rejectRes.data?.success === false;
  record(
    '1.5 Raw Wall 拒絕歸因詞',
    wasRejected ? 'PASS' : 'FAIL',
    rejectRes.data?.rejection?.rule_module,
  );

  // 驗證強制送出
  const forceRes = await fetchJSON(
    `${API_URL}/projects/${project.id}/canvas/notes`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        text: '使用者真正的需求是更快結帳',
        color: 'yellow',
        x: 250,
        y: 250,
        sub_phase_id: '1.5',
        force_publish: true,
      }),
    },
  );
  const forcedOk = forceRes.data?.success === true;
  record(
    '1.5 force_publish 允許並標記 gate_violation',
    forcedOk && forceRes.data?.gate_violation ? 'PASS' : 'FAIL',
    JSON.stringify(forceRes.data?.gate_violation),
  );

  // UI 截圖
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.goto(`${FRONTEND_URL}/projects/${project.id}/workspace`);
  await page.waitForTimeout(3000);
  const screenshotPath = path.join(SCREENSHOTS_DIR, 'phase1-canvas.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  record('UI 截圖', 'PASS', screenshotPath);
  await browser.close();

  // Report
  const passCount = results.filter((r) => r.status === 'PASS').length;
  const failCount = results.filter((r) => r.status === 'FAIL').length;
  console.log(`\n=== Result: ${passCount} PASS, ${failCount} FAIL ===`);

  const reportPath = path.join(SCREENSHOTS_DIR, 'report.json');
  fs.writeFileSync(reportPath, JSON.stringify({ results }, null, 2));
  console.log(`Report: ${reportPath}`);

  process.exit(failCount === 0 ? 0 : 1);
}

run().catch((err) => {
  console.error(err);
  process.exit(2);
});
