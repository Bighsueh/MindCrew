import { useCallback, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTransitionStore, AUTH_PATHS } from '@/stores/transitionStore'

const LANDING_FADE_OUT_MS = 600
const AUTH_FADE_OUT_MS = 400
const SCROLL_THRESHOLD = 100

function isReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function scrollToTop(): Promise<void> {
  if (window.scrollY <= SCROLL_THRESHOLD) return Promise.resolve()

  return new Promise((resolve) => {
    window.scrollTo({ top: 0, behavior: 'smooth' })

    let resolved = false
    const done = () => {
      if (resolved) return
      resolved = true
      resolve()
    }

    // Fallback: resolve after max 500ms regardless of scroll position
    setTimeout(done, 500)

    const checkScroll = () => {
      if (window.scrollY <= 1) {
        done()
      } else {
        requestAnimationFrame(checkScroll)
      }
    }
    requestAnimationFrame(checkScroll)
  })
}

export function usePageTransition() {
  const navigate = useNavigate()
  const location = useLocation()
  const mountedRef = useRef(true)
  const timerIdsRef = useRef<number[]>([])

  // Imperative access to the Zustand store (not a reactive subscription)
  const getState = useTransitionStore.getState

  const scheduleTimeout = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(() => {
      timerIdsRef.current = timerIdsRef.current.filter((t) => t !== id)
      if (mountedRef.current) fn()
    }, ms)
    timerIdsRef.current.push(id)
    return id
  }, [])

  const clearAllTimers = useCallback(() => {
    timerIdsRef.current.forEach((id) => window.clearTimeout(id))
    timerIdsRef.current = []
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      clearAllTimers()
    }
  }, [clearAllTimers])

  // Safety net: if phase is stuck when this hook mounts, reset it.
  // This handles edge cases where timers were cleared by unmount.
  useEffect(() => {
    const phase = getState().phase
    const curr = location.pathname
    const isAuth = AUTH_PATHS.has(curr)
    const isLanding = curr === '/'

    if (isAuth && phase === 'exiting-landing') {
      // Mounted on auth page with pending landing→auth transition
      getState().enterAuth()
      window.setTimeout(() => {
        if (useTransitionStore.getState().phase === 'entering-auth') {
          useTransitionStore.getState().reset()
        }
      }, AUTH_FADE_OUT_MS)
    } else if (isLanding && (phase === 'exiting-auth' || phase === 'entering-auth')) {
      // Mounted on landing with stuck auth-related phase
      getState().reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const navigateWithTransition = useCallback(
    async (to: string) => {
      if (getState().phase !== 'idle') return

      if (isReducedMotion()) {
        navigate(to)
        return
      }

      getState().startExitLanding(to)
      await scrollToTop()

      if (!mountedRef.current) return

      scheduleTimeout(() => {
        navigate(to)
        if (getState().phase === 'exiting-landing') {
          getState().enterAuth()
          // Use window.setTimeout (not scheduleTimeout) so unmount cleanup
          // of the landing page won't cancel this timer.
          window.setTimeout(() => {
            if (useTransitionStore.getState().phase === 'entering-auth') {
              useTransitionStore.getState().reset()
            }
          }, AUTH_FADE_OUT_MS)
        }
      }, LANDING_FADE_OUT_MS)
    },
    [navigate, getState, scheduleTimeout],
  )

  const navigateBackToLanding = useCallback(() => {
    if (getState().phase !== 'idle') return

    if (isReducedMotion()) {
      navigate('/')
      return
    }

    getState().startExitAuth()

    scheduleTimeout(() => {
      navigate('/')
      if (getState().phase === 'exiting-auth') {
        getState().enterLanding()
        // Use window.setTimeout (not scheduleTimeout) so unmount cleanup
        // of the auth page won't cancel this timer.
        window.setTimeout(() => {
          if (useTransitionStore.getState().phase === 'entering-landing') {
            useTransitionStore.getState().reset()
          }
        }, LANDING_FADE_OUT_MS)
      }
    }, AUTH_FADE_OUT_MS)
  }, [navigate, getState, scheduleTimeout])

  /** Fade out auth panel, then navigate to an authenticated route (e.g. after login). */
  const navigateToApp = useCallback(
    (to: string) => {
      if (getState().phase !== 'idle') return

      if (isReducedMotion()) {
        navigate(to, { replace: true })
        return
      }

      getState().startExitAuthToApp(to)

      scheduleTimeout(() => {
        navigate(to, { replace: true })
        getState().reset()
      }, AUTH_FADE_OUT_MS)
    },
    [navigate, getState, scheduleTimeout],
  )

  return { navigateWithTransition, navigateBackToLanding, navigateToApp }
}
