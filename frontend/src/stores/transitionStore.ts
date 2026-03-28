import { create } from 'zustand'

export type TransitionPhase =
  | 'idle'
  | 'exiting-landing'
  | 'entering-auth'
  | 'exiting-auth'
  | 'entering-landing'

export type TransitionSource = 'landing' | 'direct' | 'auth-back'

/** Auth route paths that participate in the Landing ↔ Auth transition */
export const AUTH_PATHS = new Set(['/login', '/register'])

interface TransitionState {
  phase: TransitionPhase
  source: TransitionSource
  targetPath: string | null

  startExitLanding: (targetPath: string) => void
  enterAuth: () => void
  startExitAuth: () => void
  enterLanding: () => void
  reset: () => void
}

/*
 * State machine transitions:
 *   idle → exiting-landing → entering-auth → idle
 *   idle → exiting-auth → entering-landing → idle
 */
export const useTransitionStore = create<TransitionState>((set, get) => ({
  phase: 'idle',
  source: 'direct',
  targetPath: null,

  startExitLanding: (targetPath: string) => {
    if (get().phase !== 'idle') return
    set({ phase: 'exiting-landing', source: 'landing', targetPath })
  },

  enterAuth: () => {
    if (get().phase !== 'exiting-landing') return
    set({ phase: 'entering-auth' })
  },

  startExitAuth: () => {
    if (get().phase !== 'idle') return
    set({ phase: 'exiting-auth', source: 'auth-back', targetPath: '/' })
  },

  enterLanding: () => {
    if (get().phase !== 'exiting-auth') return
    set({ phase: 'entering-landing' })
  },

  reset: () => {
    set({ phase: 'idle', source: 'direct', targetPath: null })
  },
}))
