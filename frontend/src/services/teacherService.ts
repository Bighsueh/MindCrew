import api from './api'
import type { CreateStudentRequest, UpdateStudentPermissionRequest, SendHintRequest, SendHintResponse } from '../types/api'
import type { User, TeacherProjectSummary, ProjectRecord, ProjectOverviewResponse } from '../types/models'

export async function createStudent(data: CreateStudentRequest): Promise<User> {
  const response = await api.post<User>('/teacher/students', data)
  return response.data
}

export async function listStudents(): Promise<User[]> {
  const response = await api.get<User[]>('/teacher/students')
  return response.data
}

export async function updateStudentPermission(
  id: string,
  data: UpdateStudentPermissionRequest,
): Promise<User> {
  const response = await api.patch<User>(`/teacher/students/${id}`, data)
  return response.data
}

export async function getTeacherProjects(): Promise<TeacherProjectSummary[]> {
  const response = await api.get<TeacherProjectSummary[]>('/teacher/projects')
  return response.data
}

export async function getProjectRecord(id: string): Promise<ProjectRecord> {
  const response = await api.get<ProjectRecord>(`/teacher/projects/${id}/record`)
  return response.data
}

export async function getProjectsOverview(): Promise<ProjectOverviewResponse> {
  const response = await api.get<ProjectOverviewResponse>('/teacher/projects/overview')
  return response.data
}

export async function sendHint(projectId: string, data: SendHintRequest): Promise<SendHintResponse> {
  const response = await api.post<SendHintResponse>(`/teacher/projects/${projectId}/send-hint`, data)
  return response.data
}

export async function updateAIContribution(projectId: string, level: string): Promise<void> {
  await api.patch(`/projects/${projectId}`, { ai_contribution: level })
}
