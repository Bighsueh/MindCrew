import { Users } from 'lucide-react'
import { Button } from '../common/Button'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { StakeholderPicker } from './StakeholderPicker'
import type { StakeholderSuggestion } from '../../types/models'

/**
 * Phase 27 Step 2：利害關係人地圖。
 *
 * Phase 28 narrative refactor：文案改成引導式問句，明確點出「勾選的這些
 * 人會化身為 AI 隊友」的因果連結，幫助使用者建立 stakeholder → persona
 * 的心智模型。
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
  const remaining = requiredCount - selected.length
  return (
    <div className="flex flex-col gap-4">
      <MindsetHintCard
        icon={<Users size={16} />}
        title="這個設計是為了誰？"
        hint="先想想誰會用、誰會反對、誰會受影響。你勾選的這幾位等下會化身為 AI 隊友，從他們的視角陪你想設計。"
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

      {/* 行動列固定貼底（sticky）：內容再長，「下一步」永遠看得到 */}
      <div className="sticky bottom-0 z-10 -mx-6 -mb-6 flex gap-3 border-t border-border bg-surface px-6 py-4">
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
              : `還差 ${remaining} 位才能進下一步`
          }
        >
          {canAdvance
            ? `下一步：把這 ${requiredCount} 位請進團隊 →`
            : `下一步：把這 ${requiredCount} 位請進團隊`}
        </Button>
      </div>
    </div>
  )
}
