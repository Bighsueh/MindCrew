import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { login } from '../../services/authService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const loginStore = useAuthStore((s) => s.login)

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
      navigate(from, { replace: true })
    } catch {
      setError('帳號或密碼錯誤，請重試。')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        {/* Logo/Title */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-3xl shadow-lg">
            🧠
          </div>
          <h1 className="text-2xl font-bold text-gray-900">MindCrew</h1>
          <p className="mt-1 text-sm text-gray-500">設計思考 AI 協作平台</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="電子郵件"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your@email.com"
            required
            autoComplete="email"
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

          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <Button type="submit" isLoading={isLoading} className="mt-2 w-full" size="lg">
            登入
          </Button>
        </form>

        {/* Footer */}
        <p className="mt-6 text-center text-sm text-gray-500">
          還沒有帳號（教師）？{' '}
          <Link to="/register" className="font-medium text-blue-600 hover:underline">
            立即註冊
          </Link>
        </p>
      </div>
    </div>
  )
}
