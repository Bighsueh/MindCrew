import { cn } from '../../lib/utils'
import type { DTStage } from '../../types/models'
import { STAGE_LABELS_PLAIN } from '../../utils/formatters'

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
// Phase 42 補正 R2：改吃 STAGE_LABELS_PLAIN 單一真相來源（spec 28 §6，學生面零英文）。
const PHASE_LABELS: Record<DTStage, string> = STAGE_LABELS_PLAIN

const PHASE_COLORS: Record<DTStage, string> = {
  warmup: 'bg-warning/15 text-warning',
  discover: 'bg-primary/10 text-primary',
  define: 'bg-accent/20 text-accent',
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
