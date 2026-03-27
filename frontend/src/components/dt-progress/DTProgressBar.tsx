import type { DTStage } from '../../types/models'

interface DTProgressBarProps {
  currentStage: DTStage
  onStageClick?: (stage: DTStage) => void
}

const STAGES: Array<{ key: DTStage; label: string; emoji: string; description: string }> = [
  { key: 'discover', label: '發現', emoji: '🔍', description: 'Discover' },
  { key: 'define', label: '定義', emoji: '📌', description: 'Define' },
  { key: 'develop', label: '發展', emoji: '💡', description: 'Develop' },
  { key: 'deliver', label: '交付', emoji: '🚀', description: 'Deliver' },
]

const STAGE_ORDER: DTStage[] = ['discover', 'define', 'develop', 'deliver', 'completed']

function getStageIndex(stage: DTStage): number {
  return STAGE_ORDER.indexOf(stage)
}

export function DTProgressBar({ currentStage, onStageClick }: DTProgressBarProps) {
  const currentIdx = getStageIndex(currentStage)
  const isAllCompleted = currentStage === 'completed'

  return (
    <div className="flex items-center gap-0 w-full">
      {STAGES.map((stage, idx) => {
        const stageIdx = getStageIndex(stage.key)
        const isCompleted = isAllCompleted || stageIdx < currentIdx
        const isCurrent = !isAllCompleted && stage.key === currentStage

        return (
          <div key={stage.key} className="flex flex-1 items-center">
            {/* Stage node */}
            <button
              onClick={() => isCompleted && onStageClick?.(stage.key)}
              className={[
                'flex flex-col items-center gap-1 flex-1 py-2 px-3 rounded-lg transition-all duration-200',
                isCurrent
                  ? 'bg-blue-600 text-white shadow-md scale-105'
                  : isCompleted
                    ? 'bg-green-100 text-green-700 cursor-pointer hover:bg-green-200'
                    : 'bg-gray-100 text-gray-400 cursor-default',
              ].join(' ')}
              disabled={!isCompleted}
            >
              <span className="text-lg leading-none">{stage.emoji}</span>
              <div className="text-center">
                <p className="text-xs font-semibold">{stage.label}</p>
                <p className={['text-xs', isCurrent ? 'text-blue-100' : 'opacity-70'].join(' ')}>
                  {stage.description}
                </p>
              </div>
              {isCompleted && !isCurrent && (
                <span className="text-xs">✓</span>
              )}
              {isCurrent && (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
              )}
            </button>

            {/* Connector */}
            {idx < STAGES.length - 1 && (
              <div
                className={[
                  'h-1 w-4 flex-shrink-0 mx-1 rounded-full',
                  isCompleted ? 'bg-green-400' : 'bg-gray-200',
                ].join(' ')}
              />
            )}
          </div>
        )
      })}

      {isAllCompleted && (
        <div className="ml-3 rounded-full bg-green-600 px-3 py-1 text-xs font-semibold text-white">
          完成！
        </div>
      )}
    </div>
  )
}
