import { Outlet, useLocation } from 'react-router-dom'
import { HeroBackgroundVideo } from '@/components/landing/HeroBackgroundVideo'
import { useTransitionStore, AUTH_PATHS } from '@/stores/transitionStore'

export function TransitionLayout() {
  const location = useLocation()
  const phase = useTransitionStore((s) => s.phase)

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
