import { create } from 'zustand'
import { getProjectSummary } from '../services/projectService'
import type { ProjectSummaryResponse } from '../types/models'

interface LobbyState {
  summary: ProjectSummaryResponse | null
  isSummaryLoading: boolean
  summaryError: string | null

  fetchSummary: (projectId: string) => Promise<void>
  clearSummary: () => void
}

export const useLobbyStore = create<LobbyState>((set) => ({
  summary: null,
  isSummaryLoading: false,
  summaryError: null,

  fetchSummary: async (projectId: string) => {
    set({ isSummaryLoading: true, summaryError: null })
    try {
      const summary = await getProjectSummary(projectId)
      set({ summary, isSummaryLoading: false })
    } catch {
      set({
        summaryError: '產生摘要失敗，請稍後再試。',
        isSummaryLoading: false,
      })
    }
  },

  clearSummary: () => set({ summary: null, summaryError: null }),
}))
