import { useEffect, useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { cn } from '../../lib/utils'
import type { LensAffinities, Persona, PersonalityAxis } from '../../types/models'

interface PersonaEditDialogProps {
  isOpen: boolean
  initial: Persona
  title?: string
  onClose: () => void
  onSave: (persona: Persona) => void | Promise<void>
}

const AXIS_OPTIONS: { value: PersonalityAxis; label: string; hint: string }[] = [
  {
    value: 'contrarian',
    label: '挑戰者',
    hint: '會質疑前提、提出反向觀點',
  },
  {
    value: 'balanced',
    label: '平衡型',
    hint: '視情境決定支持或挑戰',
  },
  {
    value: 'supportive',
    label: '共建者',
    hint: '把他人觀點接力放大',
  },
]

const LENS_FIELDS: Array<{
  key: keyof LensAffinities
  label: string
  desc: string
}> = [
  { key: 'empathy', label: '同理 (empathy)', desc: '從人的感受出發' },
  { key: 'structure', label: '結構 (structure)', desc: '把資訊歸納成模式' },
  { key: 'creativity', label: '創意 (creativity)', desc: '跨界類比、跳脫框架' },
  { key: 'feasibility', label: '可行 (feasibility)', desc: '評估資源與落地' },
]

function clamp(value: number): number {
  if (Number.isNaN(value)) return 0.5
  return Math.max(0, Math.min(1, value))
}

export function PersonaEditDialog({
  isOpen,
  initial,
  title = '編輯人設',
  onClose,
  onSave,
}: PersonaEditDialogProps) {
  const [draft, setDraft] = useState<Persona>(initial)
  const [error, setError] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setDraft(initial)
      setError('')
    }
  }, [isOpen, initial])

  const handleAffinity = (key: keyof LensAffinities, value: number) => {
    setDraft((prev) => ({
      ...prev,
      lens_affinities: {
        ...prev.lens_affinities,
        [key]: clamp(value),
      },
    }))
  }

  const handleSubmit = async () => {
    if (!draft.name.trim() || !draft.role.trim()) {
      setError('「姓名」和「角色」皆為必填。')
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

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidth="lg">
      <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
        <Input
          label="姓名"
          value={draft.name}
          onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
          placeholder="例：陳秀英"
          required
        />
        <Input
          label="角色／身分"
          value={draft.role}
          onChange={(e) => setDraft((prev) => ({ ...prev, role: e.target.value }))}
          placeholder="例：偏鄉家醫科診所護理師"
          required
        />

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-text">專長範圍</label>
          <textarea
            value={draft.expertise}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, expertise: e.target.value }))
            }
            placeholder="列 2-3 個具體會什麼，例：慢性病管理、長者衛教、社區外展"
            rows={2}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-text">背景（為什麼這個身分對主題有切角）</label>
          <textarea
            value={draft.backstory}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, backstory: e.target.value }))
            }
            placeholder="30 字內描述背景"
            rows={2}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-text">個性傾向</label>
          <div className="grid grid-cols-3 gap-2">
            {AXIS_OPTIONS.map((axis) => (
              <button
                key={axis.value}
                type="button"
                onClick={() =>
                  setDraft((prev) => ({ ...prev, personality_axis: axis.value }))
                }
                className={cn(
                  'rounded-lg border p-3 text-left text-sm transition-all cursor-pointer',
                  draft.personality_axis === axis.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
                )}
              >
                <div className="font-semibold">{axis.label}</div>
                <div className="mt-0.5 text-xs opacity-80">{axis.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-text">典型發言模式</label>
          <textarea
            value={draft.personality_desc}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, personality_desc: e.target.value }))
            }
            placeholder="一句話描述他/她在團隊裡通常怎麼發言"
            rows={2}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
          />
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border-light/60 p-3">
          <div className="text-sm font-medium text-text">認知透鏡強度</div>
          <p className="text-xs text-text-muted">
            0.0 ~ 1.0。AI 生成的分數通常已合理，僅在需要時手動微調。
          </p>
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

        {error && (
          <div className="rounded-md bg-error-bg px-3 py-2 text-sm text-error">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose} disabled={isSaving}>
            取消
          </Button>
          <Button className="flex-1" onClick={handleSubmit} isLoading={isSaving}>
            儲存
          </Button>
        </div>
      </div>
    </Modal>
  )
}
