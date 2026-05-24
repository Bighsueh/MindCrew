/**
 * Phase 23 / 24 e2e — 共用 API helper。
 *
 * 直接打 backend (localhost:8000) 用來建專案 / 註冊 / 登入，
 * 避免每個 spec 都走 UI 註冊流程。
 */

const BACKEND_BASE = 'http://localhost:8000'

interface ApiResponse<T = unknown> {
  status: number
  body: T
}

export async function apiCall<T = unknown>(
  method: string,
  urlPath: string,
  body?: unknown,
  token?: string,
): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BACKEND_BASE}${urlPath}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let parsed: unknown
  try {
    parsed = text.length > 0 ? JSON.parse(text) : null
  } catch {
    parsed = text
  }
  return { status: res.status, body: parsed as T }
}

export interface AuthedAccount {
  email: string
  password: string
  token: string
}

/**
 * 嘗試登入；失敗則註冊一個 teacher 帳號（用於不需具體權限的場景）。
 */
export async function loginOrRegisterTeacher(
  email: string,
  password: string,
  displayName: string,
): Promise<AuthedAccount> {
  const login = await apiCall<{ access_token: string }>('POST', '/api/auth/login', {
    email,
    password,
  })
  if (login.status === 200) {
    return { email, password, token: login.body.access_token }
  }
  const reg = await apiCall<{ access_token: string }>('POST', '/api/auth/register', {
    email,
    password,
    display_name: displayName,
    role: 'teacher',
  })
  if (reg.status !== 200 && reg.status !== 201) {
    throw new Error(
      `Auth failed for ${email}: login=${login.status} register=${reg.status} body=${JSON.stringify(reg.body)}`,
    )
  }
  // 繞過 backend register→subsequent-request 之間 session commit 可見性 race：
  // 先重複 login 直到拿到 token（commit 之後 login 走 fresh select by email）。
  for (let i = 0; i < 10; i++) {
    const r = await apiCall<{ access_token: string }>('POST', '/api/auth/login', {
      email,
      password,
    })
    if (r.status === 200) {
      return { email, password, token: r.body.access_token }
    }
    await new Promise((r) => setTimeout(r, 200))
  }
  // fallback：用 register 回傳的 token（雖然 JWT sub 對應的 user 可能還未可見）
  return { email, password, token: reg.body.access_token }
}

export async function registerStudent(
  teacherToken: string,
  email: string,
  password: string,
  displayName: string,
): Promise<AuthedAccount> {
  // 教師管理端點建立學生（若已存在 409 → idempotent；其他 4xx/5xx → 拋錯）
  const create = await apiCall('POST', '/api/teacher/students', {
    email,
    password,
    display_name: displayName,
    can_create_project: false,
  }, teacherToken)
  if (create.status !== 201 && create.status !== 409) {
    throw new Error(
      `Create student failed: status=${create.status} body=${JSON.stringify(create.body)}`,
    )
  }
  // 同樣 race：retry login 至多 10 次（每次 200ms）。
  for (let i = 0; i < 10; i++) {
    const login = await apiCall<{ access_token: string }>('POST', '/api/auth/login', {
      email,
      password,
    })
    if (login.status === 200) {
      return { email, password, token: login.body.access_token }
    }
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(`Student login failed after retries: ${email}`)
}

const VALID_PERSONA = (idx: number) => ({
  seat_role: `crew_${idx}`,
  persona: {
    name: `測試隊友 ${idx}`,
    role: `測試角色 ${idx}`,
    expertise: '測試專長',
    personality_axis: ['supportive', 'balanced', 'contrarian'][idx - 1] ?? 'balanced',
    personality_desc: '務實穩健、邏輯清晰、執行力強',
    backstory: '測試用人設',
    lens_affinities: {
      empathy: 0.5,
      structure: 0.5,
      creativity: 0.5,
      feasibility: 0.5,
    },
  },
})

const VALID_TIMER_CONFIG = {
  total_session_minutes: 120,
  macro_budgets: { discover: 45, define: 30, develop: 25, deliver: 20 },
  preset_id: 'timer_preset_2hr',
}

export async function createMinimalProject(
  token: string,
  name: string,
): Promise<string> {
  const resp = await apiCall<{ id: string }>('POST', '/api/projects', {
    name,
    description: 'e2e fixture',
    ai_crew_count: 3,
    personas: [VALID_PERSONA(1), VALID_PERSONA(2), VALID_PERSONA(3)],
    timer_config: VALID_TIMER_CONFIG,
  }, token)
  if (resp.status !== 200 && resp.status !== 201) {
    throw new Error(`Create project failed: status=${resp.status} body=${JSON.stringify(resp.body)}`)
  }
  return resp.body.id
}
