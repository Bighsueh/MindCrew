import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { Loading } from './Loading'

/**
 * Phase 25 — guard that only lets `role === 'admin'` users through.
 *
 * Mirrors {@link ProtectedRoute} but with the admin check. Non-admins are
 * sent to /projects (not /login) so legit students aren't shown a login
 * screen they don't need.
 */
export function AdminRoute() {
  const { user, isAuthenticated, isLoading } = useAuthStore()
  const location = useLocation()

  if (isLoading) {
    return <Loading fullScreen text="驗證身份中…" />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // We're authenticated (a token exists) but /me hasn't populated `user`
  // yet — happens right after a hard-navigation to /admin/* before the
  // App-level useAuth() effect resolves. Render Loading instead of bouncing
  // back to /projects, which used to drop admins out of the console.
  if (!user) {
    return <Loading fullScreen text="驗證身份中…" />
  }

  if (user.role !== 'admin') {
    return <Navigate to="/projects" replace />
  }

  return <Outlet />
}
