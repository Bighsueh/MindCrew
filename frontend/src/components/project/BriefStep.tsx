import { Lightbulb } from 'lucide-react'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { ConstraintsField } from './ConstraintsField'
import {
  TimerConfigForm,
  type TimerMode,
} from '../timer/TimerConfigForm'

type MacroBudgets = {
  discover: number
  define: number
  develop: number
  deliver: number
}
import { cn } from '../../lib/utils'
import type { AIContribution, UserRole } from '../../types/models'

/**
 * Phase 27 Step 1：設計簡報。
 *
 * 純展示元件——所有 state 仍由 CreateProjectDialog 持有，這裡只負責 UI。
 */
interface AiLevel {
  value: AIContribution
  label: string
  description: string
}

const AI_LEVELS: AiLevel[] = [
  { value: 'low', label: '低', description: 'AI 輔助較少，以人類主導' },
  { value: 'medium', label: '中', description: 'AI 與人類均衡協作' },
  { value: 'high', label: '高', description: 'AI 積極參與，提供大量洞察' },
]

interface Props {
  name: string
  onNameChange: (next: string) => void
  description: string
  onDescriptionChange: (next: string) => void
  constraints: string
  onConstraintsChange: (next: string) => void
  aiContribution: AIContribution
  onAiContributionChange: (next: AIContribution) => void
  aiCrewCount: number
  onAiCrewCountChange: (next: number) => void
  timerMode: TimerMode
  onTimerModeChange: (next: TimerMode) => void
  customMacroBudgets: MacroBudgets
  onCustomMacroBudgetsChange: (next: MacroBudgets) => void
  teacherSignatureCode: string
  onTeacherSignatureCodeChange: (next: string) => void
  userRole?: UserRole
  error?: string
  onCancel: () => void
  onNext: () => void
  canAdvance: boolean
}

export function BriefStep({
  name,
  onNameChange,
  description,
  onDescriptionChange,
  constraints,
  onConstraintsChange,
  aiContribution,
  onAiContributionChange,
  aiCrewCount,
  onAiCrewCountChange,
  timerMode,
  onTimerModeChange,
  customMacroBudgets,
  onCustomMacroBudgetsChange,
  teacherSignatureCode,
  onTeacherSignatureCodeChange,
  userRole,
  error,
  onCancel,
  onNext,
  canAdvance,
}: Props) {
  return (
    <div className="flex flex-col gap-5">
      <MindsetHintCard
        icon={<Lightbulb size={16} />}
        title="設計簡報"
        hint="開放任務簡報——只寫題目，不預設使用者族群或場域。"
      />
      <Input
        label="設計專案名稱"
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="例：重新設計大賣場購物車"
        required
      />

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text">描述（選填）</label>
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder="簡述這個設計挑戰的脈絡、想關心的痛點…別急著預設使用者族群。"
          rows={3}
          className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
        />
      </div>

      <ConstraintsField
        projectName={name}
        projectDescription={description}
        value={constraints}
        onChange={onConstraintsChange}
        helperText="建議方向，不是必填條件。讓 AI 幫你想到沒注意到的設計條件。"
      />

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text">AI 貢獻度</label>
        <p className="text-xs text-text-muted">
          你希望 AI 在這次專案中扮演多重的角色？
        </p>
        <div className="flex gap-2">
          {AI_LEVELS.map((level) => (
            <button
              key={level.value}
              type="button"
              onClick={() => onAiContributionChange(level.value)}
              className={cn(
                'flex-1 rounded-lg border p-3 text-left text-sm transition-all cursor-pointer',
                aiContribution === level.value
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
              )}
            >
              <div className="font-semibold">{level.label}</div>
              <div className="mt-0.5 text-xs opacity-70">{level.description}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text">AI 組員人數</label>
        <p className="text-xs text-text-muted">
          每個設計專案固定有 1 位 AI 組長 + 1 位你（人類），再加上你選的 AI 組員。
        </p>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => onAiCrewCountChange(n)}
              className={cn(
                'flex-1 rounded-lg border p-3 text-center text-sm transition-all cursor-pointer',
                aiCrewCount === n
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
              )}
            >
              <div className="text-base font-semibold">{n}</div>
              <div className="mt-0.5 text-[11px] opacity-70">AI 組員</div>
            </button>
          ))}
        </div>
        <div className="rounded-md bg-bg-warm/60 px-3 py-2 text-xs text-text-muted">
          組合預覽：組長 1（AI）+ 組員 {aiCrewCount}（AI）+ 你 1（人類）={' '}
          <span className="font-semibold text-text">共 {aiCrewCount + 2} 人</span>
        </div>
      </div>

      <TimerConfigForm
        mode={timerMode}
        customMacroBudgets={customMacroBudgets}
        onModeChange={onTimerModeChange}
        onCustomChange={onCustomMacroBudgetsChange}
      />

      {userRole === 'student' && (
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-text">
            邀請老師指導（選填）
          </label>
          <p className="text-xs text-text-muted">
            輸入老師代碼，設計專案建立後就會出現在他的儀表板。
          </p>
          <Input
            value={teacherSignatureCode}
            onChange={(e) =>
              onTeacherSignatureCodeChange(e.target.value.toUpperCase())
            }
            placeholder="老師代碼，例：MD7K2A"
            className="font-mono uppercase tracking-widest"
            maxLength={8}
          />
        </div>
      )}

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button className="flex-1" onClick={onNext} disabled={!canAdvance}>
          下一步：利害關係人地圖
        </Button>
      </div>
    </div>
  )
}
