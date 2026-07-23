import { create } from 'zustand'
import type { Seat, SeatRole } from '../types/models'

interface SeatState {
  seats: Seat[]
  setSeats: (seats: Seat[]) => void
  updateSeat: (seatRole: SeatRole, updates: Partial<Seat>) => void
  clearSeats: () => void
}

export const useSeatStore = create<SeatState>((set) => ({
  seats: [],

  setSeats: (seats: Seat[]) => {
    set({ seats })
  },

  updateSeat: (seatRole: SeatRole, updates: Partial<Seat>) => {
    set((state) => ({
      seats: state.seats.map((seat) => {
        if (seat.seat_role !== seatRole) return seat
        // 只覆蓋「有明確值」的欄位：undefined 不覆蓋（null 仍視為明確清空）。
        // 避免 seat_changed 部分更新缺 display_name/persona 時，把已知名字洗成空白
        // → SeatBar 退化成「AI 組員 A/B/C」（盲測 2026-06-08）。
        const merged = { ...seat }
        for (const [key, value] of Object.entries(updates)) {
          if (value !== undefined) {
            ;(merged as Record<string, unknown>)[key] = value
          }
        }
        return merged
      }),
    }))
  },

  clearSeats: () => {
    set({ seats: [] })
  },
}))
