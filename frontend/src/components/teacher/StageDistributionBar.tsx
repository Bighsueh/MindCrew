import { cn } from '../../lib/utils'
import type { StageDistribution } from '../../types/models'
import { STAGE_LABELS_PLAIN } from '../../utils/formatters'

interface StageDistributionBarProps {
  distribution: StageDistribution
}

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
// Phase 42 補正 R2（裁定②）：教師面一併去英文 map，吃 STAGE_LABELS_PLAIN（spec 28 §6）。
const STAGES = [
  { key: 'discover' as const, label: STAGE_LABELS_PLAIN.discover, color: 'bg-primary' },
  { key: 'define' as const, label: STAGE_LABELS_PLAIN.define, color: 'bg-accent' },
  { key: 'completed' as const, label: STAGE_LABELS_PLAIN.completed, color: 'bg-success/60' },
]

export function StageDistributionBar({ distribution }: StageDistributionBarProps) {
  const total = Object.values(distribution).reduce((sum, v) => sum + v, 0)

  if (total === 0) return null

  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-text mb-3">全班進度分佈</h3>

      <div className="flex h-6 w-full overflow-hidden rounded-full bg-bg">
        {STAGES.map(({ key, label, color }) => {
          const count = distribution[key]
          if (count === 0) return null
          const pct = (count / total) * 100
          return (
            <div
              key={key}
              className={cn(color, 'flex items-center justify-center text-xs font-medium text-text-inverse')}
              style={{ width: `${pct}%` }}
              title={`${label}: ${count} 組`}
            >
              {pct >= 15 ? count : ''}
            </div>
          )
        })}
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-muted">
        {STAGES.map(({ key, label, color }) => {
          const count = distribution[key]
          if (count === 0) return null
          return (
            <span key={key} className="flex items-center gap-1.5">
              <span className={cn('inline-block h-2.5 w-2.5 rounded-full', color)} />
              {label}: {count}
            </span>
          )
        })}
      </div>
    </div>
  )
}
