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

export interface CreateProjectRequest {
  name: string
  description: string
  constraints?: string
  ai_contribution: AIContribution
  // Phase 21: 教師可選 AI 組員人數（1–4），預設 3。Persona 數量必須等於此值。
  ai_crew_count: number
  personas: CrewPersonaAssignment[]
}

export interface GeneratePersonasRequest {
  title: string
  description?: string
  constraints?: string
  num_personas?: number
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
