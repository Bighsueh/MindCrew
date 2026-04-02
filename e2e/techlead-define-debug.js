/**
 * TechLead Define-Phase Debug Test
 *
 * Creates two projects (All-AI observer + Human supervisor) and monitors
 * for 8+ minutes to diagnose why agents get stuck in Define and never
 * advance to Develop.
 *
 * Usage: node techlead-define-debug.js
 */
"use strict";

const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// ── Config ───────────────────────────────────────────────────────────────────
const FRONTEND = "http://localhost:5173";
const BACKEND  = "http://localhost:8000";
const EMAIL    = "teacher@test.com";
const PASSWORD = "teacher123";
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

const MONITOR_DURATION_MS = 9 * 60 * 1000;   // 9 minutes
const POLL_INTERVAL_MS    = 60 * 1000;         // every 60 s

// Description shared by both projects
const PROJECT_DESC =
  "超市購物車重新設計。限制：寬度≤60cm、嵌套堆疊、手把95-105cm、" +
  "推行力<5kg、成本≤NT$3000、回收材質≥80%";

// ── Helpers ──────────────────────────────────────────────────────────────────
function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function log(msg) {
  const ts = new Date().toISOString().replace("T", " ").slice(0, 19);
  console.log(`[${ts}] ${msg}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Fetch JSON from backend with error handling */
async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, { ...opts });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

/** POST to create a project, returns project object */
async function createProject(token, name, aiContribution, description) {
  return fetchJSON(`${BACKEND}/api/projects`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      name,
      ai_contribution: aiContribution,
      description,
    }),
  });
}

/** Login via API, return access token */
async function apiLogin() {
  const res = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Login failed: HTTP ${res.status} — ${text.slice(0, 200)}`);
  }
  const data = await res.json();
  return data.access_token;
}

/** Get current stage info for a project */
async function getStage(projectId, token) {
  return fetchJSON(`${BACKEND}/api/projects/${projectId}/stage`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Get messages for a project — endpoint returns {messages: [...], has_more, next_cursor} */
async function getMessages(projectId, token, limit = 200) {
  const data = await fetchJSON(
    `${BACKEND}/api/projects/${projectId}/messages?limit=${limit}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  // Normalise: could be array (legacy) or {messages:[...]}
  if (Array.isArray(data)) return data;
  return data.messages || [];
}

/** Get micro-phase history */
async function getMicroPhaseHistory(projectId, token) {
  try {
    return await fetchJSON(
      `${BACKEND}/api/projects/${projectId}/micro-phase-history`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
  } catch {
    return [];
  }
}

/** Get recent docker logs filtered for evaluator activity (last 2 minutes) */
async function getDockerLogs(_projectId) {
  const { exec } = require("child_process");
  return new Promise((resolve) => {
    const cmd =
      `docker logs mindcrew-backend-1 --since=2m 2>&1 | grep -E "total=|passed=|action=|Time pressure|micro_phase|advance|threshold|Pre-screen" | grep -v "^$" | tail -25`;
    exec(cmd, { timeout: 10000 }, (_, stdout) => {
      resolve(stdout || "");
    });
  });
}

/** Extract unique senders from messages */
function extractSenders(messages) {
  const senders = new Set();
  for (const m of messages) {
    if (m.sender) senders.add(m.sender);
    if (m.agent_id) senders.add(m.agent_id);
  }
  return [...senders];
}

/** Parse evaluator scores from docker log output.
 *
 * Log format (from base_agent.py):
 *   "Supervisor agent_supervisor stage eval: total=32.5, passed=True, action=micro_advanced_to_1.2"
 * Time pressure format (from evaluator.py):
 *   "Time pressure: stage=discover, micro_phase=1.1, duration=120.0 min, target=8.0 min, reduction=20.0"
 */
function parseEvalFromLogs(logs) {
  const result = {
    score: null,
    passed: null,
    action: null,
    timePressure: null,
    allEvals: [],
  };

  // Collect ALL eval lines (most recent last)
  const evalLines = logs.match(/stage eval: total=[\d.]+, passed=(True|False), action=\S+/g) || [];
  for (const line of evalLines) {
    const m = line.match(/total=([\d.]+), passed=(True|False), action=(\S+)/);
    if (m) {
      result.allEvals.push({
        score: parseFloat(m[1]),
        passed: m[2] === "True",
        action: m[3],
      });
    }
  }
  // Most recent eval
  if (result.allEvals.length > 0) {
    const last = result.allEvals[result.allEvals.length - 1];
    result.score = last.score;
    result.passed = last.passed;
    result.action = last.action;
  }

  // Time pressure
  const tpMatch = logs.match(/reduction=([\d.]+)/);
  if (tpMatch) result.timePressure = parseFloat(tpMatch[1]);

  return result;
}

// ── Browser session ──────────────────────────────────────────────────────────

/** Login in browser and navigate to lobby */
async function browserLoginAndLobby(browser, projectId, screenshotPrefix) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();

  log(`Browser: navigating to ${FRONTEND}/login`);
  await page.goto(`${FRONTEND}/login`, { waitUntil: "networkidle" });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${screenshotPrefix}-login.png`),
  });

  // Fill login form
  await page.fill('input[type="email"], input[name="email"], input[placeholder*="email" i]', EMAIL);
  await page.fill('input[type="password"], input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(lobby|projects|dashboard)/, { timeout: 15000 });
  log("Browser: logged in");

  // Navigate to the specific project lobby
  await page.goto(`${FRONTEND}/projects/${projectId}`, { waitUntil: "networkidle" });
  await sleep(2000);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${screenshotPrefix}-project-page.png`),
  });

  return { page, ctx };
}

/** Click join button with role preference */
async function joinProject(page, role, screenshotPrefix) {
  log(`Browser: attempting to join as ${role}`);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${screenshotPrefix}-before-join.png`),
  });

  let joined = false;

  if (role === "observer") {
    // Try "以觀察者身份進入" button
    const observerBtn = page.locator(
      'button:has-text("觀察者"), button:has-text("observer"), [data-testid*="observer"]'
    ).first();
    if (await observerBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await observerBtn.click();
      joined = true;
      log("Browser: clicked observer button");
    }
  } else {
    // Try first available "入座" / supervisor seat
    const seatBtn = page.locator(
      'button:has-text("入座"), button:has-text("加入"), [data-testid*="seat"]'
    ).first();
    if (await seatBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await seatBtn.click();
      joined = true;
      log("Browser: clicked first seat button");
    }
  }

  if (!joined) {
    // Fallback: look for any join/enter button
    const anyBtn = page.locator(
      'button:has-text("進入"), button:has-text("Enter"), button:has-text("Join")'
    ).first();
    if (await anyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await anyBtn.click();
      joined = true;
      log("Browser: clicked generic enter button");
    }
  }

  await sleep(3000);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${screenshotPrefix}-after-join.png`),
  });

  return joined;
}

// ── Monitoring loop ──────────────────────────────────────────────────────────

async function monitorProject(projectId, label, token, durationMs, intervalMs) {
  const timeline = [];
  const startTime = Date.now();
  let minute = 0;

  log(`\n=== Starting monitoring for ${label} (${projectId}) ===`);

  while (Date.now() - startTime < durationMs) {
    await sleep(intervalMs);
    minute++;
    const elapsed = Math.round((Date.now() - startTime) / 1000);

    try {
      const [stageData, messages, mpHistory, dockerLogs] = await Promise.all([
        getStage(projectId, token),
        getMessages(projectId, token, 200),
        getMicroPhaseHistory(projectId, token),
        getDockerLogs(projectId),
      ]);

      const senders = extractSenders(messages);
      const evalInfo = parseEvalFromLogs(dockerLogs);

      const entry = {
        minute,
        elapsed_s: elapsed,
        stage: stageData.current_stage || stageData.stage || "unknown",
        micro_phase: stageData.current_micro_phase || stageData.micro_phase || null,
        message_count: Array.isArray(messages) ? messages.length : 0,
        senders: senders.join(", "),
        eval_score: evalInfo.score,
        eval_passed: evalInfo.passed,
        eval_action: evalInfo.action,
        eval_all: evalInfo.allEvals,
        time_pressure_reduction: evalInfo.timePressure,
        micro_phase_history_count: Array.isArray(mpHistory) ? mpHistory.length : 0,
        raw_logs: dockerLogs.slice(0, 500),
      };

      timeline.push(entry);

      log(
        `[${label}] min=${minute} stage=${entry.stage} micro=${entry.micro_phase} ` +
        `msgs=${entry.message_count} eval_score=${entry.eval_score ?? "n/a"} ` +
        `passed=${entry.eval_passed ?? "n/a"} action=${entry.eval_action ?? "n/a"}`
      );

      if (dockerLogs.trim()) {
        log(`[${label}] Logs:\n${dockerLogs.slice(0, 600)}`);
      }
    } catch (err) {
      log(`[${label}] Monitor error at min=${minute}: ${err.message}`);
      timeline.push({ minute, elapsed_s: elapsed, error: err.message });
    }
  }

  return timeline;
}

// ── Deep log analysis ────────────────────────────────────────────────────────

async function captureDetailedLogs(projectId, label) {
  const short = projectId.replace(/-/g, "").slice(0, 8);
  const { exec } = require("child_process");

  const patterns = [
    // Evaluator decisions — actual format: "stage eval: total=XX.X, passed=T/F, action=XXX"
    `docker logs mindcrew-backend-1 --since=15m 2>&1 | grep -E "stage eval:|Time pressure:" | grep -v "^$" | tail -40`,
    // Stage / micro phase transitions
    `docker logs mindcrew-backend-1 --since=15m 2>&1 | grep -iE "micro phase advanced|stage advanced|advance.*stage|advance.*micro" | tail -20`,
    // Application errors
    `docker logs mindcrew-backend-1 --since=15m 2>&1 | grep -iE "ERROR|Exception|Traceback|hard.min" | grep -v SQL | tail -15`,
  ];

  const results = {};
  for (const cmd of patterns) {
    const key = cmd.includes("advance") ? "transitions" : cmd.includes("error") ? "errors" : "evals";
    results[key] = await new Promise((resolve) => {
      exec(cmd, { timeout: 12000 }, (_, stdout) => resolve(stdout || ""));
    });
  }
  return results;
}

// ── Report generation ────────────────────────────────────────────────────────

function buildReport(projectA, projectB, timelineA, timelineB, logsA, logsB) {
  const lines = [];

  lines.push("# TechLead Define-Phase Debug Report");
  lines.push(`Generated: ${new Date().toISOString()}`);
  lines.push("");
  lines.push("## Projects");
  lines.push(`- **Project A (All-AI Observer)**: ${projectA.id} — ${projectA.name}`);
  lines.push(`- **Project B (Human Supervisor)**: ${projectB.id} — ${projectB.name}`);
  lines.push("");

  // Side-by-side timeline table
  lines.push("## Monitoring Timeline (Side-by-Side)");
  lines.push("");
  lines.push("| Min | A Stage | A MicroPhase | A Msgs | A Score | A Passed | A Action | B Stage | B MicroPhase | B Msgs | B Score | B Passed | B Action |");
  lines.push("|-----|---------|--------------|--------|---------|----------|----------|---------|--------------|--------|---------|----------|----------|");

  const maxMin = Math.max(timelineA.length, timelineB.length);
  for (let i = 0; i < maxMin; i++) {
    const a = timelineA[i] || {};
    const b = timelineB[i] || {};
    lines.push(
      `| ${i + 1} ` +
      `| ${a.stage || "-"} | ${a.micro_phase || "-"} | ${a.message_count ?? "-"} | ` +
      `${a.eval_score ?? "-"} | ${a.eval_passed ?? "-"} | ${a.eval_action || "-"} ` +
      `| ${b.stage || "-"} | ${b.micro_phase || "-"} | ${b.message_count ?? "-"} | ` +
      `${b.eval_score ?? "-"} | ${b.eval_passed ?? "-"} | ${b.eval_action || "-"} |`
    );
  }

  lines.push("");
  lines.push("## Analysis Questions");
  lines.push("");

  // Question 1: Did evaluator score reach threshold in Define?
  const defineEntriesA = timelineA.filter((e) => e.stage === "define");
  const defineEntriesB = timelineB.filter((e) => e.stage === "define");
  const maxScoreA = Math.max(...defineEntriesA.map((e) => e.eval_score || 0));
  const maxScoreB = Math.max(...defineEntriesB.map((e) => e.eval_score || 0));

  lines.push("### 1. Did evaluator score reach threshold in Define?");
  lines.push(`- Project A max observed score in Define: **${maxScoreA || "not captured"}**`);
  lines.push(`- Project B max observed score in Define: **${maxScoreB || "not captured"}**`);
  lines.push(`  (All-AI threshold ≈ 50.0, Human threshold ≈ 60.0)`);
  lines.push("");

  // Question 2: Micro-phase advancement
  const mpSetA = new Set(timelineA.map((e) => e.micro_phase).filter(Boolean));
  const mpSetB = new Set(timelineB.map((e) => e.micro_phase).filter(Boolean));
  lines.push("### 2. Did micro_phase advance within Define (2.1 → 2.2 → 2.3)?");
  lines.push(`- Project A micro phases seen: **${[...mpSetA].join(" → ") || "none"}**`);
  lines.push(`- Project B micro phases seen: **${[...mpSetB].join(" → ") || "none"}**`);
  lines.push("");

  // Question 3: Stage progression
  const stageSetA = new Set(timelineA.map((e) => e.stage).filter(Boolean));
  const stageSetB = new Set(timelineB.map((e) => e.stage).filter(Boolean));
  lines.push("### 3. Stage progression");
  lines.push(`- Project A stages seen: **${[...stageSetA].join(" → ") || "none"}**`);
  lines.push(`- Project B stages seen: **${[...stageSetB].join(" → ") || "none"}**`);
  lines.push("");

  // Question 4: Time pressure
  const tpA = timelineA.map((e) => e.time_pressure_reduction).filter((v) => v !== null && v !== undefined);
  const tpB = timelineB.map((e) => e.time_pressure_reduction).filter((v) => v !== null && v !== undefined);
  lines.push("### 4. Was time pressure applied?");
  lines.push(`- Project A reductions seen: ${tpA.length > 0 ? tpA.join(", ") : "none captured"}`);
  lines.push(`- Project B reductions seen: ${tpB.length > 0 ? tpB.join(", ") : "none captured"}`);
  lines.push("");

  // Scoring breakdown analysis
  lines.push("## Define Stage Scoring Analysis");
  lines.push("");
  lines.push("The `score_define` function (evaluator_scoring.py) uses:");
  lines.push("- **35%** Grouping completion (ungrouped <= 20% of total notes)");
  lines.push("- **20%** Group count (>= 3 groups = 100)");
  lines.push("- **20%** Move/group ops (>= 2 groups = 100)");
  lines.push("- **15%** HMW discussion (keyword 'hmw', '我們如何', '怎麼樣才能' in chat)");
  lines.push("- **10%** Participant coverage");
  lines.push("");
  lines.push("The `_score_2_1` micro-phase function requires:");
  lines.push("- A group named '旅程*' to exist (hard minimum)");
  lines.push("- Notes with mixed colors: green, yellow, red");
  lines.push("- Red notes for pain points");
  lines.push("");

  // Backend logs
  lines.push("## Backend Logs — Project A (All-AI)");
  lines.push("```");
  lines.push((logsA.evals || "").slice(0, 800));
  lines.push("```");
  lines.push("");
  lines.push("### Stage Transitions — Project A");
  lines.push("```");
  lines.push((logsA.transitions || "").slice(0, 600));
  lines.push("```");
  lines.push("");
  lines.push("## Backend Logs — Project B (Human Supervisor)");
  lines.push("```");
  lines.push((logsB.evals || "").slice(0, 800));
  lines.push("```");
  lines.push("");
  lines.push("### Stage Transitions — Project B");
  lines.push("```");
  lines.push((logsB.transitions || "").slice(0, 600));
  lines.push("```");
  lines.push("");

  // Hypothesis
  lines.push("## Root Cause Hypotheses");
  lines.push("");
  lines.push("Based on code analysis of `micro_phase_scoring.py`:");
  lines.push("");
  lines.push("**Hypothesis A — `_score_2_1` hard minimum blocks Define 2.1:**");
  lines.push("  `_HARD_MINIMUMS['2.1'] = {'journey_groups': 1}` requires a group starting with '旅程'.");
  lines.push("  If AI agents do NOT create this group, score is capped at 30 and never passes threshold.");
  lines.push("");
  lines.push("**Hypothesis B — `_score_2_2` requires specific chat keywords:**");
  lines.push("  Needs '矛盾', '衝突', '張力', '但是', '卻' AND '為什麼', '根本原因', '深層' in chat.");
  lines.push("  Each is binary 0/100 — if AI chat doesn't use these exact words, score is 0 for 50% of the weight.");
  lines.push("");
  lines.push("**Hypothesis C — Macro boundary stall:**");
  lines.push("  At micro-phase 1.3 → 2.1, `is_macro_boundary()` is True.");
  lines.push("  In All-AI mode this calls `_advance_stage()`. In Human mode it calls `_propose_advance()`.");
  lines.push("  If this transition stalls, ALL of Define is blocked before it starts.");
  lines.push("");
  lines.push("**Hypothesis D — `_score_2_3` requires '★HMW' group:**");
  lines.push("  `(100.0 if star_hmw else 0.0) * 0.25` — 25% weight requires a '★...HMW' named group.");
  lines.push("  If AI never creates this specific group name, score cap = 75.");
  lines.push("");

  return lines.join("\n");
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  ensureDir(SCREENSHOT_DIR);
  log("Starting TechLead Define-Phase Debug Test");

  // 1. API login
  log("Step 1: API login");
  const token = await apiLogin();
  log("API token obtained");

  // 2. Create Project A (All-AI)
  log("Step 2: Creating Project A (All-AI)");
  const projectA = await createProject(
    token,
    "TechLead-AllAI-購物車",
    "high",
    PROJECT_DESC
  );
  log(`Project A created: ${projectA.id} — ${projectA.name}`);

  // 3. Create Project B (Human Supervisor)
  log("Step 3: Creating Project B (Human Supervisor)");
  const projectB = await createProject(
    token,
    "TechLead-HumanSup-購物車",
    "high",
    PROJECT_DESC
  );
  log(`Project B created: ${projectB.id} — ${projectB.name}`);

  // 4. Browser sessions
  log("Step 4: Opening browser sessions");
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });

  // Project A — join as observer
  const { page: pageA } = await browserLoginAndLobby(browser, projectA.id, "techlead-A");
  await joinProject(pageA, "observer", "techlead-A-observer");

  // Take initial screenshots
  await pageA.screenshot({
    path: path.join(SCREENSHOT_DIR, "techlead-A-workspace.png"),
  });

  // Project B — join as supervisor (human seat)
  const { page: pageB } = await browserLoginAndLobby(browser, projectB.id, "techlead-B");
  await joinProject(pageB, "supervisor", "techlead-B-supervisor");

  await pageB.screenshot({
    path: path.join(SCREENSHOT_DIR, "techlead-B-workspace.png"),
  });

  log("Browser sessions ready. Starting parallel 9-minute monitoring...");
  log(`Monitor start time: ${new Date().toISOString()}`);

  // 5. Run both monitoring loops in parallel
  const [timelineA, timelineB] = await Promise.all([
    monitorProject(projectA.id, "A-AllAI", token, MONITOR_DURATION_MS, POLL_INTERVAL_MS),
    monitorProject(projectB.id, "B-HumanSup", token, MONITOR_DURATION_MS, POLL_INTERVAL_MS),
  ]);

  log("Monitoring complete. Capturing final state...");

  // 6. Final screenshots
  await pageA.screenshot({
    path: path.join(SCREENSHOT_DIR, "techlead-A-final.png"),
  });
  await pageB.screenshot({
    path: path.join(SCREENSHOT_DIR, "techlead-B-final.png"),
  });

  // 7. Deep log capture
  log("Capturing detailed backend logs...");
  const [logsA, logsB] = await Promise.all([
    captureDetailedLogs(projectA.id, "A"),
    captureDetailedLogs(projectB.id, "B"),
  ]);

  // 8. Final stage check
  const [finalStageA, finalStageB] = await Promise.all([
    getStage(projectA.id, token),
    getStage(projectB.id, token),
  ]);

  log(`\nFINAL STATE:`);
  log(`Project A: stage=${finalStageA.current_stage || finalStageA.stage} micro=${finalStageA.current_micro_phase || finalStageA.micro_phase}`);
  log(`Project B: stage=${finalStageB.current_stage || finalStageB.stage} micro=${finalStageB.current_micro_phase || finalStageB.micro_phase}`);

  // 9. Get micro-phase histories
  const [mpHistA, mpHistB] = await Promise.all([
    getMicroPhaseHistory(projectA.id, token),
    getMicroPhaseHistory(projectB.id, token),
  ]);
  log(`Project A micro-phase history: ${JSON.stringify(mpHistA)}`);
  log(`Project B micro-phase history: ${JSON.stringify(mpHistB)}`);

  // 10. Generate report
  log("Generating report...");
  const report = buildReport(projectA, projectB, timelineA, timelineB, logsA, logsB);

  const reportPath = path.join(__dirname, "techlead-define-debug-report.md");
  const jsonPath   = path.join(__dirname, "techlead-define-debug-data.json");

  fs.writeFileSync(reportPath, report, "utf8");
  fs.writeFileSync(jsonPath, JSON.stringify({
    projectA: { id: projectA.id, name: projectA.name, finalStage: finalStageA, mpHistory: mpHistA },
    projectB: { id: projectB.id, name: projectB.name, finalStage: finalStageB, mpHistory: mpHistB },
    timelineA,
    timelineB,
    logsA,
    logsB,
  }, null, 2), "utf8");

  log(`Report saved to: ${reportPath}`);
  log(`JSON data saved to: ${jsonPath}`);

  await browser.close();

  // Print summary table to console
  console.log("\n" + "=".repeat(80));
  console.log("SUMMARY TABLE");
  console.log("=".repeat(80));
  console.log(
    "Min | A Stage       | A Micro | A Msgs | A Score | A Passed | B Stage       | B Micro | B Msgs | B Score | B Passed"
  );
  console.log("-".repeat(110));

  const maxMin = Math.max(timelineA.length, timelineB.length);
  for (let i = 0; i < maxMin; i++) {
    const a = timelineA[i] || {};
    const b = timelineB[i] || {};
    console.log(
      `${String(i + 1).padStart(3)} | ${String(a.stage || "-").padEnd(13)} | ${String(a.micro_phase || "-").padEnd(7)} | ` +
      `${String(a.message_count ?? "-").padStart(6)} | ${String(a.eval_score ?? "-").padStart(7)} | ` +
      `${String(a.eval_passed ?? "-").padStart(8)} | ` +
      `${String(b.stage || "-").padEnd(13)} | ${String(b.micro_phase || "-").padEnd(7)} | ` +
      `${String(b.message_count ?? "-").padStart(6)} | ${String(b.eval_score ?? "-").padStart(7)} | ` +
      `${String(b.eval_passed ?? "-").padStart(8)}`
    );
  }

  console.log("\nDone. See report at: " + reportPath);

  return { projectA, projectB, timelineA, timelineB };
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
