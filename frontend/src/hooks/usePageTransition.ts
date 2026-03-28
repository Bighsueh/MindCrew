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
  const prevPathRef = useRef(location.pathname)
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

  // Detect browser back/forward: auth → landing
  useEffect(() => {
    const prev = prevPathRef.current
    const curr = location.pathname

    if (prev !== curr) {
      const wasAuth = AUTH_PATHS.has(prev)
      const isLanding = curr === '/'

      if (wasAuth && isLanding && getState().phase === 'idle') {
        if (!isReducedMotion()) {
          // Browser triggered this navigation; animate the landing entrance
          getState().enterLanding()
          scheduleTimeout(() => getState().reset(), LANDING_FADE_OUT_MS)
        }
      }

      prevPathRef.current = curr
    }
  }, [location.pathname, getState, scheduleTimeout])

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
        // Re-check phase before advancing
        if (getState().phase === 'exiting-landing') {
          getState().enterAuth()
          scheduleTimeout(() => getState().reset(), AUTH_FADE_OUT_MS)
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
      // Re-check phase before advancing
      if (getState().phase === 'exiting-auth') {
        getState().enterLanding()
        scheduleTimeout(() => getState().reset(), LANDING_FADE_OUT_MS)
      }
    }, AUTH_FADE_OUT_MS)
  }, [navigate, getState, scheduleTimeout])

  return { navigateWithTransition, navigateBackToLanding }
}
