import { create } from 'zustand'
import type { User } from '../types/models'
import { clearTokens, getAccessToken } from '../services/api'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (user: User) => void
  logout: () => void
  setUser: (user: User) => void
  setLoading: (loading: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!getAccessToken(),
  isLoading: false,

  login: (user: User) => {
    set({ user, isAuthenticated: true })
  },

  logout: () => {
    clearTokens()
    set({ user: null, isAuthenticated: false })
  },

  setUser: (user: User) => {
    set({ user, isAuthenticated: true })
  },

  setLoading: (loading: boolean) => {
    set({ isLoading: loading })
  },
}))
