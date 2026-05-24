import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { login } from '../../services/authService'
import { useAuthStore } from '../../stores/authStore'
import { usePageTransition } from '../../hooks/usePageTransition'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'

export function LoginPage() {
  const location = useLocation()
  const loginStore = useAuthStore((s) => s.login)
  const { navigateToApp } = usePageTransition()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const from = (location.state as { from?: Location })?.from?.pathname ?? '/projects'

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      const data = await login({ email, password })
      loginStore(data.user)
      // Admins land on the management console; others use the requested/default destination.
      const dest = data.user.role === 'admin' ? '/admin' : from
      navigateToApp(dest)
    } catch {
      setError('帳號或密碼錯誤，請重試。')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <h2 className="text-xl font-semibold text-text">登入</h2>

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      <Input
        label="電子郵件 / 管理員帳號"
        type="text"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        required
        autoComplete="username"
      />

      <Input
        label="密碼"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="••••••••"
        required
        autoComplete="current-password"
      />

      <Button type="submit" isLoading={isLoading} className="w-full" size="lg">
        登入
      </Button>

      <p className="text-center text-sm text-text-muted">
        還沒有帳號（教師）？{' '}
        <Link to="/register" className="font-medium text-primary hover:underline">
          立即註冊
        </Link>
      </p>
    </form>
  )
}
