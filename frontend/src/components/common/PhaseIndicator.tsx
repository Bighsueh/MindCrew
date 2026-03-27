import { cn } from '../../lib/utils'
import type { DTStage } from '../../types/models'

const PHASE_LABELS: Record<DTStage, string> = {
  discover: 'Discover',
  define: 'Define',
  develop: 'Develop',
  deliver: 'Deliver',
  completed: '完成',
}

const PHASE_COLORS: Record<DTStage, string> = {
  discover: 'bg-primary/10 text-primary',
  define: 'bg-accent/20 text-accent',
  develop: 'bg-warning/20 text-warning',
  deliver: 'bg-success/20 text-success',
  completed: 'bg-success/20 text-success',
}

interface PhaseIndicatorProps {
  phase: DTStage
  className?: string
}

export function PhaseIndicator({ phase, className }: PhaseIndicatorProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
        PHASE_COLORS[phase],
        className
      )}
    >
      {PHASE_LABELS[phase]}
    </span>
  )
}
