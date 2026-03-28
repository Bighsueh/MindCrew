import type { MouseEvent } from 'react'
import { Outlet } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useTransitionStore } from '@/stores/transitionStore'
import { usePageTransition } from '@/hooks/usePageTransition'

export function AuthLayout() {
  const phase = useTransitionStore((s) => s.phase)
  const source = useTransitionStore((s) => s.source)
  const { navigateBackToLanding } = usePageTransition()

  // Determine panel animation class
  const panelClass =
    phase === 'entering-auth' && source === 'landing'
      ? 'animate-auth-enter'
      : phase === 'exiting-auth' || phase === 'exiting-auth-to-app'
        ? 'animate-auth-exit'
        : ''

  const handleBackClick = (e: MouseEvent) => {
    e.preventDefault()
    navigateBackToLanding()
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className={`w-full max-w-md ${panelClass}`}>
        <div className="mb-4">
          <a
            href="/"
            onClick={handleBackClick}
            className="inline-flex items-center gap-1 text-sm text-text-muted transition-colors hover:text-text"
          >
            <ChevronLeft size={16} aria-hidden />
            返回首頁
          </a>
        </div>

        <div className="mb-8 text-center">
          <a
            href="/"
            onClick={handleBackClick}
            className="group inline-block rounded-lg no-underline outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            aria-label="返回首頁"
          >
            <h1 className="text-3xl font-bold text-primary transition-opacity group-hover:opacity-80">
              MindCrew
            </h1>
            <p className="mt-2 text-sm text-text-muted transition-opacity group-hover:opacity-80">
              Design Thinking AI 協作平台
            </p>
          </a>
        </div>

        <div className="rounded-xl bg-surface p-8 shadow-lg">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
