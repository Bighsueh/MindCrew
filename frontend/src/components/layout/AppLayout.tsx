import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { LayoutDashboard, FolderOpen, LogOut, HelpCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  startProjectsTour,
  clearProjectsTourFlag,
} from '../onboarding/projectsTour'
import {
  startTeacherDashboardTour,
  clearTeacherDashboardTourFlag,
} from '../onboarding/teacherDashboardTour'

export function AppLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const location = useLocation()

  const isTeacher = user?.role === 'teacher'

  const navItems = [
    { to: '/projects', label: '學習活動', icon: FolderOpen },
    ...(isTeacher
      ? [{ to: '/teacher/dashboard', label: '教師儀表板', icon: LayoutDashboard }]
      : []),
  ]

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-40 bg-bg/95 backdrop-blur-md shadow-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link to="/projects" className="font-brand text-xl text-primary transition-opacity hover:opacity-80">
            MindCrew
          </Link>

          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'nav-link-underline relative flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  location.pathname === item.to
                    ? 'text-primary'
                    : 'text-text-muted hover:text-text'
                )}
              >
                <item.icon size={16} />
                {item.label}
                {location.pathname === item.to && (
                  <span className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full bg-primary" />
                )}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-text-muted">{user.display_name}</span>
            )}
            {(() => {
              const isProjects = location.pathname === '/projects'
              const isTeacherDash = location.pathname === '/teacher/dashboard'
              if (!user?.role) return null
              if (!isProjects && !isTeacherDash) return null
              const onClick = () => {
                if (isProjects) {
                  clearProjectsTourFlag()
                  startProjectsTour(user.role)
                } else {
                  clearTeacherDashboardTourFlag()
                  startTeacherDashboardTour()
                }
              }
              return (
                <button
                  type="button"
                  onClick={onClick}
                  aria-label="重新導引"
                  title="重新導引"
                  className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-surface hover:text-text cursor-pointer"
                >
                  <HelpCircle size={16} />
                </button>
              )
            })()}
            <button
              onClick={logout}
              className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-text-muted transition-colors hover:bg-error/10 hover:text-error cursor-pointer"
            >
              <LogOut size={16} />
              登出
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        <div key={location.pathname} className="page-enter">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
