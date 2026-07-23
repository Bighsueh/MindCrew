/**
 * Timer store — Spec 15 §6.
 *
 * 前端每秒本地遞減，後端 WS / REST 對齊 used_seconds。
 */

import { create } from 'zustand'

export interface TimerStateSnapshot {
  current_sub_phase: string | null
  /** 學生友善階段名（去掉「講義第N步」等內部代號）；缺省時 fallback 回 current_sub_phase。 */
  current_sub_phase_label: string | null
  budget_seconds: number
  used_seconds: number
  paused: boolean
  used_pct: number // 0..100
  available: boolean
  /** 本關時間上限——budget_seconds 的明確化別名（spec 16 v2.0 §4.5）。 */
  sub_phase_budget_seconds?: number
  /** 本關已用秒數——used_seconds 的別名口徑；tick 與 used_seconds 同步推進（單一計時源）。 */
  sub_phase_used_seconds?: number
  /** 暖場期間的團隊目標張數（後端下發，前端不自行計算）；非暖場為 null。 */
  warmup_goal?: number | null
  /** 暖場軟目標秒數（固定 180／3 分，後端下發，spec 28 §3.1）；非暖場為 null。 */
  warmup_soft_seconds?: number | null
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

// 單調對齊容差（秒）：server 快照覆蓋時，同一 sub_phase 內小於此的「往回」視為
// 對齊抖動，壓住不讓倒數回跳；超過則視為真實漂移、完整採用 server 值。
const RECONCILE_BACKWARD_TOLERANCE = 5

const initialSnapshot: TimerStateSnapshot = {
  current_sub_phase: null,
  current_sub_phase_label: null,
  budget_seconds: 0,
  used_seconds: 0,
  paused: false,
  used_pct: 0,
  available: false,
  sub_phase_budget_seconds: 0,
  sub_phase_used_seconds: 0,
  warmup_goal: null,
  warmup_soft_seconds: null,
}

export const useTimerStore = create<TimerStore>((set) => ({
  snapshot: initialSnapshot,
  config: null,
  setSnapshot: (s) =>
    set((state) => {
      const prev = state.snapshot
      const next = { ...prev, ...s }
      // 單調對齊守衛（spec 16 §5/§4.18「本地遞減＋後端對齊」）：server 快照覆蓋時，
      // 若仍在同一 sub_phase、未翻轉 paused、且 used_seconds 只是小幅往回（對齊抖動），
      // 壓住不讓倒數回跳；sub_phase 改變／pause 翻轉／大幅漂移則完整採用 server 值。
      if (
        s.used_seconds != null &&
        next.current_sub_phase === prev.current_sub_phase &&
        next.paused === prev.paused &&
        !next.paused &&
        next.used_seconds < prev.used_seconds &&
        prev.used_seconds - next.used_seconds <= RECONCILE_BACKWARD_TOLERANCE
      ) {
        next.used_seconds = prev.used_seconds
        next.used_pct =
          next.budget_seconds > 0
            ? (prev.used_seconds / next.budget_seconds) * 100
            : next.used_pct
        if (next.sub_phase_used_seconds != null) {
          next.sub_phase_used_seconds = prev.used_seconds
        }
      }
      return { snapshot: next }
    }),
  setConfig: (c) => set({ config: c }),
  tick: () =>
    set((state) => {
      const s = state.snapshot
      if (!s.available || s.paused || !s.current_sub_phase) return state
      const used = s.used_seconds + 1
      const pct = s.budget_seconds > 0 ? (used / s.budget_seconds) * 100 : 0
      return {
        snapshot: {
          ...s,
          used_seconds: used,
          used_pct: pct,
          // sub_phase_used_seconds 是 used_seconds 的別名口徑：跟著同一計時源走，
          // 不另起計時器（避免雙計時漂移與顯示跳動）。
          sub_phase_used_seconds: s.sub_phase_used_seconds != null ? used : undefined,
        },
      }
    }),
}))

export function getTimerColor(usedPct: number): 'green' | 'yellow' | 'red' | 'overtime' {
  if (usedPct >= 100) return 'overtime'
  if (usedPct >= 80) return 'red'
  if (usedPct >= 50) return 'yellow'
  return 'green'
}

// ：對齊後端 PressureLevel 五階。
export type PressureLevel = 'calm' | 'halfway' | 'two_thirds' | 'tight' | 'critical'

export function getPressureLevel(usedPct: number): PressureLevel {
  if (usedPct >= 90) return 'critical'
  if (usedPct >= 75) return 'tight'
  if (usedPct >= 67) return 'two_thirds'
  if (usedPct >= 50) return 'halfway'
  return 'calm'
}

export function getPressureLabel(level: PressureLevel): string {
  return { calm: '充裕', halfway: '過半', two_thirds: '剩 1/3', tight: '剩 1/4', critical: '臨界' }[level]
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
