import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { LayoutDashboard, FolderOpen, LogOut } from 'lucide-react'
import { cn } from '../../lib/utils'

export function AppLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const location = useLocation()

  const isTeacher = user?.role === 'teacher'

  const navItems = [
    { to: '/projects', label: '專案列表', icon: FolderOpen },
    ...(isTeacher
      ? [{ to: '/teacher/dashboard', label: '教師儀表板', icon: LayoutDashboard }]
      : []),
  ]

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
          <Link to="/projects" className="text-lg font-bold text-primary">
            MindCrew
          </Link>

          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  location.pathname === item.to
                    ? 'bg-primary/10 text-primary'
                    : 'text-text-muted hover:bg-surface-hover hover:text-text'
                )}
              >
                <item.icon size={16} />
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-text-muted">{user.display_name}</span>
            )}
            <button
              onClick={logout}
              className="flex items-center gap-1 rounded-md px-3 py-2 text-sm text-text-muted transition-colors hover:bg-error/10 hover:text-error cursor-pointer"
            >
              <LogOut size={16} />
              登出
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
