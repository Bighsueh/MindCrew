// ── Domain model types ──────────────────────────────────────────────────────

export type UserRole = 'teacher' | 'student' | 'admin'
export type AIContribution = 'low' | 'medium' | 'high'
// 暖場(warmup)為第一級 macro stage(Alternative Uses 破冰遊戲);navbar 顯示三階段。
export type DTStage = 'warmup' | 'discover' | 'define' | 'completed'

/** Phase 28：可切換的三模式輪流規則。詳 ``。 */
export type TurnPolicy = 'cued' | 'round_robin' | 'open_floor'

/** 對應後端 `TurnDecision.allowed_actions` 的子集。 */
export type TurnAllowedAction = 'speak' | 'pass' | 'handoff' | 'raise_hand'

// Phase 42 C1（spec 22 v2.0 §2.3a）：新 6 桶；舊 1.3（Persona）隨格移除。
export type MicroPhaseId =
  | "0.0"
  | "1.1" | "1.2"
  | "2.1" | "2.2" | "2.3"

export interface MicroPhaseInfo {
  current_micro_phase: MicroPhaseId
  micro_phase_name: string
  protagonist: string | null
  suppressed: string[]
}

export interface MicroPhaseHistoryEntry {
  id: string
  project_id: string
  from_micro_phase: MicroPhaseId
  to_micro_phase: MicroPhaseId
  transition_type: 'advance' | 'backtrack'
  triggered_by: string
  reason?: string
  duration_seconds?: number
  created_at: string
}
export type ProjectStatus = 'active' | 'completed' | 'archived'
// human_creator：真人專屬席（額外 +1，綁定 creator）。crew_* 永遠是常駐 AI。
export type SeatRole =
  | 'supervisor'
  | 'human_creator'
  | 'crew_1'
  | 'crew_2'
  | 'crew_3'
  | 'crew_4'
export type CrewSeatRole = Exclude<SeatRole, 'supervisor' | 'human_creator'>
export type OccupantType = 'human' | 'ai'
export type SenderType = 'human' | 'ai' | 'system'

// ── Persona system (Phase 19) ──────────────────────────────────────────────

export type PersonalityAxis = 'contrarian' | 'balanced' | 'supportive'

export interface LensAffinities {
  empathy: number
  structure: number
  creativity: number
  feasibility: number
}

export interface Persona {
  name: string
  role: string
  expertise: string
  personality_axis: PersonalityAxis
  personality_desc: string
  backstory: string
  lens_affinities: LensAffinities
}

export interface CrewPersonaAssignment {
  seat_role: CrewSeatRole
  persona: Persona
}

export interface User {
  id: string
  email: string
  display_name: string
  role: UserRole
  can_create_project: boolean
  /** Phase 22: 教師簽名碼（學生用此碼將活動列管於該教師）。 */
  signature_code?: string | null
  created_at?: string
}

export interface LinkedTeacher {
  id: string
  display_name: string
}

export interface Seat {
  id: string
  project_id: string
  seat_role: SeatRole
  occupant_type: OccupantType
  user_id?: string | null
  agent_id?: string | null
  display_name?: string
  persona?: Persona | null
  state: string
  // Phase 21：第一位真人入座前，AI 席位為 dormant（is_active=false）→ 顯示「待加入」。
  is_active?: boolean
  /** Phase 22: 席位識別色（tldraw 8 色 token），用於聊天氣泡與便利貼預設色。 */
  sticky_color?: string | null
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
  constraints?: string
  /** Phase 27：建立時使用者勾選的利害關係人（舊 project 為 []）。 */
  stakeholders?: Stakeholder[]
  /** Phase 27：'open' = Open Brief 流程；'legacy' = Phase 27 前資料。 */
  task_brief_kind?: 'open' | 'legacy'
  creator_id: string
  current_stage: DTStage
  current_micro_phase?: MicroPhaseId
  ai_contribution: AIContribution
  status: ProjectStatus
  seats?: Seat[]
  seat_summary?: SeatSummary
  created_at: string
  updated_at: string
  /** Phase 22: 活動邀請碼（教師可用此碼列管活動）。 */
  invite_code?: string | null
  /** Phase 22: 已列管的老師（null 表未列管）。 */
  linked_teacher?: LinkedTeacher | null
  /** Phase 28: 目前的輪流規則（cued / round_robin / open_floor）。 */
  turn_policy?: TurnPolicy
  /** 當前 viewer 對此專案的角色：'creator'（可入座）/ 'observer'（列管老師・admin，只能旁觀）/ null（無權）。 */
  viewer_role?: ViewerRole | null
}

export type ViewerRole = 'creator' | 'observer'

/** Phase 27：使用者建立 project 時勾選的利害關係人（持久化到 project.stakeholders）。 */
export interface Stakeholder {
  id: string
  name: string
  role: string
  relevance: string
  selected?: boolean
}

/** Phase 27：AI 在 Step 2 列出的具體候選利害關係人（供 StakeholderPicker 勾選）。 */
export interface StakeholderSuggestion {
  id: string
  name: string
  role: string
  relevance: string
}

/** Phase 27：AI 在 Step 1 建議的限制條件（chip 形式採納，不可預勾）。 */
export interface ConstraintSuggestions {
  budget_hints: string[]
  audience_hints: string[]
  venue_hints: string[]
  other_hints: string[]
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
  /** Phase 22 */
  invite_code?: string | null
  linked_teacher?: LinkedTeacher | null
  /** Phase 28 */
  turn_policy?: TurnPolicy
}

/** Phase 28：當前回合狀態 (由 WS turn_state event 推送)。 */
export interface TurnState {
  policy: TurnPolicy
  next_speaker: SeatRole | null
  allowed_actions: TurnAllowedAction[]
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
  /** chat_id: `${project_id}:group` 或 `${project_id}:personal:${user_id}`，NULL 視為 group。 */
  chat_id?: string
  /** 純前端：樂觀送出、尚未被 server echo 對帳的暫態訊息（reconcile 後清除）。後端不會帶此欄。 */
  pending?: boolean
}

export interface StageInfo {
  current_stage: DTStage
  current_micro_phase?: MicroPhaseId
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
  /** Phase 28：當前輪流規則（後端 admin/overview endpoint 補欄位後生效）。 */
  turn_policy?: TurnPolicy
}

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
export interface StageDistribution {
  discover: number
  define: number
  completed: number
}

// Phase 34 (spec/26-first-diamond-closing.md): 第一鑽石終局產出。
// 由 backend closing ritual 寫入 project.first_diamond_output。
export interface FirstDiamondOutput {
  personas?: Array<{
    name: string
    fields?: Record<string, string>
    completeness?: number
  }>
  chosen_problem_statement?: string | null
  chosen_hmw?: string | null
  completed_at?: string
  summary?: string
}

export interface ProjectOverviewResponse {
  projects: ProjectMonitorItem[]
  stage_distribution: StageDistribution
}
