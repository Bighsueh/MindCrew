import api from './api'
import type {
  CreateProjectRequest,
  JoinProjectRequest,
  JoinProjectResponse,
  AdvanceStageRequest,
  AdvanceStageResponse,
  MessagesResponse,
} from '../types/api'
import type {
  Project,
  ProjectListItem,
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

export async function getMessages(
  id: string,
  limit = 50,
  before?: string,
): Promise<MessagesResponse> {
  const params: Record<string, string | number> = { limit }
  if (before) params.before = before
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
