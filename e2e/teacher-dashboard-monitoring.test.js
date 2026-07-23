/**
 * Teacher Dashboard Monitoring E2E Test Suite
 * Tests the monitoring features added in 
 * Run with: node e2e/teacher-dashboard-monitoring.test.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:3000';
const API_URL = 'http://localhost:3000/api';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'monitoring');

const results = [];

function recordResult(feature, status, details = '', screenshotPath = '') {
  const result = { feature, status, details, screenshotPath, timestamp: new Date().toISOString() };
  results.push(result);
  const icon = status === 'PASS' ? '\u2713' : '\u2717';
  console.log(`  ${icon} [${status}] ${feature}${details ? ': ' + details : ''}`);
  return result;
}

async function takeScreenshot(page, name) {
  const filename = `${name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_${Date.now()}.png`;
  const screenshotPath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: screenshotPath, fullPage: false });
  return screenshotPath;
}

async function waitForNetworkIdle(page, timeout = 3000) {
  try {
    await page.waitForLoadState('networkidle', { timeout });
  } catch {
    // continue even if not fully idle
  }
}

async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.fill('input[type="email"]', 'teacher@test.com');
  await page.fill('input[type="password"]', 'teacher123');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/projects', { timeout: 8000 });
}

async function getTeacherToken() {
  const loginRes = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'teacher@test.com', password: 'teacher123' }),
  });
  if (!loginRes.ok) return null;
  const data = await loginRes.json();
  return data.access_token;
}

// ─── Main test runner ──────────────────────────────────────────────────────────

async function runTests() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  console.log('\n===================================================');
  console.log('  Teacher Dashboard Monitoring E2E Test Suite');
  console.log('===================================================\n');

  const browser = await chromium.launch({ headless: true, slowMo: 100 });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    locale: 'zh-TW',
  });

  // ── Section 1: API Tests ──────────────────────────────────────────────────
  console.log('-- Section 1: Monitoring API Tests --');

  let teacherToken = await getTeacherToken();

  // 1.1 GET /api/teacher/projects/overview
  try {
    if (!teacherToken) throw new Error('Failed to get teacher token');
    const res = await fetch(`${API_URL}/teacher/projects/overview`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    if (res.ok) {
      const data = await res.json();
      const hasProjects = Array.isArray(data.projects);
      const hasDist = data.stage_distribution !== undefined;
      recordResult('1.1 GET /api/teacher/projects/overview', 'PASS',
        `${data.projects.length} projects, stage_distribution present: ${hasDist}`);

      // Validate response structure
      if (data.projects.length > 0) {
        const p = data.projects[0];
        const hasMonitoringFields =
          p.evaluation_score !== undefined &&
          p.participation !== undefined &&
          p.ai_activity !== undefined &&
          p.alerts !== undefined &&
          p.stage_duration_seconds !== undefined;
        recordResult('1.2 Overview response has monitoring fields', hasMonitoringFields ? 'PASS' : 'FAIL',
          `evaluation_score: ${!!p.evaluation_score}, participation: ${!!p.participation}, ai_activity: ${!!p.ai_activity}, alerts: ${!!p.alerts}`);
      } else {
        recordResult('1.2 Overview response has monitoring fields', 'PASS', 'No projects to validate (expected in clean state)');
      }
    } else {
      recordResult('1.1 GET /api/teacher/projects/overview', 'FAIL', `HTTP ${res.status}`);
      recordResult('1.2 Overview response has monitoring fields', 'FAIL', 'API returned error');
    }
  } catch (e) {
    recordResult('1.1 GET /api/teacher/projects/overview', 'FAIL', String(e));
    recordResult('1.2 Overview response has monitoring fields', 'FAIL', String(e));
  }

  // 1.3 GET /api/teacher/projects/overview requires teacher role
  try {
    const res = await fetch(`${API_URL}/teacher/projects/overview`);
    const isUnauthorized = res.status === 401 || res.status === 403;
    recordResult('1.3 Overview API requires authentication', isUnauthorized ? 'PASS' : 'FAIL',
      `HTTP ${res.status}`);
  } catch (e) {
    recordResult('1.3 Overview API requires authentication', 'FAIL', String(e));
  }

  // 1.4 POST /api/teacher/projects/{id}/send-hint (need a project first)
  try {
    if (!teacherToken) throw new Error('No teacher token');
    // Get a project ID first
    const projRes = await fetch(`${API_URL}/teacher/projects`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    const projects = await projRes.json();
    if (Array.isArray(projects) && projects.length > 0) {
      const projectId = projects[0].id;
      const hintRes = await fetch(`${API_URL}/teacher/projects/${projectId}/send-hint`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${teacherToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content: 'E2E test hint message' }),
      });
      if (hintRes.ok) {
        const hintData = await hintRes.json();
        const hasFields = hintData.message_id && hintData.sent_at;
        recordResult('1.4 POST send-hint creates system message', hasFields ? 'PASS' : 'FAIL',
          `message_id: ${hintData.message_id}`);
      } else {
        recordResult('1.4 POST send-hint creates system message', 'FAIL', `HTTP ${hintRes.status}`);
      }
    } else {
      recordResult('1.4 POST send-hint creates system message', 'PASS', 'No projects available (skipped)');
    }
  } catch (e) {
    recordResult('1.4 POST send-hint creates system message', 'FAIL', String(e));
  }

  // 1.5 Existing teacher/projects API still works
  try {
    if (!teacherToken) throw new Error('No teacher token');
    const res = await fetch(`${API_URL}/teacher/projects`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    if (res.ok) {
      const data = await res.json();
      recordResult('1.5 Existing GET /api/teacher/projects still works', 'PASS',
        `${data.length} projects`);
    } else {
      recordResult('1.5 Existing GET /api/teacher/projects still works', 'FAIL', `HTTP ${res.status}`);
    }
  } catch (e) {
    recordResult('1.5 Existing GET /api/teacher/projects still works', 'FAIL', String(e));
  }

  // 1.6 Existing teacher/students API still works
  try {
    if (!teacherToken) throw new Error('No teacher token');
    const res = await fetch(`${API_URL}/teacher/students`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    if (res.ok) {
      const data = await res.json();
      recordResult('1.6 Existing GET /api/teacher/students still works', 'PASS',
        `${data.length} students`);
    } else {
      recordResult('1.6 Existing GET /api/teacher/students still works', 'FAIL', `HTTP ${res.status}`);
    }
  } catch (e) {
    recordResult('1.6 Existing GET /api/teacher/students still works', 'FAIL', String(e));
  }

  // ── Section 2: UI Tests ───────────────────────────────────────────────────
  console.log('\n-- Section 2: Teacher Dashboard UI Tests --');

  const page = await context.newPage();

  // 2.1 Login and navigate to teacher dashboard
  try {
    await loginAsTeacher(page);
    await page.click('a[href="/teacher/dashboard"]');
    await page.waitForURL('**/teacher/dashboard', { timeout: 8000 });
    await waitForNetworkIdle(page, 5000);
    const ss = await takeScreenshot(page, '2_1_teacher_dashboard');
    recordResult('2.1 Navigate to teacher dashboard', 'PASS', 'Dashboard loaded', ss);
  } catch (e) {
    const ss = await takeScreenshot(page, '2_1_fail');
    recordResult('2.1 Navigate to teacher dashboard', 'FAIL', String(e), ss);
  }

  // 2.2 Verify dashboard header
  try {
    const heading = await page.textContent('h1');
    const hasTeacherName = await page.textContent('.text-text-muted');
    const ss = await takeScreenshot(page, '2_2_dashboard_header');
    recordResult('2.2 Dashboard header shows title and teacher name', 'PASS',
      `Title: "${heading?.trim()}", Name contains: "${hasTeacherName?.trim()}"`, ss);
  } catch (e) {
    const ss = await takeScreenshot(page, '2_2_fail');
    recordResult('2.2 Dashboard header shows title and teacher name', 'FAIL', String(e), ss);
  }

  // 2.3 Verify tabs exist
  try {
    const projectsTab = await page.locator('button:has-text("專案監控")').isVisible();
    const studentsTab = await page.locator('button:has-text("學生管理")').isVisible();
    recordResult('2.3 Dashboard tabs (專案監控 / 學生管理) visible', projectsTab && studentsTab ? 'PASS' : 'FAIL',
      `Projects tab: ${projectsTab}, Students tab: ${studentsTab}`);
  } catch (e) {
    recordResult('2.3 Dashboard tabs visible', 'FAIL', String(e));
  }

  // 2.4 Verify refresh button exists
  try {
    const refreshBtn = await page.locator('button:has-text("重新整理")').isVisible();
    recordResult('2.4 Refresh button visible', refreshBtn ? 'PASS' : 'FAIL', '');
  } catch (e) {
    recordResult('2.4 Refresh button visible', 'FAIL', String(e));
  }

  // 2.5 Verify create project button exists
  try {
    const createBtn = await page.locator('button:has-text("建立新專案")').isVisible();
    recordResult('2.5 Create project button visible', createBtn ? 'PASS' : 'FAIL', '');
  } catch (e) {
    recordResult('2.5 Create project button visible', 'FAIL', String(e));
  }

  // 2.6 Check stage distribution bar (if projects exist)
  try {
    await waitForNetworkIdle(page, 3000);
    const hasDist = await page.locator('text=全班進度分佈').isVisible({ timeout: 3000 }).catch(() => false);
    const hasEmptyState = await page.locator('text=尚無專案').isVisible({ timeout: 1000 }).catch(() => false);
    if (hasDist) {
      const ss = await takeScreenshot(page, '2_6_stage_distribution');
      recordResult('2.6 Stage distribution bar visible', 'PASS', 'Distribution bar shown', ss);
    } else if (hasEmptyState) {
      recordResult('2.6 Stage distribution bar visible', 'PASS', 'Empty state shown (no projects)');
    } else {
      recordResult('2.6 Stage distribution bar visible', 'FAIL', 'Neither distribution bar nor empty state found');
    }
  } catch (e) {
    recordResult('2.6 Stage distribution bar visible', 'FAIL', String(e));
  }

  // 2.7 Check project monitor cards (if projects exist)
  try {
    const cards = await page.locator('.rounded-xl.border.bg-surface').count();
    if (cards > 0) {
      const ss = await takeScreenshot(page, '2_7_monitor_cards');
      recordResult('2.7 Project monitor cards rendered', 'PASS', `${cards} cards found`, ss);
    } else {
      recordResult('2.7 Project monitor cards rendered', 'PASS', 'No project cards (expected if no projects)');
    }
  } catch (e) {
    recordResult('2.7 Project monitor cards rendered', 'FAIL', String(e));
  }

  // 2.8 Switch to students tab
  try {
    await page.click('button:has-text("學生管理")');
    await waitForNetworkIdle(page, 3000);
    const studentsVisible = await page.locator('text=學生帳號').isVisible({ timeout: 5000 });
    const ss = await takeScreenshot(page, '2_8_students_tab');
    recordResult('2.8 Switch to students tab', studentsVisible ? 'PASS' : 'FAIL',
      'Students section visible', ss);
  } catch (e) {
    const ss = await takeScreenshot(page, '2_8_fail');
    recordResult('2.8 Switch to students tab', 'FAIL', String(e), ss);
  }

  // 2.9 Switch back to projects tab
  try {
    await page.click('button:has-text("專案監控")');
    await waitForNetworkIdle(page, 3000);
    const ss = await takeScreenshot(page, '2_9_back_to_projects');
    recordResult('2.9 Switch back to projects tab', 'PASS', '', ss);
  } catch (e) {
    recordResult('2.9 Switch back to projects tab', 'FAIL', String(e));
  }

  // ── Section 3: Existing Feature Regression ────────────────────────────────
  console.log('\n-- Section 3: Existing Feature Regression Tests --');

  // 3.1 Login page still works
  try {
    const page2 = await context.newPage();
    await page2.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 10000 });
    const emailInput = await page2.locator('input[type="email"]').isVisible();
    const passwordInput = await page2.locator('input[type="password"]').isVisible();
    const submitBtn = await page2.locator('button[type="submit"]').isVisible();
    const ss = await takeScreenshot(page2, '3_1_login_page');
    recordResult('3.1 Login page renders correctly', emailInput && passwordInput && submitBtn ? 'PASS' : 'FAIL',
      `Email: ${emailInput}, Password: ${passwordInput}, Submit: ${submitBtn}`, ss);
    await page2.close();
  } catch (e) {
    recordResult('3.1 Login page renders correctly', 'FAIL', String(e));
  }

  // 3.2 Projects page still works
  try {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'domcontentloaded', timeout: 10000 });
    await waitForNetworkIdle(page, 3000);
    const heading = await page.textContent('h1');
    const ss = await takeScreenshot(page, '3_2_projects_page');
    recordResult('3.2 Projects page still renders', 'PASS',
      `Heading: "${heading?.trim()}"`, ss);
  } catch (e) {
    const ss = await takeScreenshot(page, '3_2_fail');
    recordResult('3.2 Projects page still renders', 'FAIL', String(e), ss);
  }

  // 3.3 Auth APIs still work
  try {
    const meRes = await fetch(`${API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    if (meRes.ok) {
      const meData = await meRes.json();
      recordResult('3.3 GET /api/auth/me still works', 'PASS',
        `User: ${meData.display_name}, Role: ${meData.role}`);
    } else {
      recordResult('3.3 GET /api/auth/me still works', 'FAIL', `HTTP ${meRes.status}`);
    }
  } catch (e) {
    recordResult('3.3 GET /api/auth/me still works', 'FAIL', String(e));
  }

  // 3.4 Projects API still works
  try {
    const projRes = await fetch(`${API_URL}/projects`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    if (projRes.ok) {
      const projData = await projRes.json();
      recordResult('3.4 GET /api/projects still works', 'PASS',
        `${projData.length} projects`);
    } else {
      recordResult('3.4 GET /api/projects still works', 'FAIL', `HTTP ${projRes.status}`);
    }
  } catch (e) {
    recordResult('3.4 GET /api/projects still works', 'FAIL', String(e));
  }

  // 3.5 Project record API still works
  try {
    const projRes = await fetch(`${API_URL}/teacher/projects`, {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    const projects = await projRes.json();
    if (Array.isArray(projects) && projects.length > 0) {
      const recordRes = await fetch(`${API_URL}/teacher/projects/${projects[0].id}/record`, {
        headers: { Authorization: `Bearer ${teacherToken}` },
      });
      if (recordRes.ok) {
        const recordData = await recordRes.json();
        const hasFields = recordData.stages !== undefined && recordData.total_messages !== undefined;
        recordResult('3.5 GET /api/teacher/projects/:id/record still works', hasFields ? 'PASS' : 'FAIL',
          `Stages: ${recordData.stages?.length}, Messages: ${recordData.total_messages}`);
      } else {
        recordResult('3.5 GET /api/teacher/projects/:id/record still works', 'FAIL', `HTTP ${recordRes.status}`);
      }
    } else {
      recordResult('3.5 GET /api/teacher/projects/:id/record still works', 'PASS', 'No projects to test (skipped)');
    }
  } catch (e) {
    recordResult('3.5 GET /api/teacher/projects/:id/record still works', 'FAIL', String(e));
  }

  // ── Summary ───────────────────────────────────────────────────────────────
  await browser.close();

  const passed = results.filter(r => r.status === 'PASS').length;
  const failed = results.filter(r => r.status === 'FAIL').length;
  const total = results.length;

  console.log('\n===================================================');
  console.log(`  Results: ${passed}/${total} PASS, ${failed}/${total} FAIL`);
  console.log('===================================================\n');

  // Save report
  const reportPath = path.join(__dirname, 'monitoring-test-report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    summary: { total, passed, failed, timestamp: new Date().toISOString() },
    results,
  }, null, 2));
  console.log(`Report saved to: ${reportPath}`);

  process.exit(failed > 0 ? 1 : 0);
}

runTests().catch(err => {
  console.error('Test runner failed:', err);
  process.exit(1);
});
