import { CSSProperties, useState } from 'react'
import { Check, Plus, RotateCcw, Shuffle, Sparkles, Loader2, X } from 'lucide-react'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { RotatingText } from '../common/RotatingText'
import { cn } from '../../lib/utils'
import type { StakeholderSuggestion } from '../../types/models'

interface Props {
  suggestions: StakeholderSuggestion[]
  selected: StakeholderSuggestion[]
  onChange: (next: StakeholderSuggestion[]) => void
  requiredCount: number
  isLoading: boolean
  onRefetch: () => void
  onManualAdd?: (s: StakeholderSuggestion) => void
}

const LOADING_PHRASES = [
  '分析設計挑戰…',
  '識別利害關係人…',
  '探索影響關係…',
  '整理建議名單…',
]

function makeId(): string {
  return `manual-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function pickRandom<T>(items: readonly T[], count: number): T[] {
  const pool = [...items]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, count)
}

function SkeletonCard({ delay }: { delay: number }) {
  return (
    <div
      className="flex flex-col gap-2 rounded-xl border border-border-light bg-surface/40 p-3 animate-pulse"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1.5 flex-1">
          <div className="h-3.5 w-24 rounded bg-border-light" />
          <div className="h-2.5 w-16 rounded bg-border-light" />
        </div>
        <div className="h-5 w-5 rounded-full bg-border-light shrink-0" />
      </div>
      <div className="h-2.5 w-full rounded bg-border-light" />
      <div className="h-2.5 w-3/4 rounded bg-border-light" />
    </div>
  )
}

export function StakeholderPicker({
  suggestions,
  selected,
  onChange,
  requiredCount,
  isLoading,
  onRefetch,
  onManualAdd,
}: Props) {
  const [manualOpen, setManualOpen] = useState(false)
  const [manualName, setManualName] = useState('')
  const [manualRole, setManualRole] = useState('')
  const [manualRelevance, setManualRelevance] = useState('')

  const selectedIds = new Set(selected.map((s) => s.id))
  const atCapacity = selected.length >= requiredCount
  const atFull = selected.length === requiredCount

  const handleAutoSelect = () => {
    if (suggestions.length === 0) return
    onChange(pickRandom(suggestions, requiredCount))
  }

  const toggle = (item: StakeholderSuggestion) => {
    if (selectedIds.has(item.id)) {
      onChange(selected.filter((s) => s.id !== item.id))
      return
    }
    if (atCapacity) return
    onChange([...selected, item])
  }

  const handleManualSubmit = () => {
    const name = manualName.trim()
    const role = manualRole.trim()
    const relevance = manualRelevance.trim()
    if (!name || !role) return
    const item: StakeholderSuggestion = {
      id: makeId(),
      name,
      role,
      relevance: relevance || '使用者手動加入的利害關係人',
    }
    if (onManualAdd) {
      onManualAdd(item)
    } else if (!atCapacity) {
      onChange([...selected, item])
    }
    setManualName('')
    setManualRole('')
    setManualRelevance('')
    setManualOpen(false)
  }

  const displayList: StakeholderSuggestion[] = [
    ...suggestions,
    ...selected.filter((s) => !suggestions.some((sg) => sg.id === s.id)),
  ]

  return (
    <div className="flex flex-col gap-4">
      {selected.length === 0 && suggestions.length > 0 && (
        <Button
          variant="primary"
          className="w-full"
          onClick={handleAutoSelect}
          disabled={isLoading}
        >
          <Shuffle size={14} />
          自動選擇（隨機 {requiredCount} 位）
        </Button>
      )}

      <div className="flex items-center justify-between gap-2 flex-wrap">
        {/* 計數器：小圓點 */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            {Array.from({ length: requiredCount }).map((_, i) => (
              <span
                key={i}
                className={cn(
                  'h-3 w-3 rounded-full transition-all duration-300',
                  i < selected.length
                    ? atFull
                      ? 'bg-success scale-110'
                      : 'bg-primary'
                    : 'border border-border bg-surface',
                )}
              />
            ))}
          </div>
          <span className="text-sm text-text-muted">
            <span className={cn('font-semibold', atFull ? 'text-success' : 'text-primary')}>
              {selected.length}
            </span>
            {' '}/ {requiredCount} 位
          </span>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button variant="secondary" onClick={onRefetch} disabled={isLoading}>
            {isLoading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            再請 AI 建議幾位
          </Button>
          <Button
            variant="secondary"
            onClick={() => setManualOpen((v) => !v)}
            disabled={atCapacity && !manualOpen}
          >
            <Plus size={14} />
            自己加一位
          </Button>
        </div>
      </div>

      {manualOpen && (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-bg-warm/30 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-text">手動加入利害關係人</span>
            <button
              type="button"
              onClick={() => setManualOpen(false)}
              className="text-text-muted hover:text-text cursor-pointer"
              aria-label="關閉"
            >
              <X size={14} />
            </button>
          </div>
          <Input
            label="名字 / 代稱"
            value={manualName}
            onChange={(e) => setManualName(e.target.value)}
            placeholder="例：小芸 / 採購主任張先生"
          />
          <Input
            label="身份 / 角色"
            value={manualRole}
            onChange={(e) => setManualRole(e.target.value)}
            placeholder="例：賣場顧客、店長、清潔人員"
          />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-text">與這題的關聯（選填）</label>
            <textarea
              value={manualRelevance}
              onChange={(e) => setManualRelevance(e.target.value)}
              placeholder="這個人為什麼跟這個設計題目有關？"
              rows={2}
              className="rounded-md border border-border px-3 py-2 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setManualOpen(false)}>取消</Button>
            <Button onClick={handleManualSubmit} disabled={!manualName.trim() || !manualRole.trim()}>
              加入
            </Button>
          </div>
        </div>
      )}

      {/* Loading：RotatingText + skeleton grid */}
      {isLoading && displayList.length === 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <Loader2 size={14} className="animate-spin text-primary shrink-0" />
            <RotatingText prefix="AI 正在" phrases={LOADING_PHRASES} />
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} delay={i * 60} />
            ))}
          </div>
        </div>
      )}

      {!isLoading && displayList.length === 0 && (
        <div className="rounded-xl border border-dashed border-border-light bg-surface/40 p-6 text-center text-sm text-text-muted">
          還沒有任何建議。點「再請 AI 建議幾位」開始。
        </div>
      )}

      {/* 卡片列表：stagger 進場 */}
      {displayList.length > 0 && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3 stagger-children">
          {displayList.map((item, idx) => {
            const isSelected = selectedIds.has(item.id)
            const disabled = !isSelected && atCapacity
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => toggle(item)}
                disabled={disabled}
                style={{ '--stagger-index': idx } as CSSProperties}
                className={cn(
                  'flex flex-col gap-1 rounded-xl border p-3 text-left transition-all duration-150',
                  'active:scale-95',
                  isSelected
                    ? 'border-success/60 bg-success/5 scale-[1.01] cursor-pointer'
                    : disabled
                      ? 'border-border-light bg-surface/40 opacity-60 cursor-not-allowed'
                      : 'border-border bg-surface hover:border-primary/40 hover:bg-primary/5 cursor-pointer',
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-text">{item.name}</div>
                    <div className="text-xs text-text-muted">{item.role}</div>
                  </div>
                  <div
                    className={cn(
                      'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-all duration-200',
                      isSelected
                        ? 'border-success bg-success text-text-inverse scale-110'
                        : 'border-border bg-surface',
                    )}
                    aria-hidden="true"
                  >
                    {isSelected && <Check size={12} />}
                  </div>
                </div>
                {item.relevance && (
                  <p className="text-[11px] leading-relaxed text-text-muted">{item.relevance}</p>
                )}
              </button>
            )
          })}
        </div>
      )}

      {selected.length > 0 && (
        <button
          type="button"
          onClick={() => onChange([])}
          className="self-end inline-flex items-center gap-1 text-xs text-text-muted hover:text-text cursor-pointer"
        >
          <RotateCcw size={12} />
          清空勾選
        </button>
      )}
    </div>
  )
}
