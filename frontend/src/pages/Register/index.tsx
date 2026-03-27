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
    <form onSubmit={handleSubmit} className="space-y-5">
      <h2 className="text-xl font-semibold text-text">教師註冊</h2>
      <p className="text-sm text-text-muted">建立您的教師帳號以管理課堂</p>

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

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

      <Button type="submit" isLoading={isLoading} className="w-full" size="lg">
        建立帳號
      </Button>

      <p className="text-center text-sm text-text-muted">
        已有帳號？{' '}
        <Link to="/login" className="font-medium text-primary hover:underline">
          直接登入
        </Link>
      </p>
    </form>
  )
}
