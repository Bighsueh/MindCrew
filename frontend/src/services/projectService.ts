import api, { getAccessToken } from './api'
import type {
  CreateProjectRequest,
  GeneratePersonasRequest,
  GeneratePersonasResponse,
  JoinProjectRequest,
  JoinProjectResponse,
  AdvanceStageRequest,
  AdvanceStageResponse,
  MessagesResponse,
  UpdateSeatPersonaRequest,
} from '../types/api'
import type {
  CrewSeatRole,
  Persona,
  Project,
  ProjectListItem,
  Seat,
  StageInfo,
  StageHistoryEntry,
  MicroPhaseHistoryEntry,
  AgentTrace,
  CanvasStateResponse,
  ProjectSummaryResponse,
} from '../types/models'

export async function createProject(data: CreateProjectRequest): Promise<Project> {
  const response = await api.post<Project>('/projects', data)
  return response.data
}

// specs/16-timer-system.md：舊專案啟用 timer 的 lazy bootstrap。
export async function initProjectTimer(
  projectId: string,
  config?: import('./../types/api').TimerConfigInput,
): Promise<void> {
  await api.post(`/projects/${projectId}/timer/init`, { config })
}

// Spec 13: 強制送出便條（人類限定）
export interface CreateNoteForceResponse {
  success: boolean
  note_id?: string
  zone_id?: string
  gate_violation?: Record<string, unknown>
  rejection?: {
    reason_zh: string
    rule_module: string
    rule_name: string
    matched_text?: string
  }
}

export async function createNoteForcePublish(
  projectId: string,
  payload: {
    text: string
    color: string
    x: number
    y: number
    sub_phase_id: string
  },
): Promise<CreateNoteForceResponse> {
  const response = await api.post<CreateNoteForceResponse>(
    `/projects/${projectId}/canvas/notes`,
    { ...payload, force_publish: true },
  )
  return response.data
}

export async function listProjects(): Promise<ProjectListItem[]> {
  const response = await api.get<ProjectListItem[]>('/projects')
  return response.data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}`)
}

export async function getProject(id: string): Promise<Project> {
  const response = await api.get<Project>(`/projects/${id}`)
  return response.data
}

export async function joinProject(
  id: string,
  data: JoinProjectRequest,
): Promise<JoinProjectResponse> {
  const response = await api.post<JoinProjectResponse>(`/projects/${id}/join`, data)
  return response.data
}

export async function leaveProject(id: string): Promise<void> {
  await api.post(`/projects/${id}/leave`)
}

export async function getStage(id: string): Promise<StageInfo> {
  const response = await api.get<StageInfo>(`/projects/${id}/stage`)
  return response.data
}

export async function advanceStage(
  id: string,
  data: AdvanceStageRequest,
): Promise<AdvanceStageResponse> {
  const response = await api.post<AdvanceStageResponse>(`/projects/${id}/advance-stage`, data)
  return response.data
}

export async function getStageHistory(id: string): Promise<StageHistoryEntry[]> {
  const response = await api.get<StageHistoryEntry[]>(`/projects/${id}/history`)
  return response.data
}

export interface GetMessagesOptions {
  limit?: number
  before?: string
  /** 指定要載入的 chat_id；缺省時後端視為 `${id}:group`。 */
  chatId?: string
}

export async function getMessages(
  id: string,
  options: GetMessagesOptions = {},
): Promise<MessagesResponse> {
  const { limit = 50, before, chatId } = options
  const params: Record<string, string | number> = { limit }
  if (before) params.before = before
  if (chatId) params.chat_id = chatId
  const response = await api.get<MessagesResponse>(`/projects/${id}/messages`, { params })
  return response.data
}

export async function getCanvasState(id: string): Promise<CanvasStateResponse> {
  const response = await api.get<CanvasStateResponse>(`/projects/${id}/canvas-state`)
  return response.data
}

export async function getProjectSummary(id: string): Promise<ProjectSummaryResponse> {
  const response = await api.post<ProjectSummaryResponse>(`/projects/${id}/summary`)
  return response.data
}

export async function getMicroPhaseHistory(projectId: string): Promise<MicroPhaseHistoryEntry[]> {
  const response = await api.get<MicroPhaseHistoryEntry[]>(`/projects/${projectId}/micro-phase-history`)
  return response.data
}

export async function getAgentTraces(
  id: string,
  agentId?: string,
  limit = 20,
): Promise<{ traces: AgentTrace[]; has_more: boolean }> {
  const params: Record<string, string | number> = { limit }
  if (agentId) params.agent_id = agentId
  const response = await api.get<{ traces: AgentTrace[]; has_more: boolean }>(
    `/projects/${id}/agent-traces`,
    { params },
  )
  return response.data
}

// ── Persona system (Phase 19) ────────────────────────────────────────────

export async function generatePersonas(
  data: GeneratePersonasRequest,
): Promise<Persona[]> {
  const response = await api.post<GeneratePersonasResponse>(
    '/personas/generate',
    data,
  )
  return response.data.personas
}

// ── Streaming variant (spec §17.3.1.2) ────────────────────────────────

export type PersonaStreamEvent =
  | {
      type: 'stage'
      stage: 'stakeholder_mapping' | 'persona_instantiation'
      status: 'start' | 'done'
      category_count?: number
    }
  | { type: 'persona'; index: number; persona: Persona }
  | { type: 'done'; count: number }
  | { type: 'error'; detail: string }

interface StreamOptions {
  signal?: AbortSignal
  onEvent: (event: PersonaStreamEvent) => void
}

export async function generatePersonasStream(
  data: GeneratePersonasRequest,
  { signal, onEvent }: StreamOptions,
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch('/api/personas/generate/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`SSE 連線失敗（HTTP ${response.status}）`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE frames are separated by a blank line.
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        sep = buffer.indexOf('\n\n')
        const parsed = parseSseFrame(frame)
        if (parsed) onEvent(parsed)
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseSseFrame(frame: string): PersonaStreamEvent | null {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return null
  }
  return { type: eventName, ...payload } as PersonaStreamEvent
}

export async function updateSeatPersona(
  projectId: string,
  seatRole: CrewSeatRole,
  persona: Persona,
): Promise<Seat> {
  const body: UpdateSeatPersonaRequest = { persona }
  const response = await api.patch<Seat>(
    `/projects/${projectId}/seats/${seatRole}/persona`,
    body,
  )
  return response.data
}
