import { create } from 'zustand'
import type { DTStage, StageHistoryEntry } from '../types/models'

interface StageState {
  currentStage: DTStage
  startedAt: string | null
  durationSeconds: number
  stageHistory: StageHistoryEntry[]
  isLoading: boolean

  setCurrentStage: (stage: DTStage, startedAt?: string) => void
  setStageHistory: (history: StageHistoryEntry[]) => void
  addHistoryEntry: (entry: StageHistoryEntry) => void
  setLoading: (loading: boolean) => void
}

export const useStageStore = create<StageState>((set) => ({
  currentStage: 'discover',
  startedAt: null,
  durationSeconds: 0,
  stageHistory: [],
  isLoading: false,

  setCurrentStage: (stage: DTStage, startedAt?: string) => {
    set({ currentStage: stage, startedAt: startedAt ?? null })
  },

  setStageHistory: (history: StageHistoryEntry[]) => {
    set({ stageHistory: history })
  },

  addHistoryEntry: (entry: StageHistoryEntry) => {
    set((state) => ({ stageHistory: [...state.stageHistory, entry] }))
  },

  setLoading: (loading: boolean) => {
    set({ isLoading: loading })
  },
}))
