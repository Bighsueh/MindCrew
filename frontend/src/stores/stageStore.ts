import { create } from 'zustand'
import type { DTStage, MicroPhaseId, StageHistoryEntry } from '../types/models'

interface StageState {
  currentStage: DTStage
  currentMicroPhase: MicroPhaseId | null
  startedAt: string | null
  durationSeconds: number
  stageHistory: StageHistoryEntry[]
  isLoading: boolean

  setCurrentStage: (stage: DTStage, startedAt?: string) => void
  setCurrentMicroPhase: (phase: MicroPhaseId) => void
  setStageHistory: (history: StageHistoryEntry[]) => void
  addHistoryEntry: (entry: StageHistoryEntry) => void
  setLoading: (loading: boolean) => void
}

export const useStageStore = create<StageState>((set) => ({
  currentStage: 'discover',
  currentMicroPhase: null,
  startedAt: null,
  durationSeconds: 0,
  stageHistory: [],
  isLoading: false,

  setCurrentStage: (stage: DTStage, startedAt?: string) => {
    set({ currentStage: stage, startedAt: startedAt ?? null })
  },

  setCurrentMicroPhase: (phase: MicroPhaseId) => {
    set({ currentMicroPhase: phase })
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
