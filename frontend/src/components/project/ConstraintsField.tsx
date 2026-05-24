import { useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { cn } from '../../lib/utils'
import { suggestConstraints } from '../../services/projectService'
import type { ConstraintSuggestions } from '../../types/models'

/**
 * Phase 27：ConstraintsField — Open Brief 動態建議版。
 *
 * **設計紀律**（見 `specs/17 §11`）：
 * - 完全移除「目標族群 / 落地場域 / 預算」的預設 checkbox 選項
 *   ——那些是設計師要去探索的問題空間，不是出題者預先框死的條件
 * - AI 建議僅以可點擊的 chip 呈現；點擊後**附加**到 textarea 而不是覆寫
 *   ——使用者已寫的內容永遠優先
 * - 文案強調「建議方向，不是必填條件」
 */

interface Props {
  /** Project name — AI 建議需要它，必填才能啟用「✨ 建議」按鈕 */
  projectName: string
  /** Project description — 與 name 一起送給 AI；可空（但建議按鈕仍可用） */
  projectDescription: string
  value: string
  onChange: (next: string) => void
  helperText?: string
}

type CategoryKey = 'budget' | 'audience' | 'venue' | 'other'

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  budget: '預算',
  audience: '可能族群',
  venue: '可能場域',
  other: '其他約束',
}

function chipsFromSuggestions(
  s: ConstraintSuggestions,
): Record<CategoryKey, string[]> {
  return {
    budget: s.budget_hints ?? [],
    audience: s.audience_hints ?? [],
    venue: s.venue_hints ?? [],
    other: s.other_hints ?? [],
  }
}

function appendChip(existing: string, chip: string): string {
  // 永遠附加 — 避免 substring 誤判（例：chip "低" 會被 "預算極低" 包含）。
  // 是否重複交給 `adopted` Set 在 UI 層判斷。
  const trimmed = existing.trim()
  if (!trimmed) return chip
  const sep = /[。.;\n]$/.test(trimmed) ? ' ' : '；'
  return `${trimmed}${sep}${chip}`
}

export function ConstraintsField({
  projectName,
  projectDescription,
  value,
  onChange,
  helperText,
}: Props) {
  const [suggestions, setSuggestions] = useState<
    Record<CategoryKey, string[]> | null
  >(null)
  const [adopted, setAdopted] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canRequest = projectName.trim().length > 0 && !loading

  const handleRequest = async () => {
    setError(null)
    setLoading(true)
    try {
      const result = await suggestConstraints({
        title: projectName.trim(),
        description: projectDescription.trim(),
      })
      setSuggestions(chipsFromSuggestions(result))
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'AI 建議失敗，請稍後再試或自行填寫。'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleAdopt = (chip: string) => {
    if (adopted.has(chip)) return  // 已採納過則 no-op，避免重複附加
    onChange(appendChip(value, chip))
    setAdopted((prev) => {
      const next = new Set(prev)
      next.add(chip)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <label className="text-sm font-medium text-text">
          設計限制條件（選填，但強烈建議）
        </label>
        <button
          type="button"
          onClick={handleRequest}
          disabled={!canRequest}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs transition-all cursor-pointer',
            canRequest
              ? 'bg-primary/10 text-primary hover:bg-primary/15'
              : 'bg-bg-warm/60 text-text-muted cursor-not-allowed',
          )}
        >
          {loading ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Sparkles size={12} />
          )}
          {suggestions ? '重新請 AI 建議' : '由 AI 建議條件'}
        </button>
      </div>
      {helperText && <p className="text-xs text-text-muted">{helperText}</p>}

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例：預算極低、3 個月內 MVP、需符合無障礙設計法規…（也可以等 AI 建議後採納）"
        rows={4}
        className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
      />

      {error && (
        <div className="rounded-md bg-error-bg px-3 py-2 text-xs text-error">
          {error}
        </div>
      )}

      {suggestions && (
        <div className="flex flex-col gap-2 rounded-lg border border-border-light bg-bg-warm/40 p-3">
          <p className="text-xs text-text-muted">
            AI 建議方向（點 chip 採納；不會覆寫你已寫的內容）
          </p>
          {(Object.keys(CATEGORY_LABELS) as CategoryKey[]).map((key) => {
            const chips = suggestions[key]
            if (!chips || chips.length === 0) return null
            return (
              <div key={key} className="flex flex-col gap-1">
                <div className="text-[11px] font-semibold text-text">
                  {CATEGORY_LABELS[key]}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {chips.map((chip) => {
                    const used = adopted.has(chip)
                    return (
                      <button
                        key={chip}
                        type="button"
                        onClick={() => handleAdopt(chip)}
                        className={cn(
                          'rounded-full border px-3 py-1 text-xs transition-all cursor-pointer',
                          used
                            ? 'border-success/60 bg-success/10 text-success'
                            : 'border-border bg-surface text-text hover:border-primary/40 hover:bg-primary/5',
                        )}
                      >
                        {used ? `✓ ${chip}` : `+ ${chip}`}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
