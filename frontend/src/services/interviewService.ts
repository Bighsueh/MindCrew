import { isAxiosError } from 'axios'
import api from './api'

export interface Stakeholder {
  id: string
  name: string
  description: string
}

export interface InterviewScenario {
  kind: 'preset' | 'custom' | 'teacher'
  title: string
  description: string
}

export interface ScenarioSummary extends InterviewScenario {
  id: string
  synthetic: boolean
  profiles: Stakeholder[]
  generation_state: 'pending' | 'generating' | 'ready' | 'failed'
  generation_error: string | null
  published: boolean
  mine: boolean
}

export interface Guide {
  id: string
  title: string
  body: string
  created_at: string
}

export interface ScenarioWorkspaceData {
  note: InterviewNote
  current_guide_id: string | null
  guides: Guide[]
}

export interface InterviewSummary {
  id: string
  stakeholder_id: string
  scenario_id: string | null
  started_at: string
  ended_at: string | null
  scenario: InterviewScenario
  stakeholder: Stakeholder
}

export interface Exchange {
  id: string
  request_id: string
  sequence: number
  question: string
  asked_at: string
  status: 'waiting' | 'failed' | 'skipped' | 'answered'
  answer: string | null
  answered_at: string | null
  error: string | null
  retryable: boolean
  retry_after_seconds?: number
}

export interface Interview extends InterviewSummary {
  exchanges: Exchange[]
  remaining_questions: number
}

export interface InterviewNote {
  body: string
  updated_at: string | null
}

export interface SourceRef {
  session_id: string
  sequence: number
  speaker: 'student' | 'stakeholder'
}

export interface PersonaField {
  field_id: string
  label: string
  type: 'short' | 'long' | 'list'
  value: string | string[]
  source_refs: SourceRef[]
}

export interface PersonaDraft {
  title: string
  fields: PersonaField[]
}

export interface SavedPersona extends PersonaDraft {
  id: string
  updated_at: string
}

export interface PersonaCatalog {
  personas: Pick<SavedPersona, 'id' | 'title' | 'updated_at'>[]
  groups: { id: string; label: string; fields: PersonaField[] }[]
}

const sessions = '/interview/sessions'
const personas = '/interview/personas'
const scenarios = '/interview/scenarios'
const generationOptions = { timeout: 55000 }

export function interviewRequestId(): string {
  // getRandomValues is also available when MindCrew is served over HTTP.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}

export const interviewService = {
  async scenarios(signal: AbortSignal) {
    return (await api.get<ScenarioSummary[]>(scenarios, { signal })).data
  },
  async scenario(id: string, signal: AbortSignal) {
    return (await api.get<ScenarioSummary>(`${scenarios}/${id}`, { signal })).data
  },
  async createScenario(body: object, importing: boolean) {
    return (await api.post<ScenarioSummary>(importing ? `${scenarios}/import` : scenarios, body)).data
  },
  async generateProfiles(id: string) {
    return (await api.post<ScenarioSummary>(`${scenarios}/${id}/generate`, null, generationOptions)).data
  },
  async publishScenario(id: string, student_emails: string[]) {
    return (await api.post<ScenarioSummary>(`${scenarios}/${id}/publish`, { student_emails })).data
  },
  async workspace(id: string, signal: AbortSignal) {
    return (await api.get<ScenarioWorkspaceData>(`${scenarios}/${id}/workspace`, { signal })).data
  },
  async saveScenarioNote(id: string, body: string) {
    return (await api.put<InterviewNote>(`${scenarios}/${id}/note`, { body })).data
  },
  async saveGuide(id: string, title: string, body: string) {
    return (await api.post<Guide>(`${scenarios}/${id}/guides`, { title, body })).data
  },
  async selectGuide(id: string, guide_id: string | null) {
    return (await api.put(`${scenarios}/${id}/current-guide`, { guide_id })).data
  },
  async sessions(signal: AbortSignal) {
    return (await api.get<InterviewSummary[]>(sessions, { signal })).data
  },
  async start(stakeholder_id: string, scenario_id: string) {
    return (await api.post<Interview>(sessions, { stakeholder_id, scenario_id })).data
  },
  async get(id: string, signal?: AbortSignal) {
    return (await api.get<Interview>(`${sessions}/${id}`, { signal })).data
  },
  async ask(id: string, question: string, request_id: string) {
    return (await api.post<Exchange>(`${sessions}/${id}/questions`, { question, request_id }, generationOptions)).data
  },
  async resolve(id: string, sequence: number, action: 'retry' | 'skip') {
    return (await api.post<Exchange>(`${sessions}/${id}/questions/${sequence}/resolve`, { action }, generationOptions)).data
  },
  async end(id: string) {
    return (await api.post<Interview>(`${sessions}/${id}/end`)).data
  },
  async note(id: string, signal: AbortSignal) {
    return (await api.get<InterviewNote>(`${sessions}/${id}/note`, { signal })).data
  },
  async saveNote(id: string, body: string) {
    return (await api.put<InterviewNote>(`${sessions}/${id}/note`, { body })).data
  },
  async personas(signal: AbortSignal) {
    return (await api.get<PersonaCatalog>(personas, { signal })).data
  },
  async persona(id: string) {
    return (await api.get<SavedPersona>(`${personas}/${id}`)).data
  },
  async savePersona(draft: PersonaDraft, id?: string) {
    return (id
      ? await api.put<SavedPersona>(`${personas}/${id}`, draft)
      : await api.post<SavedPersona>(personas, draft)).data
  },
  async transcript(id: string) {
    return (await api.get<string>(`${sessions}/${id}/transcript`, { responseType: 'text' })).data
  },
}

export function interviewError(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (typeof detail?.message === 'string') return detail.message
    if (error.response?.status === 422) return '欄位格式或長度不符，請確認後重送。'
  }
  return '暫時無法連線。請確認網路後再試一次。'
}
