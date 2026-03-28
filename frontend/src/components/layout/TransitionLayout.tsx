import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { HeroBackgroundVideo } from '@/components/landing/HeroBackgroundVideo'
import { useTransitionStore, AUTH_PATHS } from '@/stores/transitionStore'

const LANDING_FADE_OUT_MS = 600

function isReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function TransitionLayout() {
  const location = useLocation()
  const phase = useTransitionStore((s) => s.phase)
  const prevPathRef = useRef(location.pathname)

  // Detect browser back/forward between auth ↔ landing.
  // This component stays mounted across navigations, so prevPathRef is reliable.
  useEffect(() => {
    const prev = prevPathRef.current
    const curr = location.pathname
    prevPathRef.current = curr

    if (prev === curr) return

    const wasAuth = AUTH_PATHS.has(prev)
    const isLanding = curr === '/'
    const currentPhase = useTransitionStore.getState().phase

    if (wasAuth && isLanding && currentPhase === 'idle') {
      // Browser back from auth → landing (no programmatic exit animation was started)
      if (!isReducedMotion()) {
        useTransitionStore.getState().enterLanding()
        window.setTimeout(() => {
          if (useTransitionStore.getState().phase === 'entering-landing') {
            useTransitionStore.getState().reset()
          }
        }, LANDING_FADE_OUT_MS)
      }
    } else if (currentPhase !== 'idle'
      && currentPhase !== 'entering-auth'
      && currentPhase !== 'entering-landing') {
      // Catch-all: reset stuck exit phases on unexpected navigation
      useTransitionStore.getState().reset()
    }
  }, [location.pathname])

  const isAuthRoute = AUTH_PATHS.has(location.pathname)

  // Video mode: static when on auth pages OR transitioning to auth
  const videoMode =
    isAuthRoute || phase === 'exiting-landing' ? 'static-frame' : 'playing'

  return (
    <div className="relative min-h-svh">
      {/* Persistent video background — never unmounts */}
      <div className="fixed inset-0 -z-10">
        <HeroBackgroundVideo mode={videoMode} />
        {/* Persistent overlay — stays visible during page transitions */}
        <div
          className={`absolute inset-0 transition-[background-color] duration-500 ${
            isAuthRoute ? 'bg-bg/75' : 'bg-bg/60'
          }`}
        />
      </div>

      {/* Page content */}
      <Outlet />
    </div>
  )
}
