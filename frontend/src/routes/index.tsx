import { createBrowserRouter, Navigate } from 'react-router-dom'
import { App } from '../App'
import { ProtectedRoute } from '../components/common/ProtectedRoute'
import { LoginPage } from '../pages/Login'
import { RegisterPage } from '../pages/Register'
import { ProjectsPage } from '../pages/Projects'
import { NewProjectPage } from '../pages/Projects/NewProject'
import { ProjectLobbyPage } from '../pages/ProjectLobby'
import { WorkspacePage } from '../pages/Workspace'
import { TeacherDashboardPage } from '../pages/TeacherDashboard'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      // Public routes
      { index: true, element: <Navigate to="/login" replace /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },

      // Auth-required routes
      {
        element: <ProtectedRoute />,
        children: [
          { path: 'projects', element: <ProjectsPage /> },
          { path: 'projects/new', element: <NewProjectPage /> },
          { path: 'projects/:id/lobby', element: <ProjectLobbyPage /> },
          { path: 'projects/:id/workspace', element: <WorkspacePage /> },
        ],
      },

      // Teacher-only routes
      {
        element: <ProtectedRoute requireTeacher />,
        children: [
          { path: 'teacher/dashboard', element: <TeacherDashboardPage /> },
        ],
      },

      // Catch-all
      { path: '*', element: <Navigate to="/login" replace /> },
    ],
  },
])
