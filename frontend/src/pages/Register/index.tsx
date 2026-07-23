import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { register } from '../../services/authService'
import { useAuthStore } from '../../stores/authStore'
import { usePageTransition } from '../../hooks/usePageTransition'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { cn } from '../../lib/utils'

type RoleChoice = 'teacher' | 'student'

const COPY: Record<RoleChoice, {
  title: string
  subtitle: string
  displayNamePlaceholder: string
  emailPlaceholder: string
}> = {
  teacher: {
    title: '教師註冊',
    subtitle: '建立您的教師帳號以管理課堂',
    displayNamePlaceholder: '王小明老師',
    emailPlaceholder: 'teacher@school.edu.tw',
  },
  student: {
    title: '學生註冊',
    subtitle: '建立您的學生帳號開始探索',
    displayNamePlaceholder: '王小明',
    emailPlaceholder: 'student@school.edu.tw',
  },
}

export function RegisterPage() {
  const loginStore = useAuthStore((s) => s.login)
  const { navigateToApp } = usePageTransition()
  const [searchParams] = useSearchParams()
  const prefilledEmail = searchParams.get('email')?.trim() ?? ''

  const [role, setRole] = useState<RoleChoice>('student')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState(prefilledEmail)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const copy = COPY[role]

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
      const data = await register({ email, password, display_name: displayName, role })
      loginStore(data.user)
      navigateToApp('/projects')
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
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text">我是…</label>
        <div className="grid grid-cols-2 gap-2">
          {(['teacher', 'student'] as RoleChoice[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              className={cn(
                'rounded-lg border p-3 text-sm font-medium transition-all cursor-pointer',
                role === r
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
              )}
            >
              {r === 'teacher' ? '教師' : '學生'}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold text-text">{copy.title}</h2>
        <p className="text-sm text-text-muted">{copy.subtitle}</p>
      </div>

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
        placeholder={copy.displayNamePlaceholder}
        required
      />

      <Input
        label="電子郵件"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={copy.emailPlaceholder}
        required
        autoComplete="email"
        readOnly={prefilledEmail !== ''}
        helperText={prefilledEmail !== '' ? '研究參與：email 已自動帶入，請勿更改' : undefined}
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
