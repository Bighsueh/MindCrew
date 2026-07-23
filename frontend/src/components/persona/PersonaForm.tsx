import { useEffect, useState } from 'react'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { cn } from '../../lib/utils'
import type { LensAffinities, Persona, PersonalityAxis } from '../../types/models'

interface PersonaFormProps {
  initial: Persona
  onSave: (persona: Persona) => void | Promise<void>
  onCancel: () => void
  /** 緊湊模式：用於座位卡內嵌（縮小留白、欄位更貼） */
  compact?: boolean
  saveLabel?: string
}

const AXIS_OPTIONS: { value: PersonalityAxis; label: string; hint: string }[] = [
  { value: 'contrarian', label: '挑戰者', hint: '會質疑前提、提出反向觀點' },
  { value: 'balanced', label: '平衡型', hint: '視情境決定支持或挑戰' },
  { value: 'supportive', label: '共建者', hint: '把他人觀點接力放大' },
]

const LENS_FIELDS: Array<{ key: keyof LensAffinities; label: string; desc: string }> = [
  { key: 'empathy', label: '同理 (empathy)', desc: '從人的感受出發' },
  { key: 'structure', label: '結構 (structure)', desc: '把資訊歸納成模式' },
  { key: 'creativity', label: '創意 (creativity)', desc: '跨界類比、跳脫框架' },
  { key: 'feasibility', label: '可行 (feasibility)', desc: '評估資源與落地' },
]

function clamp(value: number): number {
  if (Number.isNaN(value)) return 0.5
  return Math.max(0, Math.min(1, value))
}

/**
 * PersonaForm — AI 隊友人設的編輯欄位本體（不含外框）。
 * 同時被 PersonaEditDialog（Modal 版）與座位卡內嵌編輯（SeatPopover）共用，
 * 確保兩處欄位/驗證/儲存邏輯完全一致。
 */
export function PersonaForm({
  initial,
  onSave,
  onCancel,
  compact = false,
  saveLabel = '儲存',
}: PersonaFormProps) {
  const [draft, setDraft] = useState<Persona>(initial)
  const [error, setError] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // initial 換人（換座位/重開）時重置草稿。
  useEffect(() => {
    setDraft(initial)
    setError('')
  }, [initial])

  const handleAffinity = (key: keyof LensAffinities, value: number) => {
    setDraft((prev) => ({
      ...prev,
      lens_affinities: { ...prev.lens_affinities, [key]: clamp(value) },
    }))
  }

  const handleSubmit = async () => {
    if (!draft.name.trim()) {
      setError('「姓名」為必填。')
      return
    }
    setError('')
    setIsSaving(true)
    try {
      await onSave({
        ...draft,
        name: draft.name.trim(),
        role: draft.role.trim(),
        expertise: draft.expertise.trim(),
        personality_desc: draft.personality_desc.trim(),
        backstory: draft.backstory.trim(),
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : '儲存失敗，請稍後再試。'
      setError(message)
    } finally {
      setIsSaving(false)
    }
  }

  const textareaClass =
    'rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary'

  return (
    <div className={cn('flex flex-col', compact ? 'gap-3' : 'max-h-[70vh] gap-4 overflow-y-auto pr-1')}>
      <Input
        label="姓名"
        value={draft.name}
        onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
        placeholder="例：陳秀英"
        required
      />

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text">專長範圍</label>
        <textarea
          value={draft.expertise}
          onChange={(e) => setDraft((prev) => ({ ...prev, expertise: e.target.value }))}
          placeholder="列 2-3 個具體會什麼，例：慢性病管理、長者衛教、社區外展"
          rows={2}
          className={textareaClass}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text">背景（為什麼這個身分對主題有切角）</label>
        <textarea
          value={draft.backstory}
          onChange={(e) => setDraft((prev) => ({ ...prev, backstory: e.target.value }))}
          placeholder="30 字內描述背景"
          rows={2}
          className={textareaClass}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text">個性傾向</label>
        <div className={cn('grid gap-2', compact ? 'grid-cols-1' : 'grid-cols-3')}>
          {AXIS_OPTIONS.map((axis) => (
            <button
              key={axis.value}
              type="button"
              onClick={() => setDraft((prev) => ({ ...prev, personality_axis: axis.value }))}
              className={cn(
                'rounded-lg border p-3 text-left text-sm transition-all cursor-pointer',
                compact && 'flex items-center gap-2 p-2',
                draft.personality_axis === axis.value
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
              )}
            >
              <div className="font-semibold">{axis.label}</div>
              <div className={cn('text-xs opacity-80', compact ? '' : 'mt-0.5')}>{axis.hint}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text">個性特質</label>
        <textarea
          value={draft.personality_desc}
          onChange={(e) => setDraft((prev) => ({ ...prev, personality_desc: e.target.value }))}
          placeholder="3-5 個個性特質短語（如：開朗樂觀、明察秋毫、思考跳躍）"
          rows={2}
          className={textareaClass}
        />
      </div>

      <details className="group flex flex-col gap-2 rounded-lg border border-border-light/60 p-3">
        <summary className="cursor-pointer list-none text-sm font-medium text-text marker:hidden">
          <span className="inline-flex items-center gap-2">
            <span className="text-text-muted transition-transform group-open:rotate-90">▶</span>
            進階：認知透鏡強度（AI 已自動配置）
          </span>
        </summary>
        <p className="mt-2 text-xs text-text-muted">
          0.0 ~ 1.0。AI 生成的分數通常已合理，僅在需要時手動微調。
        </p>
        <div className="mt-2 flex flex-col gap-2">
          {LENS_FIELDS.map((field) => {
            const value = draft.lens_affinities[field.key]
            return (
              <div key={field.key} className="flex items-center gap-3 text-sm">
                <div className="w-32 shrink-0">
                  <div className="font-medium text-text">{field.label}</div>
                  <div className="text-[11px] text-text-muted">{field.desc}</div>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={value}
                  onChange={(e) => handleAffinity(field.key, Number(e.target.value))}
                  className="flex-1 accent-primary"
                />
                <span className="w-12 text-right tabular-nums text-text-muted">
                  {value.toFixed(2)}
                </span>
              </div>
            )
          })}
        </div>
      </details>

      {error && (
        <div className="rounded-md bg-error-bg px-3 py-2 text-sm text-error">{error}</div>
      )}

      <div className="flex gap-3 pt-1">
        <Button variant="secondary" className="flex-1" onClick={onCancel} disabled={isSaving}>
          取消
        </Button>
        <Button className="flex-1" onClick={handleSubmit} isLoading={isSaving}>
          {saveLabel}
        </Button>
      </div>
    </div>
  )
}
