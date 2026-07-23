import { create } from 'zustand'
import type { SeatRole } from '../types/models'

/**
 * Phase 28 F1/F3: 維護「目前哪個席位正被 cue / 是否已超時」狀態。
 *
 * - `activeCueSeat` = 正被 cue 的席位（cue event 觸發時 set；on_speak / pass /
 *   cue_abandoned 時 clear）。觀察者 SeatChip 用此繪黃框。
 * - `timedOutSeats` = 單次 timeout 後短暫高亮（紅框 5s）的 seat set。
 *   `will_retry=True` 後 supervisor 會 re-cue → activeCueSeat 重新標示。
 * - `abandonedSeats` = abandon 後 30s 內紅框 + 「AI 接手」提示；自動 fade。
 */

export type CueStatus =
  | { kind: 'idle' }
  | { kind: 'pending'; seat: SeatRole; retryCount: number; maxRetries: number }
  | { kind: 'timed_out'; seat: SeatRole; retryCount: number; maxRetries: number; willRetry: boolean }
  | { kind: 'abandoned'; seat: SeatRole; totalAttempts: number }

interface CueState {
  status: CueStatus
  /** 上次 abandon 時間，前端用此判斷 30s 淡出。 */
  lastAbandonedAt: number | null
  setPending: (seat: SeatRole, retryCount?: number, maxRetries?: number) => void
  setTimedOut: (seat: SeatRole, retryCount: number, maxRetries: number, willRetry: boolean) => void
  setAbandoned: (seat: SeatRole, totalAttempts: number) => void
  clear: () => void
}

export const useCueStore = create<CueState>((set) => ({
  status: { kind: 'idle' },
  lastAbandonedAt: null,
  setPending: (seat, retryCount = 0, maxRetries = 5) =>
    set({ status: { kind: 'pending', seat, retryCount, maxRetries } }),
  setTimedOut: (seat, retryCount, maxRetries, willRetry) =>
    set({
      status: { kind: 'timed_out', seat, retryCount, maxRetries, willRetry },
    }),
  setAbandoned: (seat, totalAttempts) =>
    set({
      status: { kind: 'abandoned', seat, totalAttempts },
      lastAbandonedAt: Date.now(),
    }),
  clear: () => set({ status: { kind: 'idle' } }),
}))

/** Helper：判斷指定 seat 當前的視覺狀態（給 SeatChip / Observer UI 用）。 */
export function getSeatCueClass(
  status: CueStatus,
  seat: SeatRole,
): 'pending' | 'timed_out' | 'abandoned' | null {
  if (status.kind === 'idle') return null
  if (status.seat !== seat) return null
  if (status.kind === 'pending') return 'pending'
  if (status.kind === 'timed_out') return 'timed_out'
  if (status.kind === 'abandoned') return 'abandoned'
  return null
}
