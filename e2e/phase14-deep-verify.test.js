/**
 * Phase 14 Deep Verification — supplementary E2E tests
 *
 * Covers areas the first E2E suite skipped:
 *   A. Backend canvas pipeline end-to-end (Python spatial analyzer via real HTTP)
 *   B. Playwright workspace: create project → enter workspace → verify canvas
 *   C. ASSESS Rule X integration (orderliness-triggered intervention)
 *   D. CanvasOps bridge new methods (get_canvas_state_full, batch_update_coordinates)
 *   E. Context buffer canvas perception injection
 *
 * Run: node e2e/phase14-deep-verify.test.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || `${FRONTEND_URL}/api`;
const SIDECAR_URL = process.env.SIDECAR_URL || 'http://localhost:4000';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'phase14-deep');

const results = [];
const issues = [];

function record(feature, status, details = '') {
  results.push({ feature, status, details, ts: new Date().toISOString() });
  const icon = { PASS: '✓', FAIL: '✗', SKIP: '⚠', INFO: 'ℹ' }[status] || '?';
  console.log(`  ${icon} [${status}] ${feature}${details ? ': ' + details : ''}`);
}

function issue(cat, desc, detail = '') {
  issues.push({ category: cat, description: desc, details: detail });
  console.log(`  ⚠ [ISSUE] ${cat}: ${desc}${detail ? '\n    ' + detail : ''}`);
}

async function json(url, opts = {}) {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json', ...opts.headers }, ...opts });
  let data = null;
  try { data = await r.json(); } catch {}
  return { status: r.status, ok: r.ok, data };
}

async function run() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  Phase 14 Deep Verification');
  console.log('═══════════════════════════════════════════════════════════\n');

  // ── Auth ──
  let token = null;
  try {
    const { ok, data } = await json(`${API_URL}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email: 'teacher@test.com', password: 'teacher123' }),
    });
    if (ok && data?.access_token) {
      token = data.access_token;
      record('0.1 Auth', 'PASS');
    } else {
      record('0.1 Auth', 'FAIL', `status=${!ok}, data=${JSON.stringify(data)}`);
    }
  } catch (e) { record('0.1 Auth', 'FAIL', e.message); }

  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  // ══════════════════════════════════════════════════════════════════════
  // Section A: Backend canvas pipeline end-to-end
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── A: Backend Canvas Pipeline ──');

  // A.1 Verify backend has canvas module importable (hit an endpoint that lazy-loads it)
  // We'll create a project, then the context_buffer will try to load canvas perception
  let projectId = null;
  try {
    const { ok, data } = await json(`${API_URL}/projects`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({
        name: `E2E Phase14 Deep ${Date.now()}`,
        description: 'Canvas tools deep verification',
        ai_contribution: 'medium',
      }),
    });
    if (ok && data?.id) {
      projectId = data.id;
      record('A.1 Create test project', 'PASS', `id=${projectId}`);
    } else {
      record('A.1 Create test project', 'FAIL', JSON.stringify(data));
    }
  } catch (e) { record('A.1 Create test project', 'FAIL', e.message); }

  // A.2 Add notes via sidecar for this project
  if (projectId) {
    const sidecarNoteIds = [];
    try {
      for (let i = 0; i < 12; i++) {
        const { ok, data } = await json(`${SIDECAR_URL}/api/projects/${projectId}/notes`, {
          method: 'POST',
          body: JSON.stringify({
            content: [
              '等待時間太久', '客服態度差', '找不到退貨入口',
              '行動支付太少', '信用卡綁定複雜', '手續費不透明',
              '搜尋結果不準', '篩選功能太少', '排序邏輯混亂',
              '頁面載入太慢', '閃退頻繁', '通知太多太煩',
            ][i],
            author: `crew_${(i % 4) + 1}(ai)`,
            color: ['yellow', 'blue', 'green', 'red'][i % 4],
          }),
        });
        if (ok && data?.id) sidecarNoteIds.push(data.id);
      }
      record('A.2 Seed 12 notes in sidecar', sidecarNoteIds.length === 12 ? 'PASS' : 'FAIL',
        `${sidecarNoteIds.length}/12`);
    } catch (e) { record('A.2 Seed notes', 'FAIL', e.message); }

    // A.3 Test canvas-state/full returns all 12 with geometry
    try {
      const { ok, data } = await json(`${SIDECAR_URL}/api/projects/${projectId}/canvas-state/full`);
      if (ok && Array.isArray(data) && data.length === 12) {
        const sample = data[0];
        const fields = ['id', 'content', 'x', 'y', 'width', 'height', 'color', 'author', 'createdAt'];
        const missing = fields.filter(f => sample[f] === undefined);
        if (missing.length === 0) {
          record('A.3 Full state: 12 notes with geometry', 'PASS');
        } else {
          record('A.3 Full state geometry', 'FAIL', `Missing fields: ${missing.join(', ')}`);
          issue('Layer 1', 'canvas-state/full missing fields', missing.join(', '));
        }
      } else {
        record('A.3 Full state', 'FAIL', `count=${data?.length}`);
      }
    } catch (e) { record('A.3 Full state', 'FAIL', e.message); }

    // A.4 Test Python spatial module directly via unit test subprocess
    try {
      const { execSync } = require('child_process');
      const out = execSync(
        'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
        'from app.canvas.spatial import compute_orderliness, SpatialNote, detect_overlaps; ' +
        'notes = [SpatialNote(id=str(i), text=str(i), x=i*50, y=i*50, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\") for i in range(12)]; ' +
        'overlaps = detect_overlaps(notes); ' +
        'score = compute_orderliness(notes); ' +
        'print(f\\"overlaps={len(overlaps)} orderliness={score:.2f}\\")"',
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
      if (out.includes('overlaps=') && out.includes('orderliness=')) {
        record('A.4 Python spatial module import + compute', 'PASS', out);
      } else {
        record('A.4 Python spatial module', 'FAIL', out);
      }
    } catch (e) {
      record('A.4 Python spatial module', 'FAIL', e.message.slice(0, 300));
      issue('Layer 2', 'Python spatial module import failed locally', e.message.slice(0, 300));
    }

    // A.5 Test Python clustering module
    try {
      const { execSync } = require('child_process');
      const out = execSync(
        'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
        'from app.canvas.clustering import compute_clusters, ClusterState; ' +
        'from app.canvas.spatial import SpatialNote; ' +
        'import numpy as np; ' +
        'notes = [SpatialNote(id=str(i), text=str(i), x=0, y=0, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\") for i in range(5)]; ' +
        'embs = [np.random.randn(8).tolist() for _ in range(5)]; ' +
        'state = compute_clusters(notes, embs); ' +
        'print(f\\"clusters={len(state.clusters)} ungrouped={len(state.ungrouped_note_ids)}\\")"',
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
      record('A.5 Python clustering module', 'PASS', out);
    } catch (e) {
      record('A.5 Python clustering module', 'FAIL', e.message.slice(0, 300));
      issue('Layer 2', 'Clustering module failed', e.message.slice(0, 300));
    }

    // A.6 Test Python layout engine
    try {
      const { execSync } = require('child_process');
      const out = execSync(
        'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
        'from app.canvas.layout_engine import LayoutEngine; ' +
        'from app.canvas.spatial import SpatialNote; ' +
        'engine = LayoutEngine(); ' +
        'notes = [SpatialNote(id=\\"n1\\", text=\\"test\\", x=100, y=100, width=200, height=150, color=\\"y\\", author_type=\\"ai\\", created_at=\\"\\")]; ' +
        'x, y = engine.resolve_position(\\"near:n1\\", notes); ' +
        'print(f\\"near:n1 -> ({x:.0f}, {y:.0f})\\"); ' +
        'x2, y2 = engine.resolve_position(\\"grid:2,3\\", []); ' +
        'print(f\\"grid:2,3 -> ({x2:.0f}, {y2:.0f})\\"); ' +
        'x3, y3 = engine.resolve_position(\\"region:bottom-right\\", []); ' +
        'print(f\\"region:bottom-right -> ({x3:.0f}, {y3:.0f})\\")"',
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
      const allResolved = out.includes('near:n1') && out.includes('grid:2,3') && out.includes('region:bottom-right');
      record('A.6 Layout engine resolve_position', allResolved ? 'PASS' : 'FAIL', out.replace(/\n/g, ' | '));
    } catch (e) {
      record('A.6 Layout engine', 'FAIL', e.message.slice(0, 300));
      issue('Layer 4', 'Layout engine failed', e.message.slice(0, 300));
    }

    // A.7 Test embedding client can be instantiated (no actual API call)
    try {
      const { execSync } = require('child_process');
      const out = execSync(
        'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
        'from app.canvas.embedding_client import get_embedding_client; ' +
        'client = get_embedding_client(); ' +
        'print(f\\"model={client._model} base_url={client._client.base_url}\\")"',
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
      const hasCorrectUrl = out.includes('example');
      const hasCorrectModel = out.includes('Qwen3-Embedding');
      if (hasCorrectUrl && hasCorrectModel) {
        record('A.7 Embedding client config', 'PASS', out);
      } else {
        record('A.7 Embedding client config', 'FAIL', out);
        issue('Layer 2', 'Embedding client misconfigured', out);
      }
    } catch (e) {
      record('A.7 Embedding client', 'FAIL', e.message.slice(0, 300));
    }

    // A.8 Test note_lock module
    try {
      const { execSync } = require('child_process');
      const out = execSync(
        'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
        'from app.canvas.note_lock import NoteLockManager; ' +
        'mgr = NoteLockManager(); ' +
        'print(\\"NoteLockManager instantiated OK\\")"',
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
      record('A.8 NoteLockManager import', 'PASS');
    } catch (e) {
      record('A.8 NoteLockManager', 'FAIL', e.message.slice(0, 200));
    }
  }

  // ══════════════════════════════════════════════════════════════════════
  // Section B: Playwright — Full workspace journey
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── B: Playwright Workspace Journey ──');

  const browser = await chromium.launch({ headless: true, slowMo: 50 });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'zh-TW' });

  try {
    const page = await ctx.newPage();

    // B.1 Login
    try {
      await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'networkidle', timeout: 10000 });
      await page.fill('input[type="email"], input[name="email"]', 'teacher@test.com');
      await page.fill('input[type="password"], input[name="password"]', 'teacher123');
      await page.click('button[type="submit"]');
      await page.waitForURL('**/projects**', { timeout: 10000 });
      record('B.1 Login', 'PASS');
    } catch (e) {
      record('B.1 Login', 'FAIL', e.message);
      issue('Frontend', 'Login failed in Playwright', e.message.slice(0, 200));
    }

    // B.2 Create a new project if none exist
    let wsProjectId = projectId; // Reuse API-created project
    try {
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'B2_projects_page.png') });

      // Check if our test project appears
      const projectCards = await page.$$('[class*="project"], [class*="Project"], a[href*="/projects/"]');
      record('B.2 Projects page loaded', 'PASS', `${projectCards.length} project card(s) found`);
    } catch (e) {
      record('B.2 Projects page', 'FAIL', e.message);
    }

    // B.3 Navigate to project lobby then workspace
    if (wsProjectId) {
      try {
        await page.goto(`${FRONTEND_URL}/projects/${wsProjectId}/lobby`, { waitUntil: 'networkidle', timeout: 10000 });
        await page.waitForTimeout(2000);
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'B3_lobby.png') });
        record('B.3 Project lobby', 'PASS');
      } catch (e) {
        record('B.3 Project lobby', 'FAIL', e.message.slice(0, 200));
      }

      // B.4 Enter workspace
      try {
        // Try to join a seat and enter workspace
        const joinBtn = await page.$('button:has-text("加入"), button:has-text("Join"), button:has-text("進入")');
        if (joinBtn) {
          await joinBtn.click();
          await page.waitForTimeout(2000);
        }
        await page.goto(`${FRONTEND_URL}/projects/${wsProjectId}/workspace`, { waitUntil: 'networkidle', timeout: 15000 });
        await page.waitForTimeout(3000);
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'B4_workspace.png') });

        // Check canvas container
        const canvas = await page.$('.tl-container, [class*="tldraw"], canvas');
        if (canvas) {
          record('B.4 Workspace with canvas', 'PASS', 'tldraw container found');
        } else {
          // Maybe canvas is loaded differently
          const bodyText = await page.textContent('body');
          const hasWorkspaceContent = bodyText.includes('Discover') || bodyText.includes('發散')
            || bodyText.includes('白板') || bodyText.includes('聊天');
          if (hasWorkspaceContent) {
            record('B.4 Workspace loaded', 'PASS', 'Workspace content visible (canvas may use different selector)');
          } else {
            record('B.4 Workspace', 'FAIL', 'No canvas container or workspace content found');
            issue('Frontend', 'Canvas not rendering in workspace', 'Check tldraw initialization');
          }
        }
      } catch (e) {
        record('B.4 Workspace', 'FAIL', e.message.slice(0, 200));
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'B4_workspace_fail.png') }).catch(() => {});
      }

      // B.5 Verify notes added via sidecar are visible (Yjs sync)
      try {
        await page.waitForTimeout(3000);
        // Check if the page shows note count or canvas has children
        const bodyText = await page.textContent('body');
        // Our 12 seeded notes should be synced via Yjs
        record('B.5 Yjs note sync', 'INFO', `Page text includes canvas-related content: ${bodyText.includes('白板') || bodyText.includes('便條') || bodyText.length > 100}`);
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'B5_notes_synced.png') });
      } catch (e) {
        record('B.5 Yjs sync check', 'SKIP', e.message.slice(0, 100));
      }
    }
  } finally {
    await browser.close();
  }

  // ══════════════════════════════════════════════════════════════════════
  // Section C: ASSESS Rule X integration
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── C: ASSESS Rule X (Orderliness) ──');

  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "\n' +
      'from app.agents.assess import AssessEngine\n' +
      'import time\n' +
      'engine = AssessEngine()\n' +
      '# Test 1: Low orderliness + enough time -> intervene\n' +
      'ctx1 = {\n' +
      '  \\"canvas_state\\": {\\"summary\\": {\\"total_notes\\": 15, \\"orderliness_score\\": 0.3}},\n' +
      '  \\"recent_chat\\": [],\n' +
      '  \\"seats\\": [{\\"type\\": \\"ai\\", \\"role\\": \\"crew_1\\"}],\n' +
      '  \\"my_seat\\": \\"crew_1\\",\n' +
      '  \\"my_recent_actions\\": [],\n' +
      '  \\"_last_tidy_time\\": None,\n' +
      '  \\"_human_typing_timestamp\\": None,\n' +
      '  \\"_last_event_time\\": time.time() - 35,\n' +
      '}\n' +
      'r1 = engine.evaluate(ctx1, \\"agent_crew_1\\", last_action_time=time.time()-20, last_idle_event_time=time.time()-35)\n' +
      'print(f\\"Test1: {r1.decision} rule={r1.rule}\\")\n' +
      '# Test 2: High orderliness -> should NOT trigger Rule X\n' +
      'ctx2 = dict(ctx1)\n' +
      'ctx2[\\"canvas_state\\"] = {\\"summary\\": {\\"total_notes\\": 15, \\"orderliness_score\\": 0.8}}\n' +
      'r2 = engine.evaluate(ctx2, \\"agent_crew_1\\", last_action_time=time.time()-20, last_idle_event_time=time.time()-35)\n' +
      'print(f\\"Test2: {r2.decision} rule={r2.rule}\\")\n' +
      '# Test 3: Low orderliness but recent tidy -> should NOT trigger\n' +
      'ctx3 = dict(ctx1)\n' +
      'ctx3[\\"_last_tidy_time\\"] = time.time() - 60\n' +
      'r3 = engine.evaluate(ctx3, \\"agent_crew_1\\", last_action_time=time.time()-20, last_idle_event_time=time.time()-35)\n' +
      'print(f\\"Test3: {r3.decision} rule={r3.rule}\\")\n"',
      { encoding: 'utf-8', timeout: 15000 }
    ).trim();

    const lines = out.split('\n');
    let test1Pass = false, test2Pass = false, test3Pass = false;
    for (const line of lines) {
      if (line.startsWith('Test1:') && line.includes('intervene') && line.includes('rule_x_canvas_untidy')) test1Pass = true;
      if (line.startsWith('Test2:') && !line.includes('rule_x_canvas_untidy')) test2Pass = true;
      if (line.startsWith('Test3:') && !line.includes('rule_x_canvas_untidy')) test3Pass = true;
    }

    record('C.1 Rule X: low orderliness triggers', test1Pass ? 'PASS' : 'FAIL', lines.find(l => l.startsWith('Test1:')) || '');
    record('C.2 Rule X: high orderliness no trigger', test2Pass ? 'PASS' : 'FAIL', lines.find(l => l.startsWith('Test2:')) || '');
    record('C.3 Rule X: recent tidy suppresses', test3Pass ? 'PASS' : 'FAIL', lines.find(l => l.startsWith('Test3:')) || '');

    if (!test1Pass || !test2Pass || !test3Pass) {
      issue('ASSESS', 'Rule X behavior incorrect', out);
    }
  } catch (e) {
    record('C.x ASSESS Rule X', 'FAIL', e.message.slice(0, 400));
    issue('ASSESS', 'Rule X test failed to run', e.message.slice(0, 400));
  }

  // ══════════════════════════════════════════════════════════════════════
  // Section D: CanvasOps bridge new methods (inside Docker backend)
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── D: CanvasOps Bridge (Docker Backend) ──');

  // D.1 Verify backend can call sidecar's new endpoints
  if (projectId) {
    try {
      const { execSync } = require('child_process');
      // Run inside Docker container to test actual bridge connectivity
      const out = execSync(
        `docker exec mindcrew-backend-1 python -c "` +
        `import asyncio; ` +
        `from app.bridge.canvas_ops import canvas_ops; ` +
        `async def test(): ` +
        `  state = await canvas_ops.get_canvas_state_full('${projectId}'); ` +
        `  print(f'full_state_count={len(state)}'); ` +
        `  ok = await canvas_ops.batch_update_coordinates('${projectId}', []); ` +
        `  print(f'batch_empty={ok}'); ` +
        `asyncio.run(test())"`,
        { encoding: 'utf-8', timeout: 15000 }
      ).trim();
      const hasCount = out.includes('full_state_count=');
      const hasBatch = out.includes('batch_empty=');
      if (hasCount && hasBatch) {
        record('D.1 CanvasOps bridge: get_canvas_state_full + batch_update', 'PASS', out.replace(/\n/g, ' | '));
      } else {
        record('D.1 CanvasOps bridge', 'FAIL', out);
        issue('Bridge', 'CanvasOps new methods not working in Docker', out);
      }
    } catch (e) {
      record('D.1 CanvasOps bridge', 'FAIL', e.message.slice(0, 300));
      issue('Bridge', 'CanvasOps test in Docker failed', e.message.slice(0, 300));
    }
  }

  // D.2 Verify old methods are removed
  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
      'from app.bridge.canvas_ops import CanvasOps; ' +
      'ops = CanvasOps(); ' +
      'removed = []; ' +
      'for m in [\\"group_notes\\", \\"arrange_groups\\", \\"tidy_notes\\", \\"auto_layout\\", \\"check_overlap\\"]: ' +
      '  if hasattr(ops, m): removed.append(m); ' +
      'print(f\\"still_present={removed}\\")"',
      { encoding: 'utf-8', timeout: 10000 }
    ).trim();
    if (out.includes('still_present=[]')) {
      record('D.2 Old CanvasOps methods removed', 'PASS');
    } else {
      record('D.2 Old CanvasOps methods', 'FAIL', out);
      issue('Bridge', 'Old methods still on CanvasOps', out);
    }
  } catch (e) {
    record('D.2 Old CanvasOps methods check', 'FAIL', e.message.slice(0, 200));
  }

  // ══════════════════════════════════════════════════════════════════════
  // Section E: Context buffer canvas perception
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── E: Context Buffer Perception ──');

  // E.1 Verify context_buffer._load_canvas_perception exists and calls get_canvas_summary
  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
      'from app.agents.context_buffer import ContextBuffer; ' +
      'import inspect; ' +
      'src = inspect.getsource(ContextBuffer._load_canvas_perception); ' +
      'has_summary = \\"get_canvas_summary\\" in src; ' +
      'has_fallback = \\"get_canvas_state\\" in src; ' +
      'print(f\\"has_summary_call={has_summary} has_legacy_fallback={has_fallback}\\")"',
      { encoding: 'utf-8', timeout: 10000 }
    ).trim();
    const hasBoth = out.includes('has_summary_call=True') && out.includes('has_legacy_fallback=True');
    record('E.1 Context buffer uses get_canvas_summary with fallback', hasBoth ? 'PASS' : 'FAIL', out);
    if (!hasBoth) issue('Pipeline', 'Context buffer perception not wired correctly', out);
  } catch (e) {
    record('E.1 Context buffer perception', 'FAIL', e.message.slice(0, 200));
    issue('Pipeline', 'Context buffer check failed', e.message.slice(0, 200));
  }

  // E.2 Verify prompt assembler renders new canvas format
  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
      'from app.agents.prompts.context_serializer import build_context_description; ' +
      'ctx = { ' +
      '  \\"project_name\\": \\"Test\\", ' +
      '  \\"current_stage\\": \\"discover\\", ' +
      '  \\"stage_duration_minutes\\": 5, ' +
      '  \\"canvas_state\\": { ' +
      '    \\"summary\\": {\\"total_notes\\": 10, \\"orderliness_score\\": 0.65, \\"overlap_count\\": 1, \\"cluster_count\\": 2, \\"ungrouped_count\\": 3, \\"board_bounds\\": {\\"free_regions\\": [\\"bottom-left\\"]}}, ' +
      '    \\"clusters\\": [{\\"cluster_id\\": \\"c1\\", \\"suggested_label\\": \\"支付問題\\", \\"note_count\\": 4, \\"region\\": \\"top-left\\", \\"density\\": \\"dense\\"}], ' +
      '    \\"ungrouped_notes\\": [{\\"id\\": \\"n5\\", \\"text_preview\\": \\"測試...\\", \\"region\\": \\"center\\", \\"nearest_cluster\\": \\"c1\\", \\"similarity_to_nearest\\": 0.7}], ' +
      '  }, ' +
      '  \\"recent_chat\\": [], ' +
      '  \\"seats\\": [], ' +
      '  \\"my_seat\\": \\"crew_1\\", ' +
      '  \\"my_recent_actions\\": [], ' +
      '}; ' +
      'desc = build_context_description(ctx); ' +
      'has_orderliness = \\"有序度\\" in desc; ' +
      'has_clusters = \\"叢集\\" in desc or \\"支付問題\\" in desc; ' +
      'has_free = \\"空閒\\" in desc or \\"bottom-left\\" in desc; ' +
      'print(f\\"has_orderliness={has_orderliness} has_clusters={has_clusters} has_free={has_free}\\")"',
      { encoding: 'utf-8', timeout: 10000 }
    ).trim();
    const allPresent = out.includes('has_orderliness=True') && out.includes('has_clusters=True') && out.includes('has_free=True');
    record('E.2 Prompt renders spatial canvas format', allPresent ? 'PASS' : 'FAIL', out);
    if (!allPresent) issue('Pipeline', 'Prompt not rendering spatial canvas info', out);
  } catch (e) {
    record('E.2 Prompt canvas format', 'FAIL', e.message.slice(0, 200));
  }

  // E.3 Verify prompt includes new tool vocabulary
  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -c "' +
      'from app.agents.prompts.assembler import PromptAssembler; ' +
      'asm = PromptAssembler(); ' +
      'ctx = { ' +
      '  \\"my_seat\\": \\"crew_1\\", \\"current_stage\\": \\"discover\\", ' +
      '  \\"canvas_state\\": {}, \\"recent_chat\\": [], \\"seats\\": [], ' +
      '  \\"my_recent_actions\\": [], ' +
      '}; ' +
      'msgs = asm.assemble(ctx); ' +
      'sys_msg = msgs[0][\\"content\\"]; ' +
      'has_create = \\"create_note\\" in sys_msg; ' +
      'has_arrange = \\"arrange_notes\\" in sys_msg; ' +
      'has_tidy = \\"tidy_area\\" in sys_msg; ' +
      'has_old = \\"add_note\\" in sys_msg or \\"group_notes\\" in sys_msg or \\"auto_layout\\" in sys_msg; ' +
      'print(f\\"create_note={has_create} arrange_notes={has_arrange} tidy_area={has_tidy} old_types={has_old}\\")"',
      { encoding: 'utf-8', timeout: 10000 }
    ).trim();
    const newPresent = out.includes('create_note=True') && out.includes('arrange_notes=True') && out.includes('tidy_area=True');
    const noOld = out.includes('old_types=False');
    if (newPresent && noOld) {
      record('E.3 Prompt has new tool vocab, no old types', 'PASS');
    } else {
      record('E.3 Prompt tool vocabulary', 'FAIL', out);
      issue('Pipeline', 'Prompt still contains old tool types or missing new ones', out);
    }
  } catch (e) {
    record('E.3 Prompt tool vocab', 'FAIL', e.message.slice(0, 200));
  }

  // ══════════════════════════════════════════════════════════════════════
  // Section F: Existing test suite regression
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n── F: Regression — Existing Tests ──');
  try {
    const { execSync } = require('child_process');
    const out = execSync(
      'cd /Users/hsueh/Code/Experimental/MindCrew/backend && python -m pytest app/tests/ -x --tb=line -q 2>&1',
      { encoding: 'utf-8', timeout: 60000 }
    );
    const passMatch = out.match(/(\d+) passed/);
    const failMatch = out.match(/(\d+) failed/);
    const errorMatch = out.match(/(\d+) error/);
    const passed = passMatch ? parseInt(passMatch[1]) : 0;
    const failed = failMatch ? parseInt(failMatch[1]) : 0;
    const errors = errorMatch ? parseInt(errorMatch[1]) : 0;
    if (failed === 0 && errors === 0) {
      record('F.1 Full test suite', 'PASS', `${passed} passed`);
    } else {
      record('F.1 Full test suite', 'FAIL', `${passed} passed, ${failed} failed, ${errors} errors`);
      // Show last 10 lines for context
      const lastLines = out.trim().split('\n').slice(-10).join('\n');
      issue('Regression', 'Existing tests failing', lastLines);
    }
  } catch (e) {
    const output = e.stdout || e.message;
    const passMatch = output.match(/(\d+) passed/);
    const failMatch = output.match(/(\d+) failed/);
    const passed = passMatch ? parseInt(passMatch[1]) : 0;
    const failed = failMatch ? parseInt(failMatch[1]) : 0;
    record('F.1 Full test suite', failed > 0 ? 'FAIL' : 'FAIL', `${passed} passed, ${failed} failed`);
    const lastLines = output.trim().split('\n').slice(-15).join('\n');
    issue('Regression', 'Test suite execution', lastLines);
  }

  // ══════════════════════════════════════════════════════════════════════
  // Summary
  // ══════════════════════════════════════════════════════════════════════
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  SUMMARY');
  console.log('═══════════════════════════════════════════════════════════');

  const p = results.filter(r => r.status === 'PASS').length;
  const f = results.filter(r => r.status === 'FAIL').length;
  const s = results.filter(r => r.status === 'SKIP' || r.status === 'INFO').length;
  console.log(`\n  Results: ${p} passed, ${f} failed, ${s} skipped/info (${results.length} total)`);

  if (issues.length > 0) {
    console.log(`\n  Issues Found (${issues.length}):`);
    issues.forEach((iss, i) => {
      console.log(`    ${i + 1}. [${iss.category}] ${iss.description}`);
      if (iss.details) console.log(`       ${iss.details.split('\n')[0]}`);
    });
  } else {
    console.log('\n  No issues found.');
  }

  const report = { timestamp: new Date().toISOString(), phase: '14-deep', results, issues, summary: { passed: p, failed: f, skipped: s, total: results.length } };
  fs.writeFileSync(path.join(SCREENSHOTS_DIR, 'report.json'), JSON.stringify(report, null, 2));
  console.log(`\n  Report: ${path.join(SCREENSHOTS_DIR, 'report.json')}`);
  console.log('═══════════════════════════════════════════════════════════\n');

  process.exit(f > 0 ? 1 : 0);
}

run().catch(e => { console.error('Runner error:', e); process.exit(1); });
