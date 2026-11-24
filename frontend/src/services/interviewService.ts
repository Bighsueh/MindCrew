import { isAxiosError } from 'axios'
import api from './api'

export interface Stakeholder {
  id: string
  name: string
  description: string
}

interface Scenario {
  scenario: string
  synthetic: boolean
  max_question_chars: number
  stakeholders: Stakeholder[]
}

export interface InterviewSummary {
  id: string
  stakeholder_id: string
  started_at: string
  ended_at: string | null
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
}

export interface Interview extends InterviewSummary {
  exchanges: Exchange[]
  remaining_questions: number
}

const sessions = '/interview/sessions'
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
  async scenario(signal: AbortSignal) {
    return (await api.get<Scenario>('/interview/stakeholders', { signal })).data
  },
  async sessions(signal: AbortSignal) {
    return (await api.get<InterviewSummary[]>(sessions, { signal })).data
  },
  async start(stakeholder_id: string) {
    return (await api.post<Interview>(sessions, { stakeholder_id })).data
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
  async transcript(id: string) {
    return (await api.get<string>(`${sessions}/${id}/transcript`, { responseType: 'text' })).data
  },
}

export function interviewError(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (typeof detail?.message === 'string') return detail.message
    if (error.response?.status === 422) return '問題格式或長度不符，請確認後重送。'
  }
  return '暫時無法連線。請確認網路後再試一次。'
}
