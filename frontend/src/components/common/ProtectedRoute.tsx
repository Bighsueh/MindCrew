import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { Loading } from './Loading'

interface ProtectedRouteProps {
  requireTeacher?: boolean
}

export function ProtectedRoute({ requireTeacher = false }: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading } = useAuthStore()
  const location = useLocation()

  if (isLoading) {
    return <Loading fullScreen text="驗證身份中…" />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requireTeacher && user?.role !== 'teacher') {
    return <Navigate to="/projects" replace />
  }

  return <Outlet />
}
