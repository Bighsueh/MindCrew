/**
 * Phase 28 — Turn-Taking Controller smoke test (Playwright with Chrome)
 *
 * 驗收標準（ 與 plan 驗證表）：
 *  AC1：新建專案預設 turn_policy = 'cued'。
 *  AC2：PATCH /api/projects/{id}/turn-policy 教師可改、其他人 403。
 *  AC3：切換後 GET 取回的 turn_policy 立刻反映新值。
 *  AC4：學生在 Workspace 不會看到 TurnPolicySwitcher (僅教師/admin 可見)。
 *  AC5：建立表單裡的「對話模式」三選一可以送出非預設值。
 *
 * 範圍：只驗 API + UI 條件可見性，不驗 LLM agent 實際行為 (留給後端 unit test)。
 * 假設：後端 / 前端都已起來；test account 可登入或註冊。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, apiCall, createMinimalProject } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const TEACHER_EMAIL = 'qa_turn_policy_teacher@mindcrew.test'
const TEACHER_PASSWORD =
  process.env.E2E_TEST_PASSWORD || 'change-me-set-E2E_TEST_PASSWORD'

test.describe('Phase 28 — Turn-Taking Controller', () => {
  let teacherToken: string
  let projectId: string
  let adminToken: string

  test.beforeAll(async () => {
    const account = await loginOrRegisterTeacher(
      TEACHER_EMAIL,
      TEACHER_PASSWORD,
      'QA Turn Policy Teacher',
    )
    teacherToken = account.token
    projectId = await createMinimalProject(teacherToken, 'Phase 28 Turn Policy Smoke')

    // Admin token — needed for AC2+AC3 because the teacher who creates a project
    // via createMinimalProject is the creator but NOT the linked_teacher.
    // PATCH /turn-policy only allows linked_teacher or admin.
    // (AC2 spec intent: "教師可改" refers to the linked teacher; admin is the
    //  simplest way to drive that path without a full student→link_teacher flow.)
    const adminLogin = await apiCall<{ access_token: string }>('POST', '/api/auth/login', {
      email: 'admin',
      password: process.env.E2E_ADMIN_PASSWORD || 'change-me-set-E2E_ADMIN_PASSWORD',
    })
    if (adminLogin.status !== 200) {
      throw new Error(`Admin login failed: ${JSON.stringify(adminLogin.body)}`)
    }
    adminToken = adminLogin.body.access_token
  })

  test('AC1：新建專案預設 turn_policy = cued', async () => {
    const resp = await apiCall<{ turn_policy: string }>(
      'GET',
      `/api/projects/${projectId}`,
      undefined,
      teacherToken,
    )
    expect(resp.status).toBe(200)
    expect(resp.body.turn_policy).toBe('cued')
  })

  test('AC2 + AC3：admin PATCH 切換成 round_robin → GET 立即反映', async () => {
    // PATCH /turn-policy requires linked_teacher or admin.
    // Here we use admin to verify the endpoint works end-to-end.
    // The linked_teacher path is covered by phase28-turn-policy-extended.spec.ts.
    const patch = await apiCall<{ policy: string; applied_at: string }>(
      'PATCH',
      `/api/projects/${projectId}/turn-policy`,
      { policy: 'round_robin' },
      adminToken,
    )
    expect(patch.status).toBe(200)
    expect(patch.body.policy).toBe('round_robin')

    const get = await apiCall<{ turn_policy: string }>(
      'GET',
      `/api/projects/${projectId}`,
      undefined,
      teacherToken,
    )
    expect(get.body.turn_policy).toBe('round_robin')
  })

  test('AC2 (negative)：invalid policy 回 422', async () => {
    const resp = await apiCall(
      'PATCH',
      `/api/projects/${projectId}/turn-policy`,
      { policy: 'free_for_all' },
      teacherToken,
    )
    expect(resp.status).toBe(422)
  })

  test('AC4：學生在 Workspace 不會看到 turn-policy selector', async ({ page }) => {
    // 為了測試學生視角，新註冊一個 student 帳號。
    // 注意：register 後 user 對後續 select-by-id 有可見性 race（已知 backend
    // 問題），register 拿到的 token 不能立刻拿來打 PR — 必須再 login 一次拿
    // 一個 fresh JWT（login 走 select-by-email 沒有 race）。
    const studentEmail = `qa_turn_policy_student_${Date.now()}@mindcrew.test`
    const studentReg = await apiCall<{ access_token: string }>(
      'POST',
      '/api/auth/register',
      {
        email: studentEmail,
        password: TEACHER_PASSWORD,
        display_name: 'QA Student',
        role: 'student',
      },
    )
    expect([200, 201]).toContain(studentReg.status)

    // 重 login 拿可用 token（用 helpers/api.ts 既有的 retry 模式）
    let studentToken = ''
    for (let i = 0; i < 10; i++) {
      const r = await apiCall<{ access_token: string }>('POST', '/api/auth/login', {
        email: studentEmail,
        password: TEACHER_PASSWORD,
      })
      if (r.status === 200) {
        studentToken = r.body.access_token
        break
      }
      await new Promise((res) => setTimeout(res, 200))
    }
    expect(studentToken).not.toBe('')

    const studentProjectId = await createMinimalProject(
      studentToken,
      'Phase 28 Student Workspace',
    )

    await suppressFirstRunModals(page)
    await loginViaUi(page, studentEmail, TEACHER_PASSWORD)
    await page.goto(`/projects/${studentProjectId}/workspace`, {
      waitUntil: 'networkidle',
    })
    await page.waitForTimeout(1500)

    // 學生身份不應看到 switcher
    const selector = page.locator('[data-testid="turn-policy-select"]')
    await expect(selector).toHaveCount(0)
  })
})
