/**
 * Timer store — Spec 15 §6.
 *
 * 前端每秒本地遞減，後端 WS / REST 對齊 used_seconds。
 */

import { create } from 'zustand'

export interface TimerStateSnapshot {
  current_sub_phase: string | null
  budget_seconds: number
  used_seconds: number
  paused: boolean
  used_pct: number // 0..100
  available: boolean
}

export interface TimerConfig {
  total_session_minutes: number
  macro_budgets: Record<string, number>
  sub_phase_overrides: Record<string, number>
  warning_thresholds_pct: number[]
  auto_advance_on_timeout: boolean
  allow_overrun: boolean
  preset_id: string
}

interface TimerStore {
  snapshot: TimerStateSnapshot
  config: TimerConfig | null
  setSnapshot: (s: Partial<TimerStateSnapshot>) => void
  setConfig: (c: TimerConfig | null) => void
  tick: () => void // 每秒呼叫
}

const initialSnapshot: TimerStateSnapshot = {
  current_sub_phase: null,
  budget_seconds: 0,
  used_seconds: 0,
  paused: false,
  used_pct: 0,
  available: false,
}

export const useTimerStore = create<TimerStore>((set) => ({
  snapshot: initialSnapshot,
  config: null,
  setSnapshot: (s) =>
    set((state) => ({ snapshot: { ...state.snapshot, ...s } })),
  setConfig: (c) => set({ config: c }),
  tick: () =>
    set((state) => {
      const s = state.snapshot
      if (!s.available || s.paused || !s.current_sub_phase) return state
      const used = s.used_seconds + 1
      const pct = s.budget_seconds > 0 ? (used / s.budget_seconds) * 100 : 0
      return { snapshot: { ...s, used_seconds: used, used_pct: pct } }
    }),
}))

export function getTimerColor(usedPct: number): 'green' | 'yellow' | 'red' | 'overtime' {
  if (usedPct >= 100) return 'overtime'
  if (usedPct >= 80) return 'red'
  if (usedPct >= 50) return 'yellow'
  return 'green'
}

export function formatRemaining(budget: number, used: number): string {
  const remaining = Math.max(0, budget - used)
  const m = Math.floor(remaining / 60)
  const s = Math.floor(remaining % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

export function formatBudget(budget: number): string {
  const m = Math.floor(budget / 60)
  const s = Math.floor(budget % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}
