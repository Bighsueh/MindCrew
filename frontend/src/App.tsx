import { Outlet } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import { Loading } from './components/common/Loading'

export function App() {
  const { isLoading } = useAuth()

  if (isLoading) {
    return <Loading fullScreen text="初始化中…" />
  }

  return <Outlet />
}
