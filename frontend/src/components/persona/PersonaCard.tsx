import { Pencil, RefreshCw, Trash2 } from 'lucide-react'
import type { Persona } from '../../types/models'
import { cn } from '../../lib/utils'

interface PersonaCardProps {
  persona: Persona
  index?: number
  onEdit?: () => void
  onRegenerate?: () => void
  onDelete?: () => void
  isBusy?: boolean
}

const AXIS_LABEL: Record<Persona['personality_axis'], string> = {
  contrarian: '挑戰者',
  balanced: '平衡型',
  supportive: '共建者',
}

const AXIS_TONE: Record<Persona['personality_axis'], string> = {
  contrarian: 'bg-warning/10 text-warning',
  balanced: 'bg-info/10 text-info',
  supportive: 'bg-success/10 text-success',
}

const LENS_LABEL: Record<keyof Persona['lens_affinities'], string> = {
  empathy: '同理',
  structure: '結構',
  creativity: '創意',
  feasibility: '可行',
}

function LensBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="flex items-center gap-2 text-xs text-text-muted">
      <span className="w-10 shrink-0">{label}</span>
      <div className="flex-1 rounded-full bg-border-light/60 overflow-hidden h-1.5">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right tabular-nums">
        {value.toFixed(2)}
      </span>
    </div>
  )
}

export function PersonaCard({
  persona,
  index,
  onEdit,
  onRegenerate,
  onDelete,
  isBusy = false,
}: PersonaCardProps) {
  const axisLabel = AXIS_LABEL[persona.personality_axis]
  const axisTone = AXIS_TONE[persona.personality_axis]

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border-light bg-surface p-4 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {index !== undefined && (
              <span className="text-xs font-medium text-text-muted">
                Crew {index + 1}
              </span>
            )}
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                axisTone,
              )}
            >
              {axisLabel}
            </span>
          </div>
          <h3 className="mt-1 text-base font-semibold text-text truncate">
            {persona.name}
          </h3>
          <p className="text-sm text-text-muted truncate">{persona.role}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={isBusy}
              title="重新生成"
              className="rounded-md p-1.5 text-text-muted hover:bg-bg-warm hover:text-text disabled:opacity-50"
            >
              <RefreshCw size={14} />
            </button>
          )}
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              disabled={isBusy}
              title="編輯人設"
              className="rounded-md p-1.5 text-text-muted hover:bg-bg-warm hover:text-text disabled:opacity-50"
            >
              <Pencil size={14} />
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              disabled={isBusy}
              title="刪除"
              className="rounded-md p-1.5 text-text-muted hover:bg-error/10 hover:text-error disabled:opacity-50"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </header>

      {persona.backstory && (
        <p className="text-xs leading-relaxed text-text-muted line-clamp-2">
          {persona.backstory}
        </p>
      )}

      <div className="flex flex-col gap-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          專長
        </div>
        <p className="text-sm text-text leading-snug">{persona.expertise}</p>
      </div>

      {persona.personality_desc && (
        <div className="flex flex-col gap-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            個性特質
          </div>
          <p className="text-sm text-text leading-snug">
            {persona.personality_desc}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-1 pt-1 border-t border-border-light/60">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          認知透鏡
        </div>
        <div className="flex flex-col gap-1">
          {(Object.keys(LENS_LABEL) as Array<keyof Persona['lens_affinities']>).map(
            (lens) => (
              <LensBar
                key={lens}
                label={LENS_LABEL[lens]}
                value={persona.lens_affinities[lens]}
              />
            ),
          )}
        </div>
      </div>
    </div>
  )
}
