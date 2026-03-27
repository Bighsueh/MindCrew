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
      seats: state.seats.map((seat) =>
        seat.seat_role === seatRole ? { ...seat, ...updates } : seat,
      ),
    }))
  },

  clearSeats: () => {
    set({ seats: [] })
  },
}))
