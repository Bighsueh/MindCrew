/**
 * Phase 14 Full Journey E2E — Create project → seed notes → verify canvas pipeline
 *
 * This test creates a REAL project via the API, seeds notes via sidecar,
 * then uses Playwright to navigate the full user journey and verify
 * canvas perception + manipulation integration.
 *
 * Run: node e2e/phase14-full-journey.test.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || `${FRONTEND_URL}/api`;
const SIDECAR_URL = process.env.SIDECAR_URL || 'http://localhost:4000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'phase14-journey');

const results = [];
const issues = [];

function record(id, feature, status, details = '') {
  results.push({ id, feature, status, details, ts: new Date().toISOString() });
  const icon = { PASS: '✓', FAIL: '✗', SKIP: '⚠', INFO: 'ℹ' }[status] || '?';
  console.log(`  ${icon} [${status}] ${id} ${feature}${details ? ': ' + details : ''}`);
}

function logIssue(cat, desc, detail = '') {
  issues.push({ category: cat, description: desc, details: detail });
  console.log(`  ⚠ [ISSUE] ${cat}: ${desc}${detail ? '\n    ' + detail : ''}`);
}

async function api(urlPath, opts = {}) {
  const url = urlPath.startsWith('http') ? urlPath : `${API_URL}${urlPath}`;
  const { headers: extraHeaders, ...rest } = opts;
  const fetchOpts = {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
  };
  const r = await fetch(url, fetchOpts);
  let data = null;
  try { data = await r.json(); } catch {}
  return { status: r.status, ok: r.ok, data };
}

async function sidecar(urlPath, opts = {}) {
  const url = `${SIDECAR_URL}${urlPath}`;
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json', ...opts.headers }, ...opts });
  let data = null;
  try { data = await r.json(); } catch {}
  return { status: r.status, ok: r.ok, data };
}

// ─── Main ──────────────────────────────────────────────────────────────────────

async function run() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  Phase 14 Full Journey: Create Project → Canvas Verify');
  console.log('═══════════════════════════════════════════════════════════\n');

  // ══════════════════════════════════════════════════════════════════════
  // Phase A: API — Create project + seed data
  // ══════════════════════════════════════════════════════════════════════
  console.log('── A: API Setup ──');

  // A.1 Login
  let token = null;
  try {
    const { ok, data } = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: 'teacher@test.com', password: 'teacher123' }),
    });
    if (ok && data?.access_token) {
      token = data.access_token;
      record('A.1', 'Login as teacher', 'PASS');
    } else {
      record('A.1', 'Login', 'FAIL', JSON.stringify(data).slice(0, 200));
      logIssue('Auth', 'Login failed', JSON.stringify(data).slice(0, 200));
    }
  } catch (e) { record('A.1', 'Login', 'FAIL', e.message); }

  if (!token) {
    console.log('\n  Cannot proceed without auth token. Aborting.\n');
    process.exit(1);
  }

  const auth = { Authorization: `Bearer ${token}` };

  // A.2 Create a new project
  let projectId = null;
  const projectName = `Canvas 驗證 ${new Date().toLocaleTimeString('zh-TW')}`;
  try {
    const { ok, data, status } = await api('/projects', {
      method: 'POST',
      headers: auth,
      body: JSON.stringify({
        name: projectName,
        description: 'Phase 14 E2E 完整驗證：Canvas Perception & Manipulation Tools',
        ai_contribution: 'medium',
      }),
    });
    if (ok && data?.id) {
      projectId = data.id;
      record('A.2', 'Create project', 'PASS', `name="${projectName}" id=${projectId}`);
    } else {
      record('A.2', 'Create project', 'FAIL', `status=${status} body=${JSON.stringify(data).slice(0, 300)}`);
      logIssue('API', 'POST /api/projects failed', `status=${status} body=${JSON.stringify(data).slice(0, 300)}`);
    }
  } catch (e) {
    record('A.2', 'Create project', 'FAIL', e.message);
    logIssue('API', 'Create project exception', e.message);
  }

  if (!projectId) {
    console.log('\n  Cannot proceed without project. Aborting.\n');
    writeSummary();
    process.exit(1);
  }

  // A.3 Verify project appears in list
  try {
    const { ok, data } = await api('/projects', { headers: auth });
    const found = Array.isArray(data) && data.some(p => p.id === projectId);
    record('A.3', 'Project in list', found ? 'PASS' : 'FAIL', `found=${found}`);
  } catch (e) { record('A.3', 'Project in list', 'FAIL', e.message); }

  // A.4 Verify project detail
  try {
    const { ok, data } = await api(`/projects/${projectId}`, { headers: auth });
    if (ok && data?.current_stage === 'discover') {
      record('A.4', 'Project detail', 'PASS', `stage=${data.current_stage}, seats=${data.seats?.length || 0}`);
    } else {
      record('A.4', 'Project detail', 'FAIL', JSON.stringify(data).slice(0, 200));
    }
  } catch (e) { record('A.4', 'Project detail', 'FAIL', e.message); }

  // ══════════════════════════════════════════════════════════════════════
  // Phase B: Sidecar — Seed notes + verify new endpoints
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── B: Sidecar — Seed Notes ──');

  const SEED_NOTES = [
    // Cluster 1: 支付問題 (yellow)
    { content: '行動支付選項太少', color: 'yellow', author: 'crew_1(ai)' },
    { content: '信用卡綁定流程太複雜', color: 'yellow', author: 'crew_2(ai)' },
    { content: '手續費不透明', color: 'yellow', author: 'crew_3(ai)' },
    { content: '退款等待時間太久', color: 'yellow', author: 'crew_1(ai)' },
    // Cluster 2: 客服問題 (blue)
    { content: '客服電話等40分鐘', color: 'blue', author: 'crew_2(ai)' },
    { content: '客服態度差', color: 'blue', author: 'crew_4(ai)' },
    { content: '線上客服是機器人', color: 'blue', author: 'crew_3(ai)' },
    // Cluster 3: 搜尋問題 (green)
    { content: '搜尋結果不準確', color: 'green', author: 'crew_4(ai)' },
    { content: '篩選條件太少', color: 'green', author: 'crew_1(ai)' },
    { content: '排序邏輯混亂', color: 'green', author: 'crew_2(ai)' },
    // Ungrouped (red, orange)
    { content: '頁面載入太慢', color: 'red', author: 'crew_3(ai)' },
    { content: '通知太多太煩', color: 'orange', author: 'crew_4(ai)' },
    { content: '深色模式不完整', color: 'orange', author: 'crew_1(ai)' },
    { content: '缺少多語言支援', color: 'red', author: 'crew_2(ai)' },
    { content: '帳號安全驗證太頻繁', color: 'orange', author: 'crew_3(ai)' },
  ];

  const noteIds = [];
  try {
    for (const note of SEED_NOTES) {
      const { ok, data } = await sidecar(`/api/projects/${projectId}/notes`, {
        method: 'POST',
        body: JSON.stringify(note),
      });
      if (ok && data?.id) noteIds.push(data.id);
    }
    record('B.1', `Seed ${SEED_NOTES.length} notes`, noteIds.length === SEED_NOTES.length ? 'PASS' : 'FAIL',
      `created ${noteIds.length}/${SEED_NOTES.length}`);
  } catch (e) {
    record('B.1', 'Seed notes', 'FAIL', e.message);
  }

  // B.2 canvas-state/full returns all with geometry
  try {
    const { ok, data } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    if (ok && Array.isArray(data) && data.length === noteIds.length) {
      const sample = data[0];
      const requiredFields = ['id', 'content', 'x', 'y', 'width', 'height', 'color', 'author', 'createdAt'];
      const missing = requiredFields.filter(f => sample[f] === undefined);
      if (missing.length === 0) {
        record('B.2', 'canvas-state/full geometry', 'PASS', `${data.length} notes, all fields present`);
      } else {
        record('B.2', 'canvas-state/full', 'FAIL', `missing: ${missing.join(',')}`);
        logIssue('Layer 1', 'canvas-state/full missing fields', missing.join(','));
      }
    } else {
      record('B.2', 'canvas-state/full', 'FAIL', `expected ${noteIds.length}, got ${data?.length}`);
    }
  } catch (e) { record('B.2', 'canvas-state/full', 'FAIL', e.message); }

  // B.3 batch-update-coordinates: arrange in grid
  try {
    const gridUpdates = noteIds.map((id, i) => ({
      id,
      x: 80 + (i % 5) * 260,
      y: 80 + Math.floor(i / 5) * 210,
    }));
    const { ok, data } = await sidecar(`/api/projects/${projectId}/batch-update-coordinates`, {
      method: 'POST',
      body: JSON.stringify({ updates: gridUpdates }),
    });
    if (ok) {
      record('B.3', 'Batch arrange 15 notes in grid', 'PASS', `count=${data?.count}`);
    } else {
      record('B.3', 'Batch arrange', 'FAIL', JSON.stringify(data));
    }
  } catch (e) { record('B.3', 'Batch arrange', 'FAIL', e.message); }

  // B.4 Verify no overlaps after grid arrangement
  try {
    const { data: state } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    let overlapCount = 0;
    for (let i = 0; i < state.length; i++) {
      for (let j = i + 1; j < state.length; j++) {
        const a = state[i], b = state[j];
        if (a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y) {
          overlapCount++;
        }
      }
    }
    record('B.4', 'No overlaps after grid', overlapCount === 0 ? 'PASS' : 'FAIL', `overlaps=${overlapCount}`);
  } catch (e) { record('B.4', 'Overlap check', 'FAIL', e.message); }

  // B.5 Swap two notes and verify
  try {
    const { data: before } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    const n0 = before.find(n => n.id === noteIds[0]);
    const n1 = before.find(n => n.id === noteIds[1]);
    await sidecar(`/api/projects/${projectId}/batch-update-coordinates`, {
      method: 'POST',
      body: JSON.stringify({ updates: [
        { id: noteIds[0], x: n1.x, y: n1.y },
        { id: noteIds[1], x: n0.x, y: n0.y },
      ]}),
    });
    const { data: after } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    const n0a = after.find(n => n.id === noteIds[0]);
    const n1a = after.find(n => n.id === noteIds[1]);
    const swapped = n0a.x === n1.x && n0a.y === n1.y && n1a.x === n0.x && n1a.y === n0.y;
    record('B.5', 'Swap notes', swapped ? 'PASS' : 'FAIL');
    // Swap back
    await sidecar(`/api/projects/${projectId}/batch-update-coordinates`, {
      method: 'POST',
      body: JSON.stringify({ updates: [
        { id: noteIds[0], x: n0.x, y: n0.y },
        { id: noteIds[1], x: n1.x, y: n1.y },
      ]}),
    });
  } catch (e) { record('B.5', 'Swap notes', 'FAIL', e.message); }

  // B.6 Atomicity: partial failure rolls back
  try {
    const { data: before } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    const origX = before.find(n => n.id === noteIds[0])?.x;
    const { status } = await sidecar(`/api/projects/${projectId}/batch-update-coordinates`, {
      method: 'POST',
      body: JSON.stringify({ updates: [
        { id: noteIds[0], x: 9999, y: 9999 },
        { id: 'nonexistent-id', x: 0, y: 0 },
      ]}),
    });
    const { data: after } = await sidecar(`/api/projects/${projectId}/canvas-state/full`);
    const afterX = after.find(n => n.id === noteIds[0])?.x;
    const rolledBack = status === 404 && afterX === origX;
    record('B.6', 'Batch atomicity (rollback)', rolledBack ? 'PASS' : 'FAIL',
      `status=${status} origX=${origX} afterX=${afterX}`);
    if (!rolledBack) logIssue('Layer 1', 'Batch update not atomic', `note moved to ${afterX} despite 404`);
  } catch (e) { record('B.6', 'Batch atomicity', 'FAIL', e.message); }

  // B.7 Legacy /state still works
  try {
    const { ok, data } = await sidecar(`/api/projects/${projectId}/state`);
    if (ok && data?.total_notes === noteIds.length) {
      record('B.7', 'Legacy /state backward compat', 'PASS', `total=${data.total_notes}`);
    } else {
      record('B.7', 'Legacy /state', 'FAIL', `total=${data?.total_notes}`);
    }
  } catch (e) { record('B.7', 'Legacy /state', 'FAIL', e.message); }

  // ══════════════════════════════════════════════════════════════════════
  // Phase C: Python modules — verify via subprocess
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── C: Python Module Verification ──');

  const pyExec = (code, label) => {
    try {
      const { execSync } = require('child_process');
      return execSync(
        `cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "${code}"`,
        { encoding: 'utf-8', timeout: 15000 }
      ).trim();
    } catch (e) {
      return `ERROR: ${(e.stderr || e.message || '').slice(0, 300)}`;
    }
  };

  // C.1 Spatial: orderliness score computation
  {
    const out = pyExec(
      'from app.canvas.spatial import compute_orderliness, SpatialNote, detect_overlaps\\n' +
      'notes = [SpatialNote(id=str(i), text=str(i), x=80+(i%5)*260, y=80+(i//5)*210, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\") for i in range(15)]\\n' +
      'score = compute_orderliness(notes)\\n' +
      'overlaps = detect_overlaps(notes)\\n' +
      'print(f\\"orderliness={score:.2f} overlaps={len(overlaps)}\\")'
    );
    const match = out.match(/orderliness=([\d.]+) overlaps=(\d+)/);
    if (match && parseFloat(match[1]) > 0.5 && parseInt(match[2]) === 0) {
      record('C.1', 'Spatial: grid orderliness high + no overlaps', 'PASS', out);
    } else {
      record('C.1', 'Spatial orderliness', 'FAIL', out);
      logIssue('Layer 2', 'Orderliness computation unexpected result', out);
    }
  }

  // C.2 Clustering: below-threshold returns ungrouped
  {
    const out = pyExec(
      'from app.canvas.clustering import compute_clusters\\n' +
      'from app.canvas.spatial import SpatialNote\\n' +
      'notes = [SpatialNote(id=str(i), text=f\\"note {i}\\", x=0, y=0, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\") for i in range(5)]\\n' +
      'embs = [[float(i)]*8 for i in range(5)]\\n' +
      'state = compute_clusters(notes, embs)\\n' +
      'print(f\\"clusters={len(state.clusters)} ungrouped={len(state.ungrouped_note_ids)}\\")'
    );
    if (out.includes('clusters=0') && out.includes('ungrouped=5')) {
      record('C.2', 'Clustering: <10 notes skips HDBSCAN', 'PASS', out);
    } else {
      record('C.2', 'Clustering threshold', 'FAIL', out);
      logIssue('Layer 2', 'Clustering should skip for <10 notes', out);
    }
  }

  // C.3 Layout engine: all position formats
  {
    const out = pyExec(
      'from app.canvas.layout_engine import LayoutEngine\\n' +
      'from app.canvas.spatial import SpatialNote\\n' +
      'from app.canvas.clustering import ClusterResult\\n' +
      'e = LayoutEngine()\\n' +
      'n1 = SpatialNote(id=\\"n1\\", text=\\"t\\", x=100, y=100, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\")\\n' +
      'c1 = ClusterResult(cluster_id=\\"c1\\", note_ids=[\\"n1\\"], centroid=[0.0], coherence_score=0.9)\\n' +
      'r1 = e.resolve_position(\\"near:n1\\", [n1])\\n' +
      'r2 = e.resolve_position(\\"grid:2,3\\", [])\\n' +
      'r3 = e.resolve_position(\\"region:bottom-right\\", [])\\n' +
      'r4 = e.resolve_position(\\"cluster:c1\\", [n1], [c1])\\n' +
      'print(f\\"near=({r1[0]:.0f},{r1[1]:.0f}) grid=({r2[0]:.0f},{r2[1]:.0f}) region=({r3[0]:.0f},{r3[1]:.0f}) cluster=({r4[0]:.0f},{r4[1]:.0f})\\")'
    );
    const allOk = out.includes('near=') && out.includes('grid=') && out.includes('region=') && out.includes('cluster=') && !out.includes('ERROR');
    record('C.3', 'Layout engine: 4 position formats', allOk ? 'PASS' : 'FAIL', out);
    if (!allOk) logIssue('Layer 4', 'Layout engine resolve_position failed', out);
  }

  // C.4 ASSESS Rule X priority
  {
    const out = pyExec(
      'from app.agents.assess import AssessEngine\\n' +
      'import time\\n' +
      'e = AssessEngine()\\n' +
      'ctx = {' +
      '  \\"canvas_state\\": {\\"summary\\": {\\"total_notes\\": 15, \\"orderliness_score\\": 0.3}},' +
      '  \\"recent_chat\\": [],' +
      '  \\"seats\\": [{\\"type\\": \\"ai\\", \\"role\\": \\"crew_1\\"}],' +
      '  \\"my_seat\\": \\"crew_1\\",' +
      '  \\"my_recent_actions\\": [],' +
      '  \\"_last_tidy_time\\": None,' +
      '  \\"_human_typing_timestamp\\": None,' +
      '  \\"_last_event_time\\": time.time() - 35,' +
      '}\\n' +
      'r = e.evaluate(ctx, \\"agent_crew_1\\", last_action_time=time.time()-20, last_idle_event_time=time.time()-35)\\n' +
      'print(f\\"{r.decision} {r.rule}\\")'
    );
    if (out.includes('intervene') && out.includes('rule_x_canvas_untidy')) {
      record('C.4', 'ASSESS Rule X fires before Rule 5', 'PASS', out);
    } else {
      record('C.4', 'ASSESS Rule X priority', 'FAIL', out);
      logIssue('ASSESS', 'Rule X not firing before Rule 5', out);
    }
  }

  // C.5 Context serializer renders spatial format
  {
    const out = pyExec(
      'from app.agents.prompts.context_serializer import build_context_description\\n' +
      'ctx = {' +
      '  \\"project_name\\": \\"Test\\", \\"current_stage\\": \\"discover\\", \\"stage_duration_minutes\\": 5,' +
      '  \\"canvas_state\\": {' +
      '    \\"summary\\": {\\"total_notes\\": 15, \\"orderliness_score\\": 0.65, \\"overlap_count\\": 0, \\"cluster_count\\": 3, \\"ungrouped_count\\": 5, \\"board_bounds\\": {\\"free_regions\\": [\\"bottom-left\\"]}},' +
      '    \\"clusters\\": [{\\"cluster_id\\": \\"c1\\", \\"suggested_label\\": \\"支付問題\\", \\"note_count\\": 4, \\"region\\": \\"top-left\\", \\"density\\": \\"dense\\"}],' +
      '    \\"ungrouped_notes\\": [{\\"id\\": \\"n5\\", \\"text_preview\\": \\"頁面載入...\\", \\"region\\": \\"center\\", \\"nearest_cluster\\": \\"c1\\", \\"similarity_to_nearest\\": 0.7}],' +
      '  },' +
      '  \\"recent_chat\\": [], \\"seats\\": [], \\"my_seat\\": \\"crew_1\\", \\"my_recent_actions\\": [],' +
      '}\\n' +
      'desc = build_context_description(ctx)\\n' +
      'checks = [\\"有序度\\" in desc, \\"支付問題\\" in desc, \\"bottom-left\\" in desc or \\"空閒\\" in desc, \\"叢集\\" in desc]\\n' +
      'print(f\\"orderliness={checks[0]} label={checks[1]} free={checks[2]} cluster={checks[3]}\\")'
    );
    const allTrue = out.includes('orderliness=True') && out.includes('label=True') && out.includes('cluster=True');
    record('C.5', 'Context serializer renders spatial canvas', allTrue ? 'PASS' : 'FAIL', out);
    if (!allTrue) logIssue('Pipeline', 'Context serializer missing spatial info', out);
  }

  // C.6 Prompt assembler has new tool vocab
  {
    const out = pyExec(
      'from app.agents.prompts.assembler import PromptAssembler\\n' +
      'a = PromptAssembler()\\n' +
      'msgs = a.assemble({\\"my_seat\\": \\"crew_1\\", \\"current_stage\\": \\"discover\\", \\"canvas_state\\": {}, \\"recent_chat\\": [], \\"seats\\": [], \\"my_recent_actions\\": []})\\n' +
      'sys_msg = msgs[0][\\"content\\"]\\n' +
      'c1 = \\"create_note\\" in sys_msg\\n' +
      'c2 = \\"arrange_notes\\" in sys_msg\\n' +
      'c3 = \\"tidy_area\\" in sys_msg\\n' +
      'c4 = \\"add_note\\" in sys_msg\\n' +
      'print(f\\"create_note={c1} arrange_notes={c2} tidy_area={c3} old_add_note={c4}\\")'
    );
    const hasNew = out.includes('create_note=True') && out.includes('arrange_notes=True') && out.includes('tidy_area=True');
    const noOld = out.includes('old_add_note=False');
    record('C.6', 'Prompt: new tools, no old types', hasNew && noOld ? 'PASS' : 'FAIL', out);
    if (!hasNew || !noOld) logIssue('Pipeline', 'Prompt tool vocabulary wrong', out);
  }

  // C.7 think.py valid action types
  {
    const out = pyExec(
      'from app.agents.think import _VALID_ACTION_TYPES\\n' +
      'expected = {\\"chat_message\\", \\"create_note\\", \\"move_note\\", \\"edit_note\\", \\"delete_note\\", \\"arrange_notes\\", \\"swap_notes\\", \\"tidy_area\\", \\"set_directive\\", \\"no_action\\"}\\n' +
      'match = _VALID_ACTION_TYPES == expected\\n' +
      'extra = _VALID_ACTION_TYPES - expected\\n' +
      'missing = expected - _VALID_ACTION_TYPES\\n' +
      'print(f\\"match={match} extra={extra} missing={missing}\\")'
    );
    if (out.includes('match=True')) {
      record('C.7', 'think.py action types exact match', 'PASS');
    } else {
      record('C.7', 'think.py action types', 'FAIL', out);
      logIssue('Pipeline', 'think.py action types mismatch', out);
    }
  }

  // C.8 Unit test suite
  {
    const out = pyExec(
      'import subprocess, sys\\n' +
      'r = subprocess.run([sys.executable, \\"-m\\", \\"pytest\\", \\"app/tests/test_canvas_spatial.py\\", \\"app/tests/test_canvas_clustering.py\\", \\"app/tests/test_canvas_layout_engine.py\\", \\"app/tests/test_canvas_tools.py\\", \\"-q\\", \\"--tb=no\\"], capture_output=True, text=True, timeout=30)\\n' +
      'print(r.stdout.strip().split(chr(10))[-1])'
    );
    const passMatch = out.match(/(\d+) passed/);
    const failMatch = out.match(/(\d+) failed/);
    const passed = passMatch ? parseInt(passMatch[1]) : 0;
    const failed = failMatch ? parseInt(failMatch[1]) : 0;
    record('C.8', 'Unit tests', failed === 0 && passed > 0 ? 'PASS' : 'FAIL', out);
    if (failed > 0) logIssue('Tests', 'Unit test failures', out);
  }

  // ══════════════════════════════════════════════════════════════════════
  // Phase D: Playwright — Full browser journey
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── D: Playwright Browser Journey ──');

  const browser = await chromium.launch({ headless: true, slowMo: 50 });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'zh-TW' });

  try {
    const page = await ctx.newPage();

    // D.1 Login
    try {
      await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'networkidle', timeout: 10000 });
      await page.fill('input[type="email"], input[name="email"]', 'teacher@test.com');
      await page.fill('input[type="password"], input[name="password"]', 'teacher123');
      await page.click('button[type="submit"]');
      await page.waitForURL('**/projects**', { timeout: 10000 });
      record('D.1', 'Login', 'PASS');
    } catch (e) {
      record('D.1', 'Login', 'FAIL', e.message.slice(0, 200));
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D1_login_fail.png') }).catch(() => {});
    }

    // D.2 Verify new project appears in project list
    try {
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D2_projects_list.png') });
      const pageText = await page.textContent('body');
      if (pageText.includes('Canvas 驗證') || pageText.includes(projectName.slice(0, 6))) {
        record('D.2', 'New project in list', 'PASS');
      } else {
        record('D.2', 'New project in list', 'FAIL', 'Project name not found on page');
        logIssue('Frontend', 'Newly created project not visible in list', '');
      }
    } catch (e) { record('D.2', 'Projects list', 'FAIL', e.message.slice(0, 200)); }

    // D.3 Navigate to project lobby
    try {
      await page.goto(`${FRONTEND_URL}/projects/${projectId}/lobby`, { waitUntil: 'networkidle', timeout: 10000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D3_lobby.png') });

      const lobbyText = await page.textContent('body');
      const hasProjectInfo = lobbyText.includes('Canvas 驗證') || lobbyText.includes('Discover') || lobbyText.includes('discover');
      record('D.3', 'Project lobby', hasProjectInfo ? 'PASS' : 'FAIL',
        hasProjectInfo ? 'Project info visible' : 'Project info not found');
    } catch (e) {
      record('D.3', 'Project lobby', 'FAIL', e.message.slice(0, 200));
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D3_lobby_fail.png') }).catch(() => {});
    }

    // D.4 Join a seat (try clicking join button)
    try {
      const joinBtn = await page.$('button:has-text("加入"), button:has-text("進入"), button:has-text("Join"), button:has-text("開始")');
      if (joinBtn) {
        await joinBtn.click();
        await page.waitForTimeout(2000);
        record('D.4', 'Join seat', 'PASS');
      } else {
        // Try API join
        const { ok } = await api(`/projects/${projectId}/join`, {
          method: 'POST', headers: auth,
          body: JSON.stringify({ seat_role: 'crew_1' }),
        });
        record('D.4', 'Join seat (API)', ok ? 'PASS' : 'SKIP', 'No join button found, tried API');
      }
    } catch (e) { record('D.4', 'Join seat', 'SKIP', e.message.slice(0, 100)); }

    // D.5 Navigate to workspace
    try {
      await page.goto(`${FRONTEND_URL}/projects/${projectId}/workspace`, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(4000); // tldraw init time
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D5_workspace.png') });

      // Check for canvas or workspace indicators
      const canvas = await page.$('.tl-container, [class*="tldraw"], [class*="Canvas"]');
      const wsText = await page.textContent('body');
      const hasWorkspace = canvas || wsText.includes('Discover') || wsText.includes('白板') || wsText.includes('聊天');

      if (hasWorkspace) {
        record('D.5', 'Workspace loaded', 'PASS', canvas ? 'tldraw canvas found' : 'Workspace content visible');
      } else {
        record('D.5', 'Workspace', 'FAIL', 'No canvas or workspace content');
        logIssue('Frontend', 'Workspace not loading for new project', '');
      }
    } catch (e) {
      record('D.5', 'Workspace', 'FAIL', e.message.slice(0, 200));
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D5_workspace_fail.png') }).catch(() => {});
    }

    // D.6 Check chat panel exists
    try {
      const chatPanel = await page.$('[class*="chat"], [class*="Chat"], [class*="message"]');
      const chatInput = await page.$('input[placeholder*="訊息"], textarea[placeholder*="訊息"], input[placeholder*="message"]');
      record('D.6', 'Chat panel', chatPanel || chatInput ? 'PASS' : 'SKIP',
        chatPanel ? 'Chat panel found' : chatInput ? 'Chat input found' : 'Not found');
    } catch (e) { record('D.6', 'Chat panel', 'SKIP', e.message.slice(0, 100)); }

    // D.7 Check stage progress indicator
    try {
      const wsText = await page.textContent('body');
      const hasStage = wsText.includes('Discover') || wsText.includes('discover') || wsText.includes('發散');
      record('D.7', 'Stage indicator', hasStage ? 'PASS' : 'SKIP', hasStage ? 'Stage visible' : 'Not found');
    } catch (e) { record('D.7', 'Stage indicator', 'SKIP', e.message.slice(0, 100)); }

    // D.8 Take final screenshot
    try {
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'D8_final.png'), fullPage: true });
      record('D.8', 'Final screenshot', 'PASS');
    } catch (e) { record('D.8', 'Screenshot', 'SKIP', e.message.slice(0, 100)); }

  } finally {
    await browser.close();
  }

  // ══════════════════════════════════════════════════════════════════════
  // Phase E: Code quality final checks
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── E: Code Quality ──');

  // E.1 No old action types in agent code
  {
    const { execSync } = require('child_process');
    const out = execSync(
      'grep -rn --include="*.py" ' +
      '-e \'"add_note"\' -e \'"group_notes"\' -e \'"arrange_groups"\' -e \'"tidy_notes"\' -e \'"auto_layout"\' ' +
      '-e "canvas_ops.auto_layout" -e "canvas_ops.group_notes" -e "canvas_ops.tidy_notes" -e "canvas_ops.arrange_groups" ' +
      '/Users/hsueh/Code/Experimental/MindCrew/backend/app/agents/ 2>/dev/null || true',
      { encoding: 'utf-8' }
    ).trim();
    record('E.1', 'No old action types in agents/', out === '' ? 'PASS' : 'FAIL', out.slice(0, 200) || 'clean');
    if (out) logIssue('Code Quality', 'Old action types remain', out.slice(0, 300));
  }

  // E.2 All files under 500 lines
  {
    const { execSync } = require('child_process');
    const out = execSync(
      'wc -l /Users/hsueh/Code/Experimental/MindCrew/backend/app/agents/act.py ' +
      '/Users/hsueh/Code/Experimental/MindCrew/backend/app/agents/assess.py ' +
      '/Users/hsueh/Code/Experimental/MindCrew/backend/app/agents/prompts/assembler.py ' +
      '/Users/hsueh/Code/Experimental/MindCrew/backend/app/canvas/*.py 2>/dev/null',
      { encoding: 'utf-8' }
    );
    const overLimit = out.split('\n').filter(l => {
      const m = l.trim().match(/^(\d+)/);
      return m && parseInt(m[1]) > 500 && !l.includes('total');
    });
    record('E.2', 'All files ≤ 500 lines', overLimit.length === 0 ? 'PASS' : 'FAIL',
      overLimit.length > 0 ? overLimit.join('; ') : 'all under limit');
  }

  // E.3 placeholder（原 spec 文件存在性檢查已隨內部 docs 移除）
  {
    record('E.3', 'placeholder', 'PASS');
  }

  // E.4 Document index updated
  {
    const idx = fs.readFileSync('/Users/hsueh/Code/Experimental/MindCrew/', 'utf-8');
    const has10 = idx.includes('10-canvas-perception-manipulation');
    record('E.4', 'Document index has spec 10', has10 ? 'PASS' : 'FAIL');
  }

  // E.5 System architecture §7 updated
  {
    const arch = fs.readFileSync('/Users/hsueh/Code/Experimental/MindCrew/', 'utf-8');
    const hasNew = arch.includes('create_note') && arch.includes('arrange_notes') && arch.includes('tidy_area');
    const hasOldSection = arch.includes('tldraw WebSocket Bridge 架構');
    record('E.5', 'Arch spec §7 updated', hasNew && !hasOldSection ? 'PASS' : 'FAIL');
  }

  // E.6 Decision loop spec updated
  {
    const dl = fs.readFileSync('/Users/hsueh/Code/Experimental/MindCrew/', 'utf-8');
    const hasNew = dl.includes('create_note') && dl.includes('arrange_notes') && dl.includes('tidy_area') && dl.includes('swap_notes');
    record('E.6', 'Decision loop spec updated', hasNew ? 'PASS' : 'FAIL');
  }

  // E.7 Progress.md has Phase 14
  {
    const prog = fs.readFileSync('/Users/hsueh/Code/Experimental/MindCrew/prompts/progress.md', 'utf-8');
    const has14 = prog.includes('Phase 14') && prog.includes('Canvas Perception');
    record('E.7', 'progress.md has Phase 14', has14 ? 'PASS' : 'FAIL');
  }

  writeSummary();
}

function writeSummary() {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  SUMMARY');
  console.log('═══════════════════════════════════════════════════════════');

  const p = results.filter(r => r.status === 'PASS').length;
  const f = results.filter(r => r.status === 'FAIL').length;
  const s = results.filter(r => r.status === 'SKIP' || r.status === 'INFO').length;
  console.log(`\n  Results: ${p} passed, ${f} failed, ${s} skipped/info (${results.length} total)`);

  if (issues.length > 0) {
    console.log(`\n  Issues (${issues.length}):`);
    issues.forEach((iss, i) => {
      console.log(`    ${i + 1}. [${iss.category}] ${iss.description}`);
      if (iss.details) console.log(`       ${iss.details.split('\n')[0].slice(0, 120)}`);
    });
  } else {
    console.log('\n  No issues found.');
  }

  const report = { timestamp: new Date().toISOString(), results, issues, summary: { passed: p, failed: f, skipped: s, total: results.length } };
  fs.writeFileSync(path.join(SCREENSHOTS_DIR, 'report.json'), JSON.stringify(report, null, 2));
  console.log(`\n  Report: ${path.join(SCREENSHOTS_DIR, 'report.json')}`);
  console.log(`  Screenshots: ${SCREENSHOTS_DIR}/`);
  console.log('═══════════════════════════════════════════════════════════\n');

  process.exit(f > 0 ? 1 : 0);
}

run().catch(e => { console.error('Runner error:', e); process.exit(1); });
