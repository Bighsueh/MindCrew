/**
 * Define Phase Stall Investigation Script
 *
 * Investigates why agents get stuck in the Define phase
 * and never advance to Develop.
 */

const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ─── Configuration ───────────────────────────────────────────────────────────
const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const PROJECT_ID = '732b450a-4925-4059-b302-11c717859db2';
const SCREENSHOTS_DIR = '/Users/hsueh/Code/Experimental/MindCrew/e2e/screenshots';
const REPORT_FILE = '/Users/hsueh/Code/Experimental/MindCrew/e2e/define-stall-report.json';

const CHECK_INTERVAL_MS = 60_000;  // 60 seconds
const TOTAL_DURATION_MS = 720_000; // 12 minutes

// ─── State tracking ──────────────────────────────────────────────────────────
const timeline = [];
let token = null;
let checkIndex = 0;

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function timestamp() {
  return new Date().toISOString();
}

function log(msg) {
  const ts = new Date().toLocaleTimeString('zh-TW', { hour12: false });
  console.log(`[${ts}] ${msg}`);
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error(`GET ${path} → HTTP ${res.status}`);
  return res.json();
}

async function getBackendLogs(sinceSec = 65) {
  try {
    const cmd = `docker logs mindcrew-backend-1 --since=${sinceSec}s 2>&1 | grep -E "stage eval|passed|micro_advanced|Time pressure|consecutive_pass|quant_score|threshold|define|DEFINE|advance|ADVANCE|evaluator|EVALUATOR|score|SCORE" | tail -30`;
    return execSync(cmd, { encoding: 'utf-8', timeout: 10000 });
  } catch (e) {
    return `(log fetch error: ${e.message})`;
  }
}

async function getStageInfo() {
  const stage = await apiGet(`/api/projects/${PROJECT_ID}/stage`);
  return {
    current_stage: stage.current_stage,
    current_micro_phase: stage.current_micro_phase,
    raw: stage
  };
}

async function getMessageStats() {
  try {
    const msgs = await apiGet(`/api/projects/${PROJECT_ID}/messages?limit=500`);
    const list = Array.isArray(msgs) ? msgs : (msgs.messages || msgs.items || []);
    const senders = new Set(list.map(m => m.sender_id || m.agent_id || m.role || 'unknown'));
    return {
      total: list.length,
      unique_senders: senders.size,
      senders: [...senders]
    };
  } catch (e) {
    return { total: 0, unique_senders: 0, senders: [], error: e.message };
  }
}

async function takeScreenshot(page, label) {
  const filename = `define-stall-${String(checkIndex).padStart(3, '0')}-${label}.png`;
  const filepath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  log(`Screenshot: ${filename}`);
  return filepath;
}

// ─── Main Observation Loop ────────────────────────────────────────────────────

async function runInvestigation() {
  log('=== Define Phase Stall Investigation START ===');
  log(`Project ID: ${PROJECT_ID}`);

  // Step 1: Get auth token
  log('Getting auth token...');
  const authRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD })
  });
  const authData = await authRes.json();
  token = authData.access_token;
  log(`Token obtained for: ${authData.user?.display_name}`);

  // Step 2: Initial stage check
  log('Initial stage check...');
  const initialStage = await getStageInfo();
  log(`Initial stage: ${initialStage.current_stage} / micro: ${initialStage.current_micro_phase}`);

  // Step 3: Launch browser
  log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  // Capture console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      log(`[BROWSER ERROR] ${msg.text()}`);
    }
  });

  // Step 4: Login
  log('Logging in via browser...');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(lobby|projects)/, { timeout: 15000 }).catch(() => {});
  log(`After login URL: ${page.url()}`);

  // Step 5: Navigate to lobby
  log(`Navigating to project lobby...`);
  await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/lobby`, { waitUntil: 'networkidle' });
  await sleep(2000);
  await takeScreenshot(page, 'lobby');

  // Step 6: Click observer button
  log('Looking for Observer button...');
  const observerBtn = page.locator('button:has-text("觀察者"), button:has-text("observer"), button:has-text("Observer")').first();
  if (await observerBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await observerBtn.click();
    await sleep(2000);
    log('Clicked Observer button');
  } else {
    log('Observer button not found, checking page state...');
    const buttons = await page.locator('button').allTextContents();
    log(`Available buttons: ${JSON.stringify(buttons.slice(0, 10))}`);
  }
  await takeScreenshot(page, 'after-observer-click');

  // Step 7: Navigate to workspace
  log('Navigating to workspace...');
  await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workspace`, { waitUntil: 'networkidle' });
  await sleep(3000);
  await takeScreenshot(page, 'workspace-initial');

  // ─── Observation Loop ──────────────────────────────────────────────────────
  const startTime = Date.now();
  let lastStage = null;
  let lastMicro = null;
  let stuckSince = null;
  let stuckDurationMs = 0;

  log('\n=== Starting 12-minute observation loop ===\n');

  while (Date.now() - startTime < TOTAL_DURATION_MS) {
    checkIndex++;
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    log(`\n--- Check #${checkIndex} (T+${elapsed}s) ---`);

    // Collect data in parallel
    const [stageInfo, msgStats] = await Promise.all([
      getStageInfo().catch(e => ({ error: e.message })),
      getMessageStats()
    ]);

    const backendLogs = await getBackendLogs(70);

    // Detect transitions
    const stageChanged = lastStage !== null && stageInfo.current_stage !== lastStage;
    const microChanged = lastMicro !== null && stageInfo.current_micro_phase !== lastMicro;

    if (stageChanged) {
      log(`STAGE TRANSITION: ${lastStage} → ${stageInfo.current_stage}`);
      stuckSince = null;
    }
    if (microChanged) {
      log(`MICRO TRANSITION: ${lastMicro} → ${stageInfo.current_micro_phase}`);
      stuckSince = null;
    }

    // Track being stuck
    if (!stageChanged && !microChanged && lastStage !== null) {
      if (!stuckSince) stuckSince = Date.now();
      stuckDurationMs = Date.now() - stuckSince;
      if (stuckDurationMs > 120_000) {
        log(`*** STUCK DETECTED: ${stageInfo.current_stage}/${stageInfo.current_micro_phase} for ${Math.round(stuckDurationMs/1000)}s ***`);
      }
    } else if (stageChanged || microChanged) {
      stuckSince = null;
      stuckDurationMs = 0;
    }

    lastStage = stageInfo.current_stage;
    lastMicro = stageInfo.current_micro_phase;

    // Log current state
    log(`Stage: ${stageInfo.current_stage} / Micro: ${stageInfo.current_micro_phase}`);
    log(`Messages: ${msgStats.total} total, ${msgStats.unique_senders} unique senders`);
    log(`Senders: ${msgStats.senders.join(', ')}`);

    // Extract key evaluator metrics from logs
    const logLines = backendLogs.split('\n').filter(l => l.trim());
    if (logLines.length > 0) {
      log(`Backend log excerpt (${logLines.length} lines):`);
      logLines.slice(-10).forEach(l => log(`  ${l}`));
    } else {
      log('Backend logs: (no matching lines)');
    }

    // Take screenshot
    await page.reload({ waitUntil: 'networkidle' }).catch(() => {});
    await sleep(1000);
    const screenshotPath = await takeScreenshot(page, `${stageInfo.current_stage}-${stageInfo.current_micro_phase}`);

    // Record checkpoint
    const checkpoint = {
      check_number: checkIndex,
      timestamp: timestamp(),
      elapsed_seconds: elapsed,
      stage: stageInfo.current_stage,
      micro_phase: stageInfo.current_micro_phase,
      message_count: msgStats.total,
      unique_senders: msgStats.unique_senders,
      senders: msgStats.senders,
      stage_changed: stageChanged,
      micro_changed: microChanged,
      stuck_duration_seconds: Math.round(stuckDurationMs / 1000),
      backend_logs: logLines,
      screenshot: screenshotPath,
      stage_raw: stageInfo.raw
    };
    timeline.push(checkpoint);

    // Save intermediate report
    fs.writeFileSync(REPORT_FILE, JSON.stringify({
      project_id: PROJECT_ID,
      start_time: new Date(startTime).toISOString(),
      total_checks: checkIndex,
      timeline
    }, null, 2));

    // Wait for next check
    const remaining = CHECK_INTERVAL_MS - (Date.now() % CHECK_INTERVAL_MS);
    const waitMs = Math.min(CHECK_INTERVAL_MS, remaining + 1000);
    log(`Waiting ${Math.round(waitMs/1000)}s until next check...`);
    await sleep(waitMs);
  }

  // ─── Final Analysis ────────────────────────────────────────────────────────
  log('\n=== FINAL ANALYSIS ===\n');

  // Get extended backend logs for full picture
  const fullLogs = execSync(
    `docker logs mindcrew-backend-1 --since=720s 2>&1 | grep -E "stage eval|passed|micro_advanced|Time pressure|consecutive_pass|quant_score|threshold|define|DEFINE|advance|ADVANCE|evaluator|score" | head -100`,
    { encoding: 'utf-8', timeout: 15000 }
  );

  // Stage transition summary
  log('\nStage/Micro Transition Timeline:');
  let prevStage = null, prevMicro = null;
  for (const cp of timeline) {
    if (cp.stage !== prevStage || cp.micro_phase !== prevMicro) {
      log(`  T+${cp.elapsed_seconds}s → ${cp.stage} / ${cp.micro_phase}`);
      prevStage = cp.stage;
      prevMicro = cp.micro_phase;
    }
  }

  // Stuck analysis
  const maxStuck = timeline.reduce((max, cp) => Math.max(max, cp.stuck_duration_seconds), 0);
  const stuckCheckpoints = timeline.filter(cp => cp.stuck_duration_seconds > 60);
  log(`\nMax stuck duration: ${maxStuck}s`);
  log(`Checkpoints where stuck > 60s: ${stuckCheckpoints.length}`);

  // Final stage
  const lastCheckpoint = timeline[timeline.length - 1];
  log(`\nFinal state: ${lastCheckpoint?.stage} / ${lastCheckpoint?.micro_phase}`);
  log(`Final message count: ${lastCheckpoint?.message_count}`);

  // Take final screenshot
  await page.reload({ waitUntil: 'networkidle' }).catch(() => {});
  await sleep(2000);
  await takeScreenshot(page, 'FINAL');

  // Save final report
  const report = {
    project_id: PROJECT_ID,
    start_time: new Date(startTime).toISOString(),
    end_time: timestamp(),
    total_duration_seconds: Math.round((Date.now() - startTime) / 1000),
    total_checks: checkIndex,
    final_stage: lastCheckpoint?.stage,
    final_micro_phase: lastCheckpoint?.micro_phase,
    final_message_count: lastCheckpoint?.message_count,
    max_stuck_seconds: maxStuck,
    stage_transitions: timeline
      .filter(cp => cp.stage_changed || cp.micro_changed)
      .map(cp => ({
        at_seconds: cp.elapsed_seconds,
        stage: cp.stage,
        micro_phase: cp.micro_phase
      })),
    timeline,
    full_backend_logs: fullLogs
  };

  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));
  log(`\nReport saved to: ${REPORT_FILE}`);

  await browser.close();
  log('\n=== Investigation COMPLETE ===');

  return report;
}

// ─── Entry Point ──────────────────────────────────────────────────────────────
runInvestigation().then(report => {
  console.log('\n========== SUMMARY ==========');
  console.log(`Final Stage: ${report.final_stage}`);
  console.log(`Final Micro Phase: ${report.final_micro_phase}`);
  console.log(`Max Stuck Duration: ${report.max_stuck_seconds}s`);
  console.log(`Stage Transitions:`);
  report.stage_transitions.forEach(t => {
    console.log(`  T+${t.at_seconds}s → ${t.stage} / ${t.micro_phase}`);
  });
  process.exit(0);
}).catch(err => {
  console.error('Investigation FAILED:', err);
  process.exit(1);
});
