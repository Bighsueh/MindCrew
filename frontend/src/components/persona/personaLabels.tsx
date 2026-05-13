import type { Persona } from '../../types/models'
import { cn } from '../../lib/utils'

export const AXIS_LABEL: Record<Persona['personality_axis'], string> = {
  contrarian: '挑戰者',
  balanced: '平衡型',
  supportive: '共建者',
}

export const AXIS_TONE: Record<Persona['personality_axis'], string> = {
  contrarian: 'bg-warning/10 text-warning',
  balanced: 'bg-info/10 text-info',
  supportive: 'bg-success/10 text-success',
}

export const LENS_LABEL: Record<keyof Persona['lens_affinities'], string> = {
  empathy: '同理',
  structure: '結構',
  creativity: '創意',
  feasibility: '可行',
}

interface LensBarProps {
  label: string
  value: number
  /** compact=true：popover 場景用的較細條 + 較小字 */
  compact?: boolean
}

export function LensBar({ label, value, compact = false }: LensBarProps) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div
      className={cn(
        'flex items-center gap-2 text-text-muted',
        compact ? 'text-[11px]' : 'text-xs',
      )}
    >
      <span className={cn('shrink-0', compact ? 'w-8' : 'w-10')}>{label}</span>
      <div
        className={cn(
          'flex-1 overflow-hidden rounded-full bg-border-light/60',
          compact ? 'h-1' : 'h-1.5',
        )}
      >
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={cn(
          'shrink-0 text-right tabular-nums',
          compact ? 'w-8' : 'w-9',
        )}
      >
        {value.toFixed(2)}
      </span>
    </div>
  )
}
