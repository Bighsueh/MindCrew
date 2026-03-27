import { Outlet } from 'react-router-dom'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-primary">MindCrew</h1>
          <p className="mt-2 text-sm text-text-muted">
            Design Thinking AI 協作平台
          </p>
        </div>

        <div className="rounded-xl bg-surface p-8 shadow-lg">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
