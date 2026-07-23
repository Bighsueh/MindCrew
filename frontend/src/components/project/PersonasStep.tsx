import { Compass, Loader2, Sparkles, UserRound } from 'lucide-react'
import { Button } from '../common/Button'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { RotatingText } from '../common/RotatingText'
import { PersonaCard } from '../persona/PersonaCard'
import { cn } from '../../lib/utils'
import type { Persona, StakeholderSuggestion } from '../../types/models'

interface Props {
  selectedStakeholders: StakeholderSuggestion[]
  aiCrewCount: number
  personas: Persona[]
  isGenerating: boolean
  isCreating: boolean
  /** 保留 prop 相容性，不再顯示於畫面 */
  progressLog: string[]
  error?: string
  onGenerate: () => void
  onEdit: (index: number) => void
  onBack: () => void
  onSubmit: () => void
  canSubmit: boolean
}

export function PersonasStep({
  selectedStakeholders,
  aiCrewCount,
  personas,
  isGenerating,
  isCreating,
  error,
  onGenerate,
  onEdit,
  onBack,
  onSubmit,
  canSubmit,
}: Props) {
  const slotCount = Math.max(aiCrewCount, selectedStakeholders.length, personas.length)
  const slots = Array.from({ length: slotCount }).map((_, idx) => ({
    stakeholder: selectedStakeholders[idx],
    persona: personas[idx],
    index: idx,
  }))

  const allDone = personas.length === aiCrewCount

  return (
    <div className="flex flex-col gap-4">
      <MindsetHintCard
        icon={<Compass size={16} />}
        title="把他們請進團隊"
        hint={`你剛挑的 ${selectedStakeholders.length} 位利害關係人，會被一對一實體化為有個性的 AI 隊友。每位隊友會用該角色的視角陪你想設計。`}
      />

      {/* 生成按鈕 */}
      <div className="flex flex-wrap gap-2">
        <Button
          onClick={onGenerate}
          isLoading={isGenerating}
          disabled={isCreating}
          className={cn(isGenerating && 'w-full justify-center')}
          variant={allDone && !isGenerating ? 'secondary' : 'primary'}
        >
          <Sparkles size={14} />
          {personas.length === 0 ? `由 AI 生成 ${aiCrewCount} 位隊友` : '重新生成'}
        </Button>
      </div>

      {/* 2欄 TransformCard 格局 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {slots.map(({ stakeholder, persona, index }) => (
          <TransformCard
            key={`pair-${index}`}
            slotIndex={index}
            stakeholder={stakeholder}
            persona={persona}
            isGenerating={isGenerating && !persona}
            isCreating={isCreating}
            onEdit={() => onEdit(index)}
          />
        ))}
      </div>

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">{error}</div>
      )}

      {/* 行動列固定貼底（sticky），無論內容多長都看得到「建立」按鈕 */}
      <div className="sticky bottom-0 z-10 -mx-6 -mb-6 flex gap-3 border-t border-border bg-surface px-6 py-4">
        <Button variant="secondary" className="flex-1" onClick={onBack} disabled={isCreating}>
          上一步
        </Button>
        <Button
          className="flex-1"
          onClick={onSubmit}
          isLoading={isCreating}
          disabled={isGenerating || !canSubmit}
          title={allDone ? undefined : `還差 ${aiCrewCount - personas.length} 位 Crew 才能建立`}
        >
          {allDone
            ? '建立設計專案'
            : `建立設計專案（${personas.length}/${aiCrewCount}）`}
        </Button>
      </div>
    </div>
  )
}

// ── TransformCard：Stakeholder → Persona 垂直轉化卡 ────────────────────────

interface TransformCardProps {
  slotIndex: number
  stakeholder?: StakeholderSuggestion
  persona?: Persona
  isGenerating: boolean
  isCreating: boolean
  onEdit: () => void
}

function TransformCard({
  slotIndex,
  stakeholder,
  persona,
  isGenerating,
  isCreating,
  onEdit,
}: TransformCardProps) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border-light bg-surface shadow-sm">
      {/* 上半：Stakeholder 來源 */}
      <div className="bg-bg-warm/60 px-4 py-3">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          <UserRound size={10} className="shrink-0" />
          利害關係人
        </div>
        {stakeholder ? (
          <>
            <div className="mt-1 truncate text-sm font-semibold text-text" title={stakeholder.name}>
              {stakeholder.name}
            </div>
            <div className="text-xs text-text-muted">{stakeholder.role}</div>
            {stakeholder.relevance && (
              <p
                className="mt-0.5 line-clamp-2 text-[11px] italic text-text-muted/80"
                title={stakeholder.relevance}
              >
                {stakeholder.relevance}
              </p>
            )}
          </>
        ) : (
          <div className="mt-1 text-sm text-text-muted">未指定來源 · Crew {slotIndex + 1}</div>
        )}
      </div>

      {/* 分隔線：帶「↓ AI 轉化」標籤 */}
      <div className="flex items-center gap-2 border-y border-border-light bg-surface px-3 py-1">
        <div className="flex-1 h-px bg-border-light" />
        <span className="text-[10px] text-text-muted whitespace-nowrap">↓ AI 轉化</span>
        <div className="flex-1 h-px bg-border-light" />
      </div>

      {/* 下半：AI 隊友 */}
      <div className="flex-1 p-3">
        {persona ? (
          <div className="animate-stagger-in">
            <PersonaCard persona={persona} index={slotIndex} onEdit={onEdit} />
          </div>
        ) : (
          <PersonaSlotPlaceholder
            slotIndex={slotIndex}
            stakeholder={stakeholder}
            isGenerating={isGenerating}
            isCreating={isCreating}
          />
        )}
      </div>
    </div>
  )
}

// ── Loading / 等待 placeholder ──────────────────────────────────────────────

function PersonaSlotPlaceholder({
  slotIndex,
  stakeholder,
  isGenerating,
  isCreating,
}: {
  slotIndex: number
  stakeholder?: StakeholderSuggestion
  isGenerating: boolean
  isCreating: boolean
}) {
  const generatingPhrases = [
    `理解「${stakeholder?.name ?? `Crew ${slotIndex + 1}`}」的視角…`,
    '建構 AI 人格特質…',
    '設定與設計題目的關係…',
    '即將完成…',
  ]

  if (isGenerating) {
    return (
      <div className="flex min-h-[100px] flex-col items-center justify-center gap-2 rounded-lg border border-primary/30 bg-primary/5 p-4">
        <Loader2 size={16} className="animate-spin text-primary" />
        <RotatingText
          phrases={generatingPhrases}
          interval={1800}
          className={cn('text-xs text-primary/80 text-center justify-center')}
        />
      </div>
    )
  }

  if (isCreating) {
    return (
      <div className="flex min-h-[100px] items-center justify-center rounded-lg border border-dashed border-border-light bg-surface/40 p-4">
        <span className="text-xs text-text-muted opacity-60">建立中…</span>
      </div>
    )
  }

  return (
    <div className="flex min-h-[100px] items-center justify-center rounded-lg border border-dashed border-border-light bg-surface/40 p-4 text-center">
      <div>
        <div className="text-xs font-medium text-text">等待生成</div>
        <div className="mt-0.5 text-[11px] text-text-muted opacity-70">按上方「由 AI 生成」</div>
      </div>
    </div>
  )
}
