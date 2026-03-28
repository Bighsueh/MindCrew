import { Link, Outlet } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      <div className="w-full max-w-md">
        <div className="mb-4">
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-sm text-text-muted transition-colors hover:text-text"
          >
            <ChevronLeft size={16} aria-hidden />
            返回首頁
          </Link>
        </div>

        <div className="mb-8 text-center">
          <Link
            to="/"
            className="group inline-block rounded-lg no-underline outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            aria-label="返回首頁"
          >
            <h1 className="text-3xl font-bold text-primary transition-opacity group-hover:opacity-80">
              MindCrew
            </h1>
            <p className="mt-2 text-sm text-text-muted transition-opacity group-hover:opacity-80">
              Design Thinking AI 協作平台
            </p>
          </Link>
        </div>

        <div className="rounded-xl bg-surface p-8 shadow-lg">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
