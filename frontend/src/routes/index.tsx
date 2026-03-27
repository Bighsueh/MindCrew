import { createBrowserRouter, Navigate } from 'react-router-dom'
import { App } from '../App'
import { ProtectedRoute } from '../components/common/ProtectedRoute'
import { AppLayout } from '../components/layout/AppLayout'
import { AuthLayout } from '../components/layout/AuthLayout'
import { LoginPage } from '../pages/Login'
import { RegisterPage } from '../pages/Register'
import { ProjectsPage } from '../pages/Projects'
import { ProjectLobbyPage } from '../pages/ProjectLobby'
import { WorkspacePage } from '../pages/Workspace'
import { TeacherDashboardPage } from '../pages/TeacherDashboard'
import { LandingPage } from '../pages/Landing'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      // 公開路由
      { index: true, element: <LandingPage /> },

      // 登入/註冊 — 包裹在 AuthLayout
      {
        element: <AuthLayout />,
        children: [
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
        ],
      },

      // 需登入 — 包裹在 AppLayout + ProtectedRoute
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: 'projects', element: <ProjectsPage /> },
              { path: 'projects/:id/lobby', element: <ProjectLobbyPage /> },
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
              { path: 'teacher/dashboard', element: <TeacherDashboardPage /> },
            ],
          },
        ],
      },

      // 全螢幕路由 — 不包 Layout
      {
        element: <ProtectedRoute />,
        children: [
          { path: 'projects/:id/workspace', element: <WorkspacePage /> },
        ],
      },

      // 預設
      { path: '*', element: <Navigate to="/login" replace /> },
    ],
  },
])
