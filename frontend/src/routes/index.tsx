import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { App } from '../App'
import { ProtectedRoute } from '../components/common/ProtectedRoute'
import { AppLayout } from '../components/layout/AppLayout'
import { AuthLayout } from '../components/layout/AuthLayout'
import { TransitionLayout } from '../components/layout/TransitionLayout'
import { LandingPage } from '../pages/Landing'
import { Loading } from '../components/common/Loading'

const LoginPage = lazy(() => import('../pages/Login').then(m => ({ default: m.LoginPage })))
const RegisterPage = lazy(() => import('../pages/Register').then(m => ({ default: m.RegisterPage })))
const ProjectsPage = lazy(() => import('../pages/Projects').then(m => ({ default: m.ProjectsPage })))
const ProjectLobbyPage = lazy(() => import('../pages/ProjectLobby').then(m => ({ default: m.ProjectLobbyPage })))
const WorkspacePage = lazy(() => import('../pages/Workspace').then(m => ({ default: m.WorkspacePage })))
const TeacherDashboardPage = lazy(() => import('../pages/TeacherDashboard').then(m => ({ default: m.TeacherDashboardPage })))

function SuspenseOutlet({ children }: { readonly children: React.ReactNode }) {
  return <Suspense fallback={<Loading fullScreen text="載入中…" />}>{children}</Suspense>
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      // 公開路由 — Landing + Auth 共享 TransitionLayout（影片背景）
      {
        element: <TransitionLayout />,
        children: [
          { index: true, element: <LandingPage /> },
          {
            element: <AuthLayout />,
            children: [
              { path: 'login', element: <SuspenseOutlet><LoginPage /></SuspenseOutlet> },
              { path: 'register', element: <SuspenseOutlet><RegisterPage /></SuspenseOutlet> },
            ],
          },
        ],
      },

      // 需登入 — 包裹在 AppLayout + ProtectedRoute
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: 'projects', element: <SuspenseOutlet><ProjectsPage /></SuspenseOutlet> },
              { path: 'projects/:id/lobby', element: <SuspenseOutlet><ProjectLobbyPage /></SuspenseOutlet> },
            ],
          },
        ],
      },

      // 教師路由 — AppLayout + ProtectedRoute(requireTeacher)
      {
        element: <ProtectedRoute requireTeacher />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: 'teacher/dashboard', element: <SuspenseOutlet><TeacherDashboardPage /></SuspenseOutlet> },
            ],
          },
        ],
      },

      // 全螢幕路由 — 不包 Layout
      {
        element: <ProtectedRoute />,
        children: [
          { path: 'projects/:id/workspace', element: <SuspenseOutlet><WorkspacePage /></SuspenseOutlet> },
        ],
      },

      // 預設
      { path: '*', element: <Navigate to="/login" replace /> },
    ],
  },
])
