import { useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { cn } from '../../lib/utils'
import { suggestConstraints } from '../../services/projectService'
import type { ConstraintSuggestions } from '../../types/models'

interface Props {
  projectName: string
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

function chipsFromSuggestions(s: ConstraintSuggestions): Record<CategoryKey, string[]> {
  return {
    budget: s.budget_hints ?? [],
    audience: s.audience_hints ?? [],
    venue: s.venue_hints ?? [],
    other: s.other_hints ?? [],
  }
}

function appendChip(existing: string, chip: string): string {
  const trimmed = existing.trim()
  if (!trimmed) return chip
  const sep = /[。.;\n]$/.test(trimmed) ? ' ' : '；'
  return `${trimmed}${sep}${chip}`
}

function removeChip(existing: string, chip: string): string {
  let result = existing
  // Remove with surrounding separators (order matters: mid → trailing → leading)
  result = result.replace(`；${chip}；`, '；')
  result = result.replace(`；${chip}`, '')
  result = result.replace(`${chip}；`, '')
  result = result.replace(` ${chip}`, '')
  result = result.replace(`${chip} `, '')
  if (result === chip) result = ''
  return result.replace(/^[；\s]+|[；\s]+$/g, '').trim()
}

// Skeleton row widths for shimmer placeholder
const SKELETON_ROWS: number[][] = [[72, 90, 60], [80, 64, 96, 56], [70, 88]]

export function ConstraintsField({
  projectName,
  projectDescription,
  value,
  onChange,
  helperText,
}: Props) {
  const [suggestions, setSuggestions] = useState<Record<CategoryKey, string[]> | null>(null)
  const [adopted, setAdopted] = useState<Set<string>>(new Set())
  const [hoveringChip, setHoveringChip] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [textareaFlash, setTextareaFlash] = useState(false)

  const canRequest = projectName.trim().length > 0 && !loading
  const panelVisible = loading || suggestions !== null

  const handleRequest = async () => {
    setError(null)
    setLoading(true)
    setSuggestions(null)
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

  const handleToggle = (chip: string) => {
    if (adopted.has(chip)) {
      onChange(removeChip(value, chip))
      setAdopted((prev) => {
        const next = new Set(prev)
        next.delete(chip)
        return next
      })
    } else {
      onChange(appendChip(value, chip))
      setAdopted((prev) => new Set(prev).add(chip))
      setTextareaFlash(true)
      setTimeout(() => setTextareaFlash(false), 350)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Label row */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <label className="text-sm font-medium text-text">
          設計限制條件（選填，但強烈建議）
        </label>

        {/* AI button + tooltip wrapper */}
        <div className="relative group/tip">
          <button
            type="button"
            onClick={handleRequest}
            disabled={!canRequest}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs transition-all duration-200',
              canRequest
                ? 'bg-primary/10 text-primary hover:bg-primary/20 hover:shadow-sm active:scale-95 cursor-pointer'
                : 'bg-bg-warm/60 text-text-muted cursor-not-allowed',
            )}
          >
            {loading ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Sparkles size={12} />
            )}
            {loading ? 'AI 思考中…' : suggestions ? '重新請 AI 建議' : '由 AI 建議條件'}
          </button>

          {/* Disabled tooltip */}
          {!canRequest && !loading && (
            <div className="pointer-events-none absolute right-0 top-full mt-1.5 z-10 rounded-md bg-text px-2 py-1 text-[10px] text-bg whitespace-nowrap opacity-0 group-hover/tip:opacity-100 transition-opacity duration-150">
              請先填寫設計題目
            </div>
          )}
        </div>
      </div>

      {helperText && <p className="text-xs text-text-muted">{helperText}</p>}

      {/* Suggestions panel — slides in between label and textarea */}
      <div
        className={cn(
          'grid transition-all duration-300 ease-out',
          panelVisible ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
      >
        <div className="overflow-hidden">
          <div className="flex flex-col gap-2 rounded-lg border border-border-light bg-bg-warm/40 p-3 mb-0.5">
            {loading ? (
              // Shimmer skeleton
              <>
                <div className="h-3 w-28 rounded bg-border-light animate-pulse" />
                {SKELETON_ROWS.map((widths, rowIdx) => (
                  <div key={rowIdx} className="flex flex-col gap-1">
                    <div
                      className="h-2.5 w-10 rounded bg-border-light animate-pulse"
                      style={{ animationDelay: `${rowIdx * 80}ms` }}
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {widths.map((w, colIdx) => (
                        <div
                          key={colIdx}
                          className="h-6 rounded-full bg-border-light animate-pulse"
                          style={{
                            width: `${w}px`,
                            animationDelay: `${(rowIdx * widths.length + colIdx) * 40}ms`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </>
            ) : suggestions ? (
              <>
                <p className="text-xs text-text-muted">
                  AI 建議方向（點選採納，再點一次移除）
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
                        {chips.map((chip, idx) => {
                          const used = adopted.has(chip)
                          const isHovering = hoveringChip === chip
                          return (
                            <button
                              key={chip}
                              type="button"
                              onClick={() => handleToggle(chip)}
                              onMouseEnter={() => setHoveringChip(chip)}
                              onMouseLeave={() => setHoveringChip(null)}
                              style={{ animationDelay: `${idx * 35}ms` }}
                              className={cn(
                                'animate-chip-enter rounded-full border px-3 py-1 text-xs cursor-pointer',
                                'transition-all duration-150 active:scale-90',
                                used && isHovering
                                  ? 'border-error/50 bg-error/10 text-error scale-95'
                                  : used
                                  ? 'border-success/60 bg-success/10 text-success'
                                  : isHovering
                                  ? 'border-primary/50 bg-primary/8 text-primary scale-105'
                                  : 'border-border bg-surface text-text',
                              )}
                            >
                              {used && isHovering
                                ? `✕ ${chip}`
                                : used
                                ? `✓ ${chip}`
                                : `+ ${chip}`}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* Textarea */}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例：預算極低、3 個月內 MVP、需符合無障礙設計法規…（也可以等 AI 建議後採納）"
        rows={4}
        className={cn(
          'rounded-md border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none transition-all duration-300',
          textareaFlash
            ? 'border-success/50 ring-2 ring-success/20 focus:ring-success/20'
            : 'border-border focus:ring-2 focus:ring-primary/20 focus:border-primary',
        )}
      />

      {error && (
        <div className="rounded-md bg-error-bg px-3 py-2 text-xs text-error">
          {error}
        </div>
      )}
    </div>
  )
}
