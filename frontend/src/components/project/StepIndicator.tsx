import { cn } from '../../lib/utils'

export type WizardStep = 'brief' | 'stakeholders' | 'personas'

// Phase 28 — 把步驟改成動詞性敘事弧，讓使用者感覺「正在前進」而不是「填三張表」。
// 故事比喻：「先描述題目 → 找出對的人 → 讓他們進團隊」。
const STEP_LABELS: Record<WizardStep, string> = {
  brief: '1. 描述你的設計挑戰',
  stakeholders: '2. 找出你的設計對象',
  personas: '3. 把他們請進團隊',
}

const STEPS: WizardStep[] = ['brief', 'stakeholders', 'personas']

/** 精靈 Modal 標題（與步驟敘事同源維護） */
export const WIZARD_TITLES: Record<WizardStep, string> = {
  brief: '建立新設計專案',
  stakeholders: '這個設計是為了誰？',
  personas: '把他們請進團隊',
}

interface StepIndicatorProps {
  current: WizardStep
}

export function StepIndicator({ current }: StepIndicatorProps) {
  const currentIdx = STEPS.indexOf(current)
  return (
    <div className="flex items-center gap-1.5 text-xs font-medium flex-wrap">
      {STEPS.map((s, idx) => {
        const isCurrent = s === current
        const isDone = idx < currentIdx
        return (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span
              className={cn(
                'rounded-full px-3 py-1',
                isCurrent
                  ? 'bg-primary text-text-inverse'
                  : isDone
                    ? 'bg-success/10 text-success'
                    : 'bg-bg-warm text-text-muted',
              )}
            >
              {STEP_LABELS[s]}
            </span>
            {idx < STEPS.length - 1 && (
              <span className="text-text-muted">→</span>
            )}
          </span>
        )
      })}
    </div>
  )
}
