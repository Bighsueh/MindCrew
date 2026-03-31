import type { DTStage, MicroPhaseId, SeatRole, OccupantType } from './models'

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

export interface WSChatMessagePayload {
  id?: string
  sender_id: string
  sender_type: 'human' | 'ai' | 'system'
  sender_name: string
  content: string
  stage?: DTStage
  timestamp: string
}

export interface WSTypingPayload {
  user_name: string
  is_typing: boolean
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
  from: MicroPhaseId
  to: MicroPhaseId
  transition_type: 'advance' | 'backtrack'
  triggered_by: string
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
  | Record<string, never>

export interface WSMessage {
  type: WSMessageType
  payload: WSPayload
}

// Client → Server messages
export interface WSSendChatMessage {
  type: 'chat_message'
  payload: { content: string }
}

export interface WSSendTypingStart {
  type: 'typing_start'
  payload: Record<string, never>
}

export interface WSSendTypingStop {
  type: 'typing_stop'
  payload: Record<string, never>
}

export type WSClientMessage = WSSendChatMessage | WSSendTypingStart | WSSendTypingStop
