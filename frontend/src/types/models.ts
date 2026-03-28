// ── Domain model types ──────────────────────────────────────────────────────

export type UserRole = 'teacher' | 'student'
export type AIContribution = 'low' | 'medium' | 'high'
export type DTStage = 'discover' | 'define' | 'develop' | 'deliver' | 'completed'
export type ProjectStatus = 'active' | 'completed' | 'archived'
export type SeatRole = 'supervisor' | 'crew_1' | 'crew_2' | 'crew_3' | 'crew_4'
export type OccupantType = 'human' | 'ai'
export type SenderType = 'human' | 'ai' | 'system'

export interface User {
  id: string
  email: string
  display_name: string
  role: UserRole
  can_create_project: boolean
  created_at?: string
}

export interface Seat {
  id: string
  project_id: string
  seat_role: SeatRole
  occupant_type: OccupantType
  user_id?: string | null
  agent_id?: string | null
  display_name?: string
  state: string
  joined_at?: string | null
  updated_at: string
}

export interface SeatSummary {
  human: number
  ai: number
}

export interface Project {
  id: string
  name: string
  description?: string
  creator_id: string
  current_stage: DTStage
  ai_contribution: AIContribution
  status: ProjectStatus
  seats?: Seat[]
  seat_summary?: SeatSummary
  created_at: string
  updated_at: string
}

export interface ProjectListItem {
  id: string
  name: string
  description?: string
  current_stage: DTStage
  status: ProjectStatus
  creator_id: string
  seat_summary: SeatSummary
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  project_id: string
  sender_type: SenderType
  sender_id: string
  sender_name: string
  content: string
  stage: DTStage
  created_at: string
}

export interface StageInfo {
  current_stage: DTStage
  started_at: string
  duration_seconds: number
}

export interface StageHistoryEntry {
  id?: string
  from_stage: DTStage
  to_stage: DTStage
  triggered_by: string
  duration_seconds?: number
  canvas_snapshot?: unknown
  created_at: string
}

export interface AgentTrace {
  id: string
  agent_id: string
  stage: DTStage
  assess_result: 'intervene' | 'wait' | 'skip'
  assess_rule?: string
  assess_details?: unknown
  prompt_text?: string
  llm_response?: string
  llm_model?: string
  llm_tokens_in?: number
  llm_tokens_out?: number
  llm_latency_ms?: number
  action_type?: 'chat' | 'canvas' | 'both' | 'no_action'
  action_details?: unknown
  action_result?: 'success' | 'blocked' | 'error'
  created_at: string
}

export interface TeacherProjectSummary {
  id: string
  name: string
  current_stage: DTStage
  status: ProjectStatus
  seat_summary: SeatSummary
  note_count: number
  last_activity: string
}

export interface ProjectRecord {
  project: Project
  stages: Array<{
    stage: DTStage
    duration_seconds: number
    canvas_snapshot?: unknown
    started_at: string
  }>
  total_messages: number
  total_notes: number
  llm_usage: {
    total_tokens: number
    total_calls: number
    total_cost_estimate: string
  }
}

// ── Lobby Types ─────────────────────────────────────────────────────────

export interface CanvasNote {
  id: string
  content: string
  color: string
  author: string
  group_name: string | null
}

export interface CanvasGroup {
  name: string
  notes: string[]
}

export interface CanvasStateResponse {
  total_notes: number
  groups: CanvasGroup[]
  ungrouped: string[]
  notes: CanvasNote[]
}

export interface ProjectSummaryResponse {
  summary: string
  topics: string[]
  current_focus: string
  blind_spots: string[]
  generated_at: string
}

// ── Teacher Dashboard Monitoring ─────────────────────────────────────────

export interface EvaluationScoreSummary {
  latest_total: number | null
  threshold: number | null
  consecutive_passes: number
  trend: 'improving' | 'stagnant' | 'declining'
}

export interface ParticipationSummary {
  human_messages: number
  ai_messages: number
  active_members: number
  total_members: number
}

export interface AIActivitySummary {
  total_interventions: number
  recent_interventions: number
  action_distribution: Record<string, number>
}

export interface AlertItem {
  level: 'error' | 'warning' | 'info'
  type: 'stage_stagnation' | 'low_participation' | 'ai_dominant'
  message: string
}

export interface ProjectMonitorItem {
  id: string
  name: string
  current_stage: DTStage
  status: ProjectStatus
  seat_summary: SeatSummary
  note_count: number
  last_activity: string | null
  created_at: string
  ai_contribution: AIContribution
  stage_duration_seconds: number
  stage_started_at: string | null
  evaluation_score: EvaluationScoreSummary
  participation: ParticipationSummary
  ai_activity: AIActivitySummary
  alerts: AlertItem[]
}

export interface StageDistribution {
  discover: number
  define: number
  develop: number
  deliver: number
  completed: number
}

export interface ProjectOverviewResponse {
  projects: ProjectMonitorItem[]
  stage_distribution: StageDistribution
}
