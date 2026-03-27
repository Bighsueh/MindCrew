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
  ai_contribution: AIContribution
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
