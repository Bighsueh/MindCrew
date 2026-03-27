import { useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { getMe } from '../services/authService'
import { getAccessToken } from '../services/api'

export function useAuth() {
  const { user, isAuthenticated, isLoading, login, logout, setLoading } = useAuthStore()

  useEffect(() => {
    // On mount: if we have a token but no user, fetch user info
    if (getAccessToken() && !user && !isLoading) {
      setLoading(true)
      getMe()
        .then((me) => login(me))
        .catch(() => logout())
        .finally(() => setLoading(false))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return { user, isAuthenticated, isLoading }
}
