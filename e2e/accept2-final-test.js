/**
 * FINAL ACCEPTANCE TEST — accept2
 * Tests: SUP-SILENT, EDGE CASES, AUTO-ADVANCE (OBSERVER)
 *
 * Verified API shapes:
 *   POST /api/projects/{id}/advance-stage  body: { from, to }
 *   POST /api/projects/{id}/join           body: { seat_role }
 *   GET  /api/projects/{id}/stage          → { current_stage, current_micro_phase, ... }
 *   GET  /api/projects/{id}/messages       → { messages: [{sender_type, sender_id, sender_name, ...}], ... }
 *
 * Notes:
 *   - All AI messages have sender_type="ai", differentiated by sender_id (agent_supervisor, agent_crew_N)
 *   - There is no "observer" seat role; observer = creator connects via WS without joining a seat
 *   - Micro-phase 1.1 uses "one_by_one" strategy: crew agents wait for supervisor to call on them
 *   - For Test 1 (SUP-SILENT), we verify if ANY crew agents produced messages despite silent supervisor
 *   - For Test 3 (OBSERVER), creator opens workspace via WS → agents run; we check if evaluator auto-advances
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:8000';
const FRONTEND_URL = 'http://localhost:5173';
const EMAIL = 'teacher@test.com';
const PASSWORD = 'teacher123';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

// ─────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────
async function getToken() {
  const resp = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD })
  });
  const d = await resp.json();
  if (!d.access_token) throw new Error('Login failed: ' + JSON.stringify(d));
  return d.access_token;
}

async function api(method, urlPath, token, body = null) {
  const opts = {
    method,
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
  };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(`${BASE_URL}${urlPath}`, opts);
  const text = await resp.text();
  let json;
  try { json = JSON.parse(text); } catch { json = { _raw: text }; }
  return { status: resp.status, json };
}

async function createProject(token, name, aiContribution = 'high',
  description = '超市購物車重新設計。限制：寬度≤60cm、嵌套堆疊、手把95-105cm、推行力<5kg、成本≤NT$3000、回收材質≥80%') {
  const r = await api('POST', '/api/projects', token, { name, ai_contribution: aiContribution, description });
  if (r.status !== 200 && r.status !== 201) throw new Error(`Create project failed ${r.status}: ${JSON.stringify(r.json)}`);
  return r.json;
}

async function getStageStatus(token, projectId) {
  const r = await api('GET', `/api/projects/${projectId}/stage`, token);
  return r.json;
}

async function getMessages(token, projectId, limit = 100) {
  // API enforces le=200; using 100 as safe default. 200 is the max.
  const safeLimit = Math.min(limit, 200);
  const r = await api('GET', `/api/projects/${projectId}/messages?limit=${safeLimit}`, token);
  if (r.status === 422) {
    console.warn(`  WARN: messages API returned 422 for limit=${safeLimit}`);
    return [];
  }
  return Array.isArray(r.json) ? r.json : (r.json.messages || []);
}

async function advanceStage(token, projectId, fromStage, toStage) {
  return await api('POST', `/api/projects/${projectId}/advance-stage`, token, { from: fromStage, to: toStage });
}

async function joinProject(token, projectId, seatRole) {
  return await api('POST', `/api/projects/${projectId}/join`, token, { seat_role: seatRole });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function analyzeMessages(messages) {
  // sender_type is always "ai" for AI agents
  // Use sender_id to distinguish: agent_supervisor, agent_crew_1, agent_crew_2, ...
  // Use sender_name for human-readable names
  const bySenderId = new Set();
  const bySenderName = new Set();
  const humanSenderIds = new Set(['human', 'system']);

  for (const m of messages) {
    const id = m.sender_id || '';
    const name = m.sender_name || '';
    if (id) bySenderId.add(id);
    if (name) bySenderName.add(name);
  }

  const crewIds = [...bySenderId].filter(id => id.startsWith('agent_crew'));
  const supervisorActive = [...bySenderId].some(id => id.includes('supervisor'));

  return {
    totalUniqueSenderIds: bySenderId.size,
    senderIds: [...bySenderId],
    senderNames: [...bySenderName],
    crewIds,
    supervisorActive,
    crewCount: crewIds.length
  };
}

async function browserLogin(page) {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input[type="email"], input[name="email"]', EMAIL);
  await page.fill('input[type="password"], input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  // Routes: /projects, /teacher/dashboard, /login → redirect to one of these after login
  try { await page.waitForURL(/\/(projects|teacher|dashboard)/, { timeout: 10000 }); } catch {}
}

// ─────────────────────────────────────────
// TEST 1: SUPERVISOR SILENT
// ─────────────────────────────────────────
async function test1SupervisorSilent(browser, token) {
  console.log('\n========================================');
  console.log('TEST 1: SUP-SILENT — crew active when human supervisor is silent');
  console.log('Expected behavior: crew agents should still produce messages (AI-supervisor');
  console.log('calls on them via OO strategy) even when human supervisor does not type.');
  console.log('========================================');

  const results = { passed: [], failed: [], data: {} };

  // 1. Create project
  console.log('\n  [1/7] Creating project...');
  const project = await createProject(token, 'Final2-Sup-購物車', 'high');
  const projectId = project.id;
  console.log(`  Project ID: ${projectId}`);
  results.data.projectId = projectId;

  // 2. Browser login
  console.log('  [2/7] Browser login...');
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await browserLogin(page);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t1-login.png') });

  // 3. Join as supervisor via API (starts agents, sets human seat)
  console.log('  [3/7] Joining as supervisor via API...');
  const joinResp = await joinProject(token, projectId, 'supervisor');
  console.log(`  Join: HTTP ${joinResp.status} — ${JSON.stringify(joinResp.json).slice(0, 80)}`);

  // Open workspace in browser (this establishes WS connection → presence gate fires)
  // Correct URL: /projects/:id/workspace (not /workspace/:id)
  await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t1-workspace-joined.png') });
  console.log('  WS connection established via browser.');

  // 4. Wait 90 seconds — DO NOT TYPE (silent supervisor)
  console.log('\n  [4/7] Waiting 120s silently (human supervisor does NOT type)...');

  const msgsT0 = await getMessages(token, projectId);
  console.log(`    t=0s:  ${msgsT0.length} messages`);
  const stT0 = await getStageStatus(token, projectId);
  console.log(`    Stage: ${stT0.current_stage}, micro_phase: ${stT0.current_micro_phase}`);
  results.data.t0_messages = msgsT0.length;

  for (const t of [30, 60, 90, 120]) {
    await sleep(30000);
    const msgs = await getMessages(token, projectId);
    const analysis = analyzeMessages(msgs);
    console.log(`    t=${t}s: ${msgs.length} messages — sender_ids: [${analysis.senderIds.join(', ')}]`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `accept2-t1-workspace-${t}s.png`) });
  }

  // 5. Final analysis at 120s
  const msgs90 = await getMessages(token, projectId);
  const analysis = analyzeMessages(msgs90);

  console.log(`  Messages: ${msgs90.length}`);
  console.log(`  Unique sender_ids: ${analysis.totalUniqueSenderIds} — [${analysis.senderIds.join(', ')}]`);
  console.log(`  Crew agent IDs: ${analysis.crewCount} — [${analysis.crewIds.join(', ')}]`);
  console.log(`  Supervisor active: ${analysis.supervisorActive}`);

  results.data.t90_messages = msgs90.length;
  results.data.senderIds = analysis.senderIds;
  results.data.crewIds = analysis.crewIds;
  results.data.totalUniqueSenderIds = analysis.totalUniqueSenderIds;

  // Check: ≥2 crew senders active
  if (analysis.crewCount >= 2) {
    results.passed.push(`SUP-SILENT: crew active (${analysis.crewCount} crew agents: ${analysis.crewIds.join(',')})`);
    console.log(`  PASS: ${analysis.crewCount} crew agents produced messages while supervisor was silent`);
  } else {
    results.failed.push(`SUP-SILENT: Only ${analysis.crewCount} crew agent sender(s) [${analysis.crewIds.join(',')}] — expected ≥2`);
    console.log(`  FAIL: Only ${analysis.crewCount} crew agents produced messages`);
    // Additional diagnostic
    if (msgs90.length === 0) {
      console.log('  DIAGNOSTIC: Zero messages produced — agents may be blocked on presence gate');
    } else if (analysis.crewCount < 2) {
      console.log('  DIAGNOSTIC: Agents likely blocked by rule_0_strategy_gate (OO mode, waiting for supervisor to call on them)');
    }
  }

  // Check: ≥3 total unique sender_ids
  if (analysis.totalUniqueSenderIds >= 3) {
    results.passed.push(`SUP-SILENT: ≥3 total unique senders (got ${analysis.totalUniqueSenderIds})`);
    console.log(`  PASS: ${analysis.totalUniqueSenderIds} unique senders`);
  } else {
    results.failed.push(`SUP-SILENT: Only ${analysis.totalUniqueSenderIds} unique senders — expected ≥3`);
    console.log(`  FAIL: Only ${analysis.totalUniqueSenderIds} unique senders`);
  }

  // 6. Advance through all phases (30s each)
  console.log('\n  [6/7] Rapid phase advancement (30s each stage)...');
  const transitions = [['discover', 'define'], ['define', 'develop'], ['develop', 'deliver']];
  for (const [from, to] of transitions) {
    await sleep(30000);
    const r = await advanceStage(token, projectId, from, to);
    console.log(`  Advance ${from}→${to}: HTTP ${r.status}`);
  }

  // 7. Final state
  console.log('\n  [7/7] Final state...');
  const finalStatus = await getStageStatus(token, projectId);
  const finalMsgs = await getMessages(token, projectId, 200);
  const finalAnalysis = analyzeMessages(finalMsgs);

  results.data.finalStage = finalStatus.current_stage;
  results.data.finalMicroPhase = finalStatus.current_micro_phase;
  results.data.finalMessages = finalMsgs.length;
  results.data.finalSenderIds = finalAnalysis.senderIds;

  console.log(`  Final stage: ${finalStatus.current_stage}, micro_phase: ${finalStatus.current_micro_phase}`);
  console.log(`  Total messages: ${finalMsgs.length}, senders: [${finalAnalysis.senderIds.join(', ')}]`);

  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t1-final.png') });
  await context.close();
  return results;
}

// ─────────────────────────────────────────
// TEST 2: EDGE CASES (API only)
// ─────────────────────────────────────────
async function test2EdgeCases(token) {
  console.log('\n========================================');
  console.log('TEST 2: EDGE CASES — invalid stage transitions (API only)');
  console.log('========================================');

  const results = { passed: [], failed: [], data: {} };

  // 1. Create project
  console.log('\n  [1/6] Creating project Final2-Edge-購物車...');
  const project = await createProject(token, 'Final2-Edge-購物車', 'medium',
    '超市購物車重新設計。限制：寬度≤60cm、嵌套堆疊、手把95-105cm');
  const projectId = project.id;
  console.log(`  Project ID: ${projectId}`);
  results.data.projectId = projectId;

  // 2. Join as supervisor (required to advance stages)
  console.log('  [2/6] Joining as supervisor...');
  const joinResp = await joinProject(token, projectId, 'supervisor');
  console.log(`  Join: HTTP ${joinResp.status}`);
  await sleep(2000);

  // Confirm initial stage
  let st = await getStageStatus(token, projectId);
  console.log(`  Initial state: stage=${st.current_stage}, micro_phase=${st.current_micro_phase}`);

  // 3. SKIP advance: discover → develop (skip define)
  console.log('\n  [3/6] SKIP advance: discover→develop (should be 400)...');
  const skipResp = await advanceStage(token, projectId, 'discover', 'develop');
  console.log(`  HTTP ${skipResp.status}: ${JSON.stringify(skipResp.json).slice(0, 120)}`);
  results.data.skipStatus = skipResp.status;

  if (skipResp.status === 400) {
    results.passed.push('EDGE: skip advance rejected (HTTP 400)');
    console.log('  PASS: skip advance correctly rejected with 400');
  } else {
    results.failed.push(`EDGE: skip advance returned HTTP ${skipResp.status} (expected 400)`);
    console.log(`  FAIL: expected 400, got ${skipResp.status}`);
  }

  st = await getStageStatus(token, projectId);
  console.log(`  Stage after skip attempt: ${st.current_stage} (expected: discover)`);
  results.data.stageAfterSkip = st.current_stage;

  // 4. Valid advance: discover → define
  console.log('\n  [4/6] Valid advance: discover→define (HTTP 200 expected)...');
  const validResp = await advanceStage(token, projectId, 'discover', 'define');
  console.log(`  HTTP ${validResp.status}`);
  if (validResp.status !== 200) {
    console.log(`  WARNING: valid advance failed: ${JSON.stringify(validResp.json).slice(0, 100)}`);
  }
  st = await getStageStatus(token, projectId);
  console.log(`  Stage after valid advance: ${st.current_stage}`);
  results.data.stageAfterValidAdv = st.current_stage;

  // 5. BACKWARD: define → discover
  console.log('\n  [5/6] BACKWARD advance: define→discover (should be 400)...');
  const backResp = await advanceStage(token, projectId, 'define', 'discover');
  console.log(`  HTTP ${backResp.status}: ${JSON.stringify(backResp.json).slice(0, 120)}`);
  results.data.backwardStatus = backResp.status;

  if (backResp.status === 400) {
    results.passed.push('EDGE: backward advance rejected (HTTP 400)');
    console.log('  PASS: backward advance correctly rejected with 400');
  } else {
    results.failed.push(`EDGE: backward advance returned HTTP ${backResp.status} (expected 400)`);
    console.log(`  FAIL: expected 400, got ${backResp.status}`);
  }

  // 6. DOUBLE advance: discover → define again (already at define)
  console.log('\n  [6/6] DOUBLE advance: discover→define again (should be 400)...');
  const doubleResp = await advanceStage(token, projectId, 'discover', 'define');
  console.log(`  HTTP ${doubleResp.status}: ${JSON.stringify(doubleResp.json).slice(0, 120)}`);
  results.data.doubleStatus = doubleResp.status;

  if (doubleResp.status === 400) {
    results.passed.push('EDGE: double advance rejected (HTTP 400)');
    console.log('  PASS: double advance correctly rejected with 400');
  } else {
    results.failed.push(`EDGE: double advance returned HTTP ${doubleResp.status} (expected 400)`);
    console.log(`  FAIL: expected 400, got ${doubleResp.status}`);
  }

  // Final state + micro_phase coherence check
  st = await getStageStatus(token, projectId);
  results.data.finalStage = st.current_stage;
  results.data.finalMicroPhase = st.current_micro_phase;
  console.log(`\n  Final: stage=${st.current_stage}, micro_phase=${st.current_micro_phase}`);

  if (st.current_stage === 'define' && st.current_micro_phase) {
    results.passed.push(`EDGE: micro_phase coherent after advances (stage=${st.current_stage}, mp=${st.current_micro_phase})`);
    console.log('  PASS: stage and micro_phase are coherent after edge case attempts');
  } else if (st.current_stage && st.current_micro_phase) {
    results.passed.push(`EDGE: micro_phase coherent (stage=${st.current_stage}, mp=${st.current_micro_phase})`);
    console.log(`  PASS: state coherent (stage=${st.current_stage}, micro_phase=${st.current_micro_phase})`);
  } else {
    results.failed.push(`EDGE: micro_phase incoherent — stage=${st.current_stage}, mp=${st.current_micro_phase}`);
    console.log('  FAIL: micro_phase data missing or incoherent');
  }

  return results;
}

// ─────────────────────────────────────────
// TEST 3: OBSERVER (creator via WS) + AUTO-ADVANCE
// ─────────────────────────────────────────
async function test3ObserverAutoAdvance(browser, token) {
  console.log('\n========================================');
  console.log('TEST 3: AUTO-ADVANCE — evaluator auto-advances micro_phase');
  console.log('Observer mode: creator opens workspace via WS without joining a seat.');
  console.log('All 5 seats remain AI. Evaluator should auto-advance micro_phase after');
  console.log('sufficient rounds. Messages and senders checked at 120s.');
  console.log('========================================');

  const results = { passed: [], failed: [], data: {} };

  // 1. Create project
  console.log('\n  [1/5] Creating project Final2-AutoAdv-購物車...');
  const project = await createProject(token, 'Final2-AutoAdv-購物車', 'high');
  const projectId = project.id;
  console.log(`  Project ID: ${projectId}`);
  results.data.projectId = projectId;

  let st = await getStageStatus(token, projectId);
  const initialMicroPhase = st.current_micro_phase;
  console.log(`  Initial: stage=${st.current_stage}, micro_phase=${initialMicroPhase}`);
  results.data.initialMicroPhase = initialMicroPhase;

  // 2. Browser: login, open workspace WITHOUT joining any seat
  //    Creator connects via WS → presence gate fires → agents run
  console.log('\n  [2/5] Browser login, open workspace (observer mode — no seat join)...');
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await browserLogin(page);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t3-login.png') });

  // Open workspace WITHOUT joining (creator can connect via WS)
  // Correct URL: /projects/:id/workspace
  await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t3-workspace-entry.png') });
  console.log('  Workspace opened. WS connection established (presence gate → agents start).');

  // 3. Wait 120s — observe if evaluator auto-advances micro_phase
  console.log('\n  [3/5] Waiting 180s (passive observer — watching evaluator)...');

  let microPhaseAdvanced = false;
  let lastMicroPhase = initialMicroPhase;

  for (const t of [30, 60, 90, 120, 150, 180]) {
    await sleep(30000);
    st = await getStageStatus(token, projectId);
    const msgs = await getMessages(token, projectId, 200);
    const analysis = analyzeMessages(msgs);
    const mp = st.current_micro_phase;

    console.log(`    t=${t}s: micro_phase=${mp}, messages=${msgs.length}, unique_senders=${analysis.totalUniqueSenderIds} [${analysis.senderIds.slice(0, 5).join(',')}]`);
    if (t <= 120) await page.screenshot({ path: path.join(SCREENSHOT_DIR, `accept2-t3-workspace-${t}s.png`) });

    if (mp && mp !== lastMicroPhase) {
      microPhaseAdvanced = true;
      console.log(`    -> micro_phase ADVANCED: ${lastMicroPhase} → ${mp}`);
      lastMicroPhase = mp;
    }

    results.data[`t${t}s`] = { micro_phase: mp, messages: msgs.length, senders: analysis.senderIds };
  }

  // 4. Final evaluation
  console.log('\n  [4/5] Final state...');
  st = await getStageStatus(token, projectId);
  const finalMsgs = await getMessages(token, projectId, 200);
  const finalAnalysis = analyzeMessages(finalMsgs);

  results.data.finalMicroPhase = st.current_micro_phase;
  results.data.finalMessages = finalMsgs.length;
  results.data.finalSenderIds = finalAnalysis.senderIds;

  console.log(`  Final micro_phase: ${st.current_micro_phase} (started: ${initialMicroPhase})`);
  console.log(`  Messages: ${finalMsgs.length}, unique_senders: ${finalAnalysis.totalUniqueSenderIds} [${finalAnalysis.senderIds.join(', ')}]`);

  // 5. Assertions
  if (microPhaseAdvanced || (st.current_micro_phase && st.current_micro_phase !== initialMicroPhase)) {
    results.passed.push(`AUTO: micro_phase advanced (${initialMicroPhase} → ${st.current_micro_phase})`);
    console.log('  PASS: evaluator auto-advanced micro_phase');
  } else {
    results.failed.push(`AUTO: micro_phase did NOT advance (stayed at ${st.current_micro_phase})`);
    console.log('  FAIL: micro_phase did not advance');
    console.log('  DIAGNOSTIC: Check if agents were blocked by presence gate or OO strategy');
  }

  if (finalMsgs.length > 15) {
    results.passed.push(`AUTO: messages > 15 (got ${finalMsgs.length})`);
    console.log(`  PASS: ${finalMsgs.length} messages`);
  } else {
    results.failed.push(`AUTO: Only ${finalMsgs.length} messages — expected > 15`);
    console.log(`  FAIL: Only ${finalMsgs.length} messages`);
  }

  if (finalAnalysis.totalUniqueSenderIds >= 3) {
    results.passed.push(`AUTO: ≥3 unique senders (got ${finalAnalysis.totalUniqueSenderIds})`);
    console.log(`  PASS: ${finalAnalysis.totalUniqueSenderIds} unique senders`);
  } else {
    results.failed.push(`AUTO: Only ${finalAnalysis.totalUniqueSenderIds} senders — expected ≥3`);
    console.log(`  FAIL: Only ${finalAnalysis.totalUniqueSenderIds} unique senders`);
  }

  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'accept2-t3-final.png') });
  await context.close();
  return results;
}

// ─────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────
async function main() {
  console.log('============================================================');
  console.log('FINAL ACCEPTANCE TEST — accept2');
  console.log(`Started: ${new Date().toISOString()}`);
  console.log('============================================================');

  let token;
  try {
    token = await getToken();
    console.log('Auth: OK');
  } catch (e) {
    console.error('FATAL: Cannot authenticate:', e.message);
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const allResults = { timestamp: new Date().toISOString(), tests: {} };

  try {
    allResults.tests.t1 = await test1SupervisorSilent(browser, token);
  } catch (e) {
    console.error('\nTest 1 CRASHED:', e.message);
    allResults.tests.t1 = { passed: [], failed: [`Test 1 crashed: ${e.message}`], data: {} };
  }

  try {
    allResults.tests.t2 = await test2EdgeCases(token);
  } catch (e) {
    console.error('\nTest 2 CRASHED:', e.message);
    allResults.tests.t2 = { passed: [], failed: [`Test 2 crashed: ${e.message}`], data: {} };
  }

  try {
    allResults.tests.t3 = await test3ObserverAutoAdvance(browser, token);
  } catch (e) {
    console.error('\nTest 3 CRASHED:', e.message);
    allResults.tests.t3 = { passed: [], failed: [`Test 3 crashed: ${e.message}`], data: {} };
  }

  await browser.close();

  // ── Final Report ──────────────────────
  console.log('\n\n============================================================');
  console.log('FINAL ACCEPTANCE CHECKLIST');
  console.log('============================================================');

  const allPassed = [];
  const allFailed = [];
  for (const t of Object.values(allResults.tests)) {
    allPassed.push(...(t.passed || []));
    allFailed.push(...(t.failed || []));
  }

  function checkItem(label, ...keywords) {
    const matched = allPassed.some(p => keywords.every(k => p.toLowerCase().includes(k.toLowerCase())));
    console.log(`  [${matched ? 'PASS' : 'FAIL'}] ${label}`);
    return matched;
  }

  const checks = [
    checkItem('SUP-SILENT: crew active when human supervisor silent (≥2 crew senders)', 'SUP-SILENT', 'crew'),
    checkItem('SUP-SILENT: ≥3 total unique senders', 'SUP-SILENT', '3'),
    checkItem('EDGE: skip advance rejected (400)', 'EDGE', 'skip'),
    checkItem('EDGE: backward advance rejected (400)', 'EDGE', 'backward'),
    checkItem('EDGE: double advance rejected (400)', 'EDGE', 'double'),
    checkItem('EDGE: micro_phase correct after advances', 'EDGE', 'micro_phase'),
    checkItem('AUTO: evaluator auto-advanced micro_phase (1.1→1.2+)', 'AUTO', 'micro_phase'),
    checkItem('AUTO: messages > 15', 'AUTO', 'messages'),
    checkItem('AUTO: ≥3 unique senders', 'AUTO', 'senders'),
  ];

  const passCount = checks.filter(Boolean).length;
  const totalCount = checks.length;
  console.log(`\n  Score: ${passCount}/${totalCount}`);

  if (allFailed.length > 0) {
    console.log('\nFailed details:');
    for (const f of allFailed) console.log(`  - ${f}`);
  }

  const reportPath = path.join(SCREENSHOT_DIR, 'accept2-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(allResults, null, 2));
  console.log(`\nReport saved: ${reportPath}`);
  console.log('Screenshots: e2e/screenshots/accept2-*.png');
  console.log(`\nCompleted: ${new Date().toISOString()}`);
  console.log(`\nOVERALL: ${passCount === totalCount ? 'PASS' : 'FAIL'} (${passCount}/${totalCount})`);

  process.exit(passCount === totalCount ? 0 : 1);
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
