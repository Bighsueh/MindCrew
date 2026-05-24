import type {
  User,
  Project,
  Seat,
  Message,
  StageInfo,
  StageHistoryEntry,
  AgentTrace,
  TeacherProjectSummary,
  ProjectRecord,
  AIContribution,
  CrewPersonaAssignment,
  Persona,
  SeatRole,
} from './models'

// ── Auth ──────────────────────────────────────────────────────────────────

export interface RegisterRequest {
  email: string
  password: string
  display_name: string
  role?: 'teacher' | 'student'
}

export interface LoginRequest {
  email: string
  password: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: User
}

export interface RefreshRequest {
  refresh_token: string
}

// ── Projects ──────────────────────────────────────────────────────────────

// specs/16-timer-system.md：老師建立專案時的 timer 配置。
// 對齊後端 app/timer/schemas.py::TimerConfig，未提供時 backend 走 DEFAULT_2HR_PRESET。
export interface TimerConfigInput {
  total_session_minutes: number
  macro_budgets: {
    discover: number
    define: number
    develop: number
    deliver: number
  }
  sub_phase_overrides?: Record<string, number>
  warning_thresholds_pct?: number[]
  auto_advance_on_timeout?: boolean
  allow_overrun?: boolean
  preset_id: string
}

export interface CreateProjectRequest {
  name: string
  description: string
  constraints?: string
  /** Phase 27：使用者於 Step 2 勾選的利害關係人；長度必須 == ai_crew_count（提供時）。 */
  stakeholders?: StakeholderSelectionInput[]
  ai_contribution: AIContribution
  // Phase 21: 教師可選 AI 組員人數（1–4），預設 3。Persona 數量必須等於此值。
  ai_crew_count: number
  personas: CrewPersonaAssignment[]
  // specs/16-timer-system.md：建立者必須明確選 preset 或自訂；後端拒絕缺值。
  timer_config: TimerConfigInput
  // Phase 22: 學生建立活動時可選填教師的 signature_code 即被列管
  teacher_signature_code?: string
}

/** Phase 27：post body 用的 stakeholder shape（後端 Pydantic 對應）。 */
export interface StakeholderSelectionInput {
  id: string
  name: string
  role: string
  relevance: string
}

export interface GeneratePersonasRequest {
  title: string
  description?: string
  constraints?: string
  num_personas?: number
  /** Phase 27：使用者勾選的利害關係人；提供則跳過內部 stakeholder mapping。 */
  stakeholders?: StakeholderSelectionInput[]
}

/** Phase 27：POST /api/projects/draft/suggest-constraints body。 */
export interface SuggestConstraintsRequest {
  title: string
  description: string
}

/** Phase 27：POST /api/projects/draft/suggest-stakeholders body。 */
export interface SuggestStakeholdersRequest {
  title: string
  description?: string
  constraints?: string
  existing_names?: string[]
}

export interface GeneratePersonasResponse {
  personas: Persona[]
}

export interface UpdateSeatPersonaRequest {
  persona: Persona
}

export interface JoinProjectRequest {
  seat_role: SeatRole
}

export interface JoinProjectResponse {
  seat: Seat
  workspace_url: string
}

export interface AdvanceStageRequest {
  from: string
  to: string
}

export interface AdvanceStageResponse {
  current_stage: string
  previous_snapshot_id: string
}

export interface AdvanceMicroPhaseRequest {
  from_phase: string
  to_phase: string
}

export interface AdvanceMicroPhaseResponse {
  current_micro_phase: string
  is_backtrack: boolean
}

// ── Messages ──────────────────────────────────────────────────────────────

export interface MessagesResponse {
  messages: Message[]
  has_more: boolean
}

// ── Teacher ──────────────────────────────────────────────────────────────

export interface CreateStudentRequest {
  email: string
  password: string
  display_name: string
  can_create_project: boolean
}

export interface UpdateStudentPermissionRequest {
  can_create_project: boolean
}

// ── Agent traces ──────────────────────────────────────────────────────────

export interface AgentTracesResponse {
  traces: AgentTrace[]
  has_more: boolean
}

// ── Teacher Monitoring ──────────────────────────────────────────────────

export interface SendHintRequest {
  content: string
}

export interface SendHintResponse {
  message_id: string
  sent_at: string
}

// ── Re-exports for convenience ────────────────────────────────────────────

export type {
  User,
  Project,
  Seat,
  Message,
  StageInfo,
  StageHistoryEntry,
  TeacherProjectSummary,
  ProjectRecord,
}
