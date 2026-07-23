import type {
  DTStage,
  MicroPhaseId,
  SeatRole,
  OccupantType,
  TurnPolicy,
  TurnAllowedAction,
} from './models'

// ── WebSocket message types ───────────────────────────────────────────────

export type WSMessageType =
  | 'chat_message'
  | 'typing_indicator'
  | 'stage_changed'
  | 'seat_changed'
  | 'system_message'
  | 'ping'
  | 'project_update'
  | 'micro_phase_changed'
  | 'timer_state'
  | 'timer_warning'
  | 'timer_timeout'
  // Phase 28 — Turn-Taking Controller events
  | 'turn_policy_changed'
  | 'cue'
  | 'turn_state'
  | 'cue_timeout'       // B4: 單次 timeout（可能即將 retry）
  | 'cue_abandoned'     // B4: 達 retry 上限，supervisor 完全放棄
  // Phase 42 A2/A3 — 回合鎖 + 真人不迷失 UX（spec 06 §3.1）
  | 'waiting_for_human' // 回合鎖凍結：等待真人輸入
  | 'input_bounced'     // 實質檢核退回提示
  | 'user_task'         // 「你的任務」釘住 banner
  | 'note_highlight'    // 便條指認高亮
  | 'agent_typing'      // D2/WP9 #9：AI 發話/白板動作前置 typing 指示
  // Phase 42 D5 — LLM fail-stop 全房暫停／恢復（spec 20 §13.3/§13.4）
  | 'room_paused'
  | 'room_resumed'

export interface WSChatMessagePayload {
  id?: string
  sender_id: string
  sender_type: 'human' | 'ai' | 'system'
  sender_name: string
  content: string
  stage?: DTStage
  timestamp: string
  /** chat_id：`${project_id}:group` | `${project_id}:personal:${user_id}`，缺省視為 group。 */
  chat_id?: string
}

export interface WSTypingPayload {
  user_name: string
  is_typing: boolean
}

/** D2/WP9 #9（spec 06 §3.1）：AI 發話/白板動作前置 typing 指示（僅群組 channel）。 */
export interface WSAgentTypingPayload {
  project_id: string
  seat_id: string
  display_name: string
  kind: 'chat' | 'canvas'
  state: 'start' | 'stop'
  timestamp: string
}

export interface WSStageChangedPayload {
  from: DTStage
  to: DTStage
  triggered_by: string
  timestamp: string
}

export interface WSSeatChangedPayload {
  seat_role: SeatRole
  previous: {
    occupant_type: OccupantType
    display_name?: string
  }
  current: {
    occupant_type: OccupantType
    display_name?: string
    user_id?: string
    agent_id?: string
  }
  timestamp: string
}

export interface WSSystemMessagePayload {
  content: string
  level: 'info' | 'warning' | 'error'
}

export interface WSProjectUpdatePayload {
  project_id: string
  current_stage: DTStage
  note_count: number
  human_count: number
  last_activity: string
}

export interface WSMicroPhaseChangedPayload {
  from_phase: MicroPhaseId
  to_phase: MicroPhaseId
  transition_type: 'advance' | 'backtrack'
  triggered_by: string
  timestamp: string
}

// ：每 10s tick + threshold + timeout 三類 timer 事件。
export interface WSTimerStatePayload {
  project_id: string
  current_sub_phase: string | null
  /** 學生友善階段名（後端去掉「講義第N步」等內部代號後送出）。 */
  current_sub_phase_label?: string | null
  budget_seconds: number
  used_seconds: number
  paused: boolean
  used_pct: number
  /** 本關時間上限——budget_seconds 的明確化別名（spec 16 v2.0 §4.5）。 */
  sub_phase_budget_seconds?: number
  /** 本關已用秒數——used_seconds 的明確化別名（spec 16 v2.0 §4.5）。 */
  sub_phase_used_seconds?: number
  /** 暖場期間的團隊目標張數（後端依 intensity 計算下發）；非暖場為 null。 */
  warmup_goal?: number | null
  /** 暖場軟目標秒數（固定 180／3 分，spec 28 §3.1）；非暖場為 null。 */
  warmup_soft_seconds?: number | null
}

export interface WSTimerWarningPayload {
  project_id: string
  threshold_pct: number
  current_sub_phase: string
  used_seconds: number
  budget_seconds: number
}

export interface WSTimerTimeoutPayload {
  project_id: string
  current_sub_phase: string
}

// Phase 28 — Turn-Taking Controller payloads

export interface WSTurnPolicyChangedPayload {
  policy: TurnPolicy
  changed_by: string
  timestamp: string
}

export interface WSCuePayload {
  target_seat_id: SeatRole
  from_seat_id: SeatRole
  timestamp: string
}

export interface WSTurnStatePayload {
  policy: TurnPolicy
  next_speaker: SeatRole | null
  allowed_actions: TurnAllowedAction[]
  /**
   * 發布者標記（spec 06 v4.28，Phase 42 補正 R4／A-P2）：'round_lock'＝回合鎖
   * 解鎖/清除；'policy'＝輪替政策層。等待列只認 round_lock 來源清除；
   * 舊後端缺欄位時視為 policy（不清）。
   */
  source?: 'round_lock' | 'policy'
  timestamp: string
}

// B4 events
export interface WSCueTimeoutPayload {
  target_seat_role: SeatRole
  from_seat_role: SeatRole
  timeout_seconds: number
  retry_count: number
  max_retries: number
  will_retry: boolean
  timestamp: string
}

export interface WSCueAbandonedPayload {
  target_seat_role: SeatRole
  from_seat_role: SeatRole
  total_attempts: number
  elapsed_seconds: number
  cooldown_seconds: number
  timestamp: string
}

// Phase 42 A2/A3 — 回合鎖 + 真人不迷失 UX payloads（spec 06 §3.1）

export type UserTaskActionKind = 'chat' | 'note' | 'move' | 'confirm'

export interface WSWaitingForHumanPayload {
  project_id: string
  sub_phase: string
  /** 本 sub-phase 內第幾回合（從 1 起算）。 */
  round: number
  /** 解鎖所需輸入型態旗標＋組合語意：all=全部都要、any=擇一。 */
  required: {
    note: boolean
    chat: boolean
    move: boolean
    confirm: boolean
    mode: 'all' | 'any'
  }
  target_user_id: string
  timestamp: string
}

export interface WSInputBouncedPayload {
  project_id: string
  user_id: string
  /** 退回原因（內容層中文白話）。 */
  reason_zh: string
  /** 教練式提示：「怎樣才算」＋例子。 */
  hint_zh: string
  timestamp: string
}

export interface WSUserTaskPayload {
  project_id: string
  /** 單一最小動作；null＝清除 banner。 */
  task_text: string | null
  sub_phase: string
  action_kind: UserTaskActionKind
  /** 任務相關便條 id（前端據此連動高亮）；可缺省。 */
  anchor_note_ids?: string[] | null
  timestamp: string
}

export interface WSNoteHighlightPayload {
  project_id: string
  note_ids: string[]
  by_seat: string
  /** 高亮持續秒數，到期前端自動解除。 */
  ttl: number
  timestamp: string
}

// Phase 42 D5 — LLM fail-stop 全房暫停／恢復 payloads（spec 20 §13.3/§13.4）
// Phase 43 — 新增 "awaiting_human"（人離席/未回應的全房休眠，spec 20 §3/§11.7）

export type RoomPauseReason = 'llm_down' | 'teacher' | 'awaiting_human'

export interface WSRoomPausedPayload {
  project_id: string
  /**
   * "llm_down"＝AI 服務中斷 fail-stop；"teacher"＝老師手動；
   * "awaiting_human"＝你離席/被點名未回應的全房休眠（回來自動解凍）。
   */
  reason: RoomPauseReason
  timestamp: string
}

export interface WSRoomResumedPayload {
  project_id: string
  timestamp: string
}

export type WSPayload =
  | WSChatMessagePayload
  | WSTypingPayload
  | WSStageChangedPayload
  | WSSeatChangedPayload
  | WSSystemMessagePayload
  | WSProjectUpdatePayload
  | WSMicroPhaseChangedPayload
  | WSTimerStatePayload
  | WSTimerWarningPayload
  | WSTimerTimeoutPayload
  | WSTurnPolicyChangedPayload
  | WSCuePayload
  | WSTurnStatePayload
  | WSCueTimeoutPayload
  | WSCueAbandonedPayload
  | WSWaitingForHumanPayload
  | WSInputBouncedPayload
  | WSUserTaskPayload
  | WSNoteHighlightPayload
  | WSRoomPausedPayload
  | WSRoomResumedPayload
  | Record<string, never>

export interface WSMessage {
  type: WSMessageType
  payload: WSPayload
}

// Client → Server messages
export interface WSSendChatMessage {
  type: 'chat_message'
  /** chat_id 缺省時，後端 default 視為 `${project_id}:group`。 */
  payload: { content: string; chat_id?: string }
}

export interface WSSendTypingStart {
  type: 'typing_start'
  payload: Record<string, never>
}

export interface WSSendTypingStop {
  type: 'typing_stop'
  payload: Record<string, never>
}

/** Phase 28：學生在前端按 Pass / Raise-Hand 時送出。 */
export interface WSSendAgentAction {
  type: 'agent_action'
  payload: {
    action: 'pass' | 'raise_hand'
    seat_role: SeatRole
  }
}

export type WSClientMessage =
  | WSSendChatMessage
  | WSSendTypingStart
  | WSSendTypingStop
  | WSSendAgentAction
