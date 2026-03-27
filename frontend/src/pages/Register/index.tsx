import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../../services/authService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'

export function RegisterPage() {
  const navigate = useNavigate()
  const loginStore = useAuthStore((s) => s.login)

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('兩次輸入的密碼不一致。')
      return
    }

    if (password.length < 8) {
      setError('密碼至少需要 8 個字元。')
      return
    }

    setIsLoading(true)

    try {
      const data = await register({ email, password, display_name: displayName })
      loginStore(data.user)
      navigate('/projects', { replace: true })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        setError('此電子郵件已被使用。')
      } else {
        setError('註冊失敗，請稍後再試。')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        {/* Title */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-3xl shadow-lg">
            👩‍🏫
          </div>
          <h1 className="text-2xl font-bold text-gray-900">教師註冊</h1>
          <p className="mt-1 text-sm text-gray-500">建立您的教師帳號以管理課堂</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="顯示名稱"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="王小明老師"
            required
          />

          <Input
            label="電子郵件"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teacher@school.edu.tw"
            required
            autoComplete="email"
          />

          <Input
            label="密碼"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 8 個字元"
            required
            autoComplete="new-password"
          />

          <Input
            label="確認密碼"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="再次輸入密碼"
            required
            autoComplete="new-password"
          />

          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <Button type="submit" isLoading={isLoading} className="mt-2 w-full" size="lg">
            建立帳號
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-gray-500">
          已有帳號？{' '}
          <Link to="/login" className="font-medium text-blue-600 hover:underline">
            直接登入
          </Link>
        </p>
      </div>
    </div>
  )
}
