import { Lightbulb, Lock } from 'lucide-react'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { ConstraintsField } from './ConstraintsField'
import type { StudyAutofillUI, StudyFieldKey } from '../../hooks/useStudyAutofill'
import {
  TimerConfigForm,
  type TimerMode,
} from '../timer/TimerConfigForm'

type MacroBudgets = {
  discover: number
  define: number
}
import { cn } from '../../lib/utils'
import type { AIContribution, TurnPolicy, UserRole } from '../../types/models'

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

// Phase 28 — 初始輪流規則（建立後仍可隨時切換）。
interface TurnPolicyOption {
  value: TurnPolicy
  label: string
  description: string
}

const TURN_POLICY_OPTIONS: TurnPolicyOption[] = [
  {
    value: 'cued',
    label: '點名',
    description: 'Supervisor 主導，點名指定成員回應',
  },
  {
    value: 'round_robin',
    label: '輪流',
    description: '依固定順序輪流發言，每人一次',
  },
  {
    value: 'open_floor',
    label: '搶答',
    description: '任何人可主動發言；學生可舉手優先',
  },
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
  turnPolicy: TurnPolicy
  onTurnPolicyChange: (next: TurnPolicy) => void
  timerMode: TimerMode
  onTimerModeChange: (next: TimerMode) => void
  customMacroBudgets: MacroBudgets
  onCustomMacroBudgetsChange: (next: MacroBudgets) => void
  teacherSignatureCode: string
  onTeacherSignatureCodeChange: (next: string) => void
  userRole?: UserRole
  /** Phase 43（spec/29）：study 幽靈代填的展示狀態；undefined = 非 study，行為照舊 */
  study?: StudyAutofillUI
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
  turnPolicy,
  onTurnPolicyChange,
  timerMode,
  onTimerModeChange,
  customMacroBudgets,
  onCustomMacroBudgetsChange,
  teacherSignatureCode,
  onTeacherSignatureCodeChange,
  userRole,
  study,
  error,
  onCancel,
  onNext,
  canAdvance,
}: Props) {
  // Phase 43：動畫中與鎖定後皆不可操作（語意層 readOnly/disabled，pointer-events 擋不住鍵盤）；
  // 僅鎖定後（動畫播畢）顯示 🔒。
  const isControlled = (field: StudyFieldKey): boolean =>
    !!study && (study.isAnimating || study.lockedFields.has(field))
  const isLocked = (field: StudyFieldKey): boolean => !!study?.lockedFields.has(field)
  const highlightCls = (field: StudyFieldKey): string =>
    study?.highlightTarget === field ? 'ring-2 ring-primary/60 animate-pulse rounded-lg' : ''
  const lockBadge = (field: StudyFieldKey) =>
    isLocked(field) ? (
      <Lock size={12} className="ml-1 inline-block align-middle text-text-muted" aria-label="實驗設定已鎖定" />
    ) : null

  return (
    // Phase 36 UIUX：寬版雙欄（6xl）— 左「設計題目＋邀請老師」/ 右「AI 團隊＋時間」。
    // 時間配置壓成單列、兩側欄位數量平均，盡量讓一頁看完少捲動。
    // banner、錯誤、按鈕皆整列 span。md 以下自動塌回單欄。
    <div className="grid grid-cols-1 gap-x-6 gap-y-5 md:grid-cols-2">
      <div className="md:col-span-2">
        <MindsetHintCard
          icon={<Lightbulb size={16} />}
          title="設計簡報"
          hint="開放任務簡報——只寫題目，不預設使用者族群或場域。"
        />
      </div>

      {/* 第 1 欄：你的設計題目 */}
      <div className="flex flex-col gap-5">
        <h3 className="text-sm font-semibold text-text">你的設計題目</h3>

        <div className={cn('flex flex-col gap-1', highlightCls('name'))}>
          <label className="text-sm font-medium text-text">
            設計專案名稱{lockBadge('name')}
          </label>
          <Input
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="例：重新設計大賣場購物車"
            required
            readOnly={isControlled('name')}
          />
        </div>

        <div className={cn('flex flex-col gap-1', highlightCls('description'))}>
          <label className="text-sm font-medium text-text">
            描述（選填）{lockBadge('description')}
          </label>
          <textarea
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder="簡述這個設計挑戰的脈絡、想關心的痛點…別急著預設使用者族群。"
            rows={3}
            readOnly={isControlled('description')}
            className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary read-only:bg-surface-hover"
          />
        </div>

        <ConstraintsField
          projectName={name}
          projectDescription={description}
          value={constraints}
          onChange={onConstraintsChange}
          helperText="建議方向，不是必填條件。讓 AI 幫你想到沒注意到的設計條件。"
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
      </div>

      {/* 第 2 欄：AI 團隊與對話設定 */}
      <div className="flex flex-col gap-5">
        <h3 className="text-sm font-semibold text-text">AI 團隊與對話設定</h3>

        <div className={cn('flex flex-col gap-2', highlightCls('turnPolicy'))}>
          <label className="text-sm font-medium text-text">
            對話模式（Turn-taking）{lockBadge('turnPolicy')}
          </label>
          <p className="text-xs text-text-muted">
            初始設定，建立後仍可隨時調整。控制 AI 與成員如何輪流發言。
          </p>
          <div className="flex gap-2">
            {TURN_POLICY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                disabled={isControlled('turnPolicy')}
                onClick={() => onTurnPolicyChange(opt.value)}
                className={cn(
                  'flex-1 rounded-lg border p-3 text-left text-sm transition-all cursor-pointer disabled:cursor-not-allowed',
                  turnPolicy === opt.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
                  isControlled('turnPolicy') && turnPolicy !== opt.value && 'opacity-40',
                )}
              >
                <div className="font-semibold">{opt.label}</div>
                <div className="mt-0.5 text-xs opacity-70">{opt.description}</div>
              </button>
            ))}
          </div>
        </div>

        <div className={cn('flex flex-col gap-2', highlightCls('aiCrewCount'))}>
          <label className="text-sm font-medium text-text">
            AI 組員人數{lockBadge('aiCrewCount')}
          </label>
          <p className="text-xs text-text-muted">
            每個設計專案固定有 1 位 AI 組長 + 1 位你（人類），再加上你選的 AI 組員。
          </p>
          <div className="flex gap-2">
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                type="button"
                disabled={isControlled('aiCrewCount')}
                onClick={() => onAiCrewCountChange(n)}
                className={cn(
                  'flex-1 rounded-lg border p-3 text-center text-sm transition-all cursor-pointer disabled:cursor-not-allowed',
                  aiCrewCount === n
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
                  isControlled('aiCrewCount') && aiCrewCount !== n && 'opacity-40',
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

        <div className={highlightCls('timerMode')}>
          <TimerConfigForm
            mode={timerMode}
            customMacroBudgets={customMacroBudgets}
            onModeChange={onTimerModeChange}
            onCustomChange={onCustomMacroBudgetsChange}
            disabled={isControlled('timerMode')}
            locked={isLocked('timerMode')}
          />
        </div>

        <div className={cn('flex flex-col gap-2', highlightCls('aiContribution'))}>
          <label className="text-sm font-medium text-text">
            AI 貢獻度{lockBadge('aiContribution')}
          </label>
          <p className="text-xs text-text-muted">
            你希望 AI 在這次專案中扮演多重的角色？
          </p>
          <div className="flex gap-2">
            {AI_LEVELS.map((level) => (
              <button
                key={level.value}
                type="button"
                disabled={isControlled('aiContribution')}
                onClick={() => onAiContributionChange(level.value)}
                className={cn(
                  'flex-1 rounded-lg border p-3 text-left text-sm transition-all cursor-pointer disabled:cursor-not-allowed',
                  aiContribution === level.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
                  isControlled('aiContribution') && aiContribution !== level.value && 'opacity-40',
                )}
              >
                <div className="font-semibold">{level.label}</div>
                <div className="mt-0.5 text-xs opacity-70">{level.description}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error md:col-span-2">
          {error}
        </div>
      )}

      {/* Phase 28 narrative：建立期待，讓使用者預知下一步在幹什麼 */}
      <p className="text-center text-xs text-text-muted md:col-span-2">
        接下來會請 AI 為你列出可能的設計對象，你來挑選誰最值得設計。
      </p>
      {/* 行動列固定貼底（sticky）：表單再長，「下一步」永遠看得到 */}
      <div className="sticky bottom-0 z-10 -mx-6 -mb-6 flex gap-3 border-t border-border bg-surface px-6 py-4 md:col-span-2">
        <Button variant="secondary" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button className="flex-1" onClick={onNext} disabled={!canAdvance}>
          下一步：找出你的設計對象 →
        </Button>
      </div>
    </div>
  )
}
