import { cn } from '../../lib/utils'
import type { StageDistribution } from '../../types/models'

interface StageDistributionBarProps {
  distribution: StageDistribution
}

const STAGES = [
  { key: 'discover' as const, label: 'Discover', color: 'bg-primary' },
  { key: 'define' as const, label: 'Define', color: 'bg-accent' },
  { key: 'develop' as const, label: 'Develop', color: 'bg-warning' },
  { key: 'deliver' as const, label: 'Deliver', color: 'bg-success' },
  { key: 'completed' as const, label: '完成', color: 'bg-success/60' },
]

export function StageDistributionBar({ distribution }: StageDistributionBarProps) {
  const total = Object.values(distribution).reduce((sum, v) => sum + v, 0)

  if (total === 0) return null

  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-text mb-3">全班進度分佈</h3>

      <div className="flex h-6 w-full overflow-hidden rounded-full bg-bg">
        {STAGES.map(({ key, color }) => {
          const count = distribution[key]
          if (count === 0) return null
          const pct = (count / total) * 100
          return (
            <div
              key={key}
              className={cn(color, 'flex items-center justify-center text-xs font-medium text-text-inverse')}
              style={{ width: `${pct}%` }}
              title={`${key}: ${count} 組`}
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
