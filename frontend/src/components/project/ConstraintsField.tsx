import { useMemo } from 'react'
import { cn } from '../../lib/utils'

export type ConstraintsMode = 'simple' | 'advanced'

export type BudgetLevel =
  | ''
  | '無預算（NT$ 0）'
  | '微型（NT$ 1,000 以下）'
  | '小型（NT$ 1,000 – 10,000）'
  | '中型（NT$ 10,000 – 100,000）'
  | '大型（NT$ 100,000 以上）'
  | '不限'

export interface SimpleConstraints {
  budget: BudgetLevel
  targetUsers: string[]
  targetUsersOther: string
  fieldSites: string[]
  fieldSitesOther: string
}

export const EMPTY_SIMPLE_CONSTRAINTS: SimpleConstraints = {
  budget: '',
  targetUsers: [],
  targetUsersOther: '',
  fieldSites: [],
  fieldSitesOther: '',
}

const BUDGET_OPTIONS: BudgetLevel[] = [
  '無預算（NT$ 0）',
  '微型（NT$ 1,000 以下）',
  '小型（NT$ 1,000 – 10,000）',
  '中型（NT$ 10,000 – 100,000）',
  '大型（NT$ 100,000 以上）',
  '不限',
]

const TARGET_USER_OPTIONS = [
  '兒童',
  '青少年',
  '上班族',
  '長者',
  '身障者',
  '偏鄉居民',
]

const FIELD_SITE_OPTIONS = [
  '校園',
  '社區',
  '線上',
  '實體商店',
  '公共空間',
  '醫療場域',
]

export function buildSimpleConstraintsText(simple: SimpleConstraints): string {
  const parts: string[] = []
  if (simple.budget) parts.push(`預算：${simple.budget}`)

  const users = [...simple.targetUsers]
  if (simple.targetUsersOther.trim()) users.push(simple.targetUsersOther.trim())
  if (users.length > 0) parts.push(`目標使用者：${users.join('、')}`)

  const sites = [...simple.fieldSites]
  if (simple.fieldSitesOther.trim()) sites.push(simple.fieldSitesOther.trim())
  if (sites.length > 0) parts.push(`落地場域：${sites.join('、')}`)

  return parts.join('；')
}

interface Props {
  mode: ConstraintsMode
  onModeChange: (mode: ConstraintsMode) => void
  simple: SimpleConstraints
  onSimpleChange: (next: SimpleConstraints) => void
  advancedText: string
  onAdvancedTextChange: (next: string) => void
  helperText?: string
}

export function ConstraintsField({
  mode,
  onModeChange,
  simple,
  onSimpleChange,
  advancedText,
  onAdvancedTextChange,
  helperText,
}: Props) {
  const preview = useMemo(() => buildSimpleConstraintsText(simple), [simple])

  const toggle = (key: 'targetUsers' | 'fieldSites', value: string) => {
    const current = simple[key]
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value]
    onSimpleChange({ ...simple, [key]: next })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-text">學習活動限制（選填，但強烈建議）</label>
        <div className="flex gap-1 rounded-full bg-bg-warm/60 p-0.5 text-xs">
          {(['simple', 'advanced'] as ConstraintsMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onModeChange(m)}
              className={cn(
                'rounded-full px-3 py-1 transition-all cursor-pointer',
                mode === m
                  ? 'bg-primary text-text-inverse shadow-sm'
                  : 'text-text-muted hover:text-text',
              )}
            >
              {m === 'simple' ? '簡單' : '進階'}
            </button>
          ))}
        </div>
      </div>
      {helperText && <p className="text-xs text-text-muted">{helperText}</p>}

      {mode === 'simple' ? (
        <div className="flex flex-col gap-4 rounded-lg border border-border-light bg-surface/60 p-4">
          {/* 預算 */}
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-text">預算範圍</div>
            <div className="flex flex-wrap gap-1.5">
              {BUDGET_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() =>
                    onSimpleChange({
                      ...simple,
                      budget: simple.budget === opt ? '' : opt,
                    })
                  }
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-all cursor-pointer',
                    simple.budget === opt
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-surface text-text-muted hover:border-primary/40',
                  )}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          {/* 目標使用者 */}
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-text">目標使用者族群</div>
            <div className="flex flex-wrap gap-1.5">
              {TARGET_USER_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => toggle('targetUsers', opt)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-all cursor-pointer',
                    simple.targetUsers.includes(opt)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-surface text-text-muted hover:border-primary/40',
                  )}
                >
                  {opt}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={simple.targetUsersOther}
              onChange={(e) =>
                onSimpleChange({ ...simple, targetUsersOther: e.target.value })
              }
              placeholder="其他（自填，例：新住民、自閉症兒童）"
              className="mt-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>

          {/* 落地場域 */}
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-text">落地場域</div>
            <div className="flex flex-wrap gap-1.5">
              {FIELD_SITE_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => toggle('fieldSites', opt)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-all cursor-pointer',
                    simple.fieldSites.includes(opt)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-surface text-text-muted hover:border-primary/40',
                  )}
                >
                  {opt}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={simple.fieldSitesOther}
              onChange={(e) =>
                onSimpleChange({ ...simple, fieldSitesOther: e.target.value })
              }
              placeholder="其他（自填，例：博物館、安養院）"
              className="mt-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>

          {preview && (
            <div className="rounded-md bg-bg-warm/60 px-3 py-2 text-xs text-text-muted">
              <span className="font-semibold text-text">送出內容：</span>
              {preview}
            </div>
          )}
        </div>
      ) : (
        <textarea
          value={advancedText}
          onChange={(e) => onAdvancedTextChange(e.target.value)}
          placeholder="列出這個學習活動的關鍵限制條件…例：預算極低、使用者多為長者、必須在 3 個月內落地。"
          rows={4}
          className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
        />
      )}
    </div>
  )
}
