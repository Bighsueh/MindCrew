import { Users } from 'lucide-react'
import { Button } from '../common/Button'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { StakeholderPicker } from './StakeholderPicker'
import type { StakeholderSuggestion } from '../../types/models'

/**
 * Phase 27 Step 2：利害關係人地圖。
 */
interface Props {
  suggestions: StakeholderSuggestion[]
  selected: StakeholderSuggestion[]
  onChange: (next: StakeholderSuggestion[]) => void
  requiredCount: number
  isLoading: boolean
  onRefetch: () => void
  error?: string
  onBack: () => void
  onNext: () => void
  canAdvance: boolean
}

export function StakeholdersStep({
  suggestions,
  selected,
  onChange,
  requiredCount,
  isLoading,
  onRefetch,
  error,
  onBack,
  onNext,
  canAdvance,
}: Props) {
  return (
    <div className="flex flex-col gap-4">
      <MindsetHintCard
        icon={<Users size={16} />}
        title="利害關係人地圖"
        hint="從 AI 建議的人裡，挑你想去訪談、想派出當 AI 隊友的對象。"
      />
      <StakeholderPicker
        suggestions={suggestions}
        selected={selected}
        onChange={onChange}
        requiredCount={requiredCount}
        isLoading={isLoading}
        onRefetch={onRefetch}
      />

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <Button variant="secondary" className="flex-1" onClick={onBack}>
          上一步
        </Button>
        <Button
          className="flex-1"
          onClick={onNext}
          disabled={!canAdvance}
          title={
            canAdvance
              ? undefined
              : `還差 ${requiredCount - selected.length} 位才能進下一步`
          }
        >
          下一步：設計 AI 隊友
        </Button>
      </div>
    </div>
  )
}
