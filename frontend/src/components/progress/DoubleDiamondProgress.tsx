import type { DTStage, MicroPhaseId } from '../../types/models'
import { cn } from '../../lib/utils'

const PHASES: { key: Exclude<DTStage, 'completed'>; label: string; type: 'diverge' | 'converge' }[] = [
  { key: 'discover', label: 'Discover', type: 'diverge' },
  { key: 'define', label: 'Define', type: 'converge' },
  { key: 'develop', label: 'Develop', type: 'diverge' },
  { key: 'deliver', label: 'Deliver', type: 'converge' },
]

const PHASE_ORDER: Record<string, number> = {
  discover: 0, define: 1, develop: 2, deliver: 3, completed: 4,
}

const MICRO_PHASE_ORDER: MicroPhaseId[] = [
  "1.1", "1.2", "1.3",
  "2.1", "2.2", "2.3",
  "3.1", "3.2", "3.3",
  "4.1", "4.2", "4.3",
]

const MACRO_TO_MICRO: Record<string, [MicroPhaseId, MicroPhaseId, MicroPhaseId]> = {
  discover: ["1.1", "1.2", "1.3"],
  define:   ["2.1", "2.2", "2.3"],
  develop:  ["3.1", "3.2", "3.3"],
  deliver:  ["4.1", "4.2", "4.3"],
}

interface DoubleDiamondProgressProps {
  currentStage: DTStage
  currentMicroPhase?: MicroPhaseId
  onPhaseClick?: (stage: DTStage) => void
}

export function DoubleDiamondProgress({ currentStage, currentMicroPhase, onPhaseClick }: DoubleDiamondProgressProps) {
  const currentIdx = PHASE_ORDER[currentStage] ?? 0
  const isAllCompleted = currentStage === 'completed'

  return (
    <div className="flex items-center justify-center gap-1">
      {PHASES.map((phase, idx) => {
        const isCompleted = isAllCompleted || idx < currentIdx
        const isCurrent = !isAllCompleted && phase.key === currentStage
        const isFuture = !isAllCompleted && idx > currentIdx

        return (
          <button
            key={phase.key}
            onClick={() => isCompleted && onPhaseClick?.(phase.key)}
            disabled={!isCompleted}
            className={cn(
              'group relative flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-all',
              isCompleted && 'bg-accent/15 text-accent hover:bg-accent/25 cursor-pointer',
              isCurrent && 'bg-accent text-white shadow-md',
              isFuture && 'bg-secondary/30 text-text-muted cursor-default',
            )}
          >
            <span
              className={cn(
                'inline-block h-2.5 w-2.5 rotate-45 rounded-sm',
                isCompleted && 'bg-accent',
                isCurrent && 'bg-white animate-pulse',
                isFuture && 'bg-text-muted/40',
              )}
            />
            <span className="hidden sm:inline">{phase.label}</span>
            <span className="sm:hidden">{phase.label.slice(0, 3)}</span>
            <span className="hidden text-xs opacity-60 lg:inline">
              {phase.type === 'diverge' ? '◇' : '◆'}
            </span>
            {currentMicroPhase && (
              <div className="flex gap-1 mt-1">
                {MACRO_TO_MICRO[phase.key]?.map((mp) => {
                  const microIdx = MICRO_PHASE_ORDER.indexOf(mp)
                  const currentIdx = MICRO_PHASE_ORDER.indexOf(currentMicroPhase)
                  const isMicroCompleted = microIdx < currentIdx
                  const isMicroCurrent = mp === currentMicroPhase
                  return (
                    <div
                      key={mp}
                      className={cn(
                        "w-1.5 h-1.5 rounded-full transition-all",
                        isMicroCompleted && "bg-accent",
                        isMicroCurrent && "bg-accent animate-pulse",
                        !isMicroCompleted && !isMicroCurrent && "bg-secondary/40",
                      )}
                    />
                  )
                })}
              </div>
            )}
          </button>
        )
      })}

      {isAllCompleted && (
        <span className="ml-2 rounded-full bg-success/15 px-3 py-1 text-xs font-semibold text-success">
          完成
        </span>
      )}
    </div>
  )
}
