import { Compass, Loader2, Plus, RotateCcw, Sparkles } from 'lucide-react'
import { Button } from '../common/Button'
import { MindsetHintCard } from '../common/MindsetHintCard'
import { PersonaCard } from '../persona/PersonaCard'
import type { Persona } from '../../types/models'

/**
 * Phase 27 Step 3：設計 AI 隊友。
 *
 * 純展示元件——所有 state 仍由 CreateProjectDialog 持有。
 */
interface Props {
  selectedStakeholderCount: number
  aiCrewCount: number
  personas: Persona[]
  isGenerating: boolean
  isCreating: boolean
  progressLog: string[]
  error?: string
  onGenerate: () => void
  onClear: () => void
  onManualAdd: () => void
  onEdit: (index: number) => void
  onDelete: (index: number) => void
  onBack: () => void
  onSubmit: () => void
  canSubmit: boolean
}

export function PersonasStep({
  selectedStakeholderCount,
  aiCrewCount,
  personas,
  isGenerating,
  isCreating,
  progressLog,
  error,
  onGenerate,
  onClear,
  onManualAdd,
  onEdit,
  onDelete,
  onBack,
  onSubmit,
  canSubmit,
}: Props) {
  return (
    <div className="flex flex-col gap-4">
      <MindsetHintCard
        icon={<Compass size={16} />}
        title="設計 AI 隊友"
        hint="勾選的利害關係人會被實體化為有個性的 AI 隊友。"
      />
      <div className="rounded-lg border border-border-light bg-bg-warm/40 p-4 text-sm leading-relaxed text-text-muted">
        基於你勾選的 {selectedStakeholderCount} 位利害關係人，AI 會把每位實體化為跨領域的 AI 隊友。你可以調整、刪除、手動新增。建立設計專案前需要備齊 {aiCrewCount} 位 Crew。
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={onGenerate}
          isLoading={isGenerating}
          disabled={isCreating}
        >
          <Sparkles size={14} />
          {personas.length === 0
            ? `由 AI 生成 ${aiCrewCount} 位隊友`
            : '重新生成'}
        </Button>
        {personas.length > 0 && (
          <Button
            variant="secondary"
            onClick={onClear}
            disabled={isCreating || isGenerating}
          >
            <RotateCcw size={14} />
            清空
          </Button>
        )}
        {personas.length < aiCrewCount && (
          <Button
            variant="secondary"
            onClick={onManualAdd}
            disabled={isCreating || isGenerating}
          >
            <Plus size={14} />
            手動新增
          </Button>
        )}
      </div>

      {progressLog.length > 0 && (
        <div className="rounded-lg border border-border-light bg-bg-warm/40 p-3 font-mono text-xs leading-relaxed text-text-muted">
          {progressLog.map((line, idx) => (
            <div key={idx} className="flex items-start gap-1.5">
              {isGenerating && idx === progressLog.length - 1 ? (
                <Loader2
                  size={12}
                  className="mt-0.5 shrink-0 animate-spin text-primary"
                />
              ) : (
                <span className="w-3 shrink-0" aria-hidden="true" />
              )}
              <span className="whitespace-pre-wrap">{line}</span>
            </div>
          ))}
        </div>
      )}

      {personas.length === 0 && !isGenerating ? (
        <div className="rounded-xl border border-dashed border-border-light bg-surface/40 p-8 text-center text-sm text-text-muted">
          還沒有 AI 隊友。點「由 AI 生成」或「手動新增」開始設計。
          <br />
          <span className="text-text">
            建立設計專案前需要 {aiCrewCount} 位 Crew 隊友。
          </span>
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {personas.map((persona, idx) => (
            <div key={`${idx}-${persona.name}`} className="w-72 shrink-0">
              <PersonaCard
                persona={persona}
                index={idx}
                onEdit={() => onEdit(idx)}
                onDelete={() => onDelete(idx)}
              />
            </div>
          ))}
          {isGenerating &&
            Array.from({
              length: Math.max(0, aiCrewCount - personas.length),
            }).map((_, idx) => (
              <div
                key={`placeholder-${idx}`}
                className="flex w-72 shrink-0 items-center justify-center rounded-xl border border-dashed border-border-light bg-surface/30 p-6 text-xs text-text-muted"
              >
                <Loader2
                  size={16}
                  className="mr-2 animate-spin text-primary"
                />
                等待 Crew {personas.length + idx + 1}…
              </div>
            ))}
        </div>
      )}

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <Button
          variant="secondary"
          className="flex-1"
          onClick={onBack}
          disabled={isCreating}
        >
          上一步
        </Button>
        <Button
          className="flex-1"
          onClick={onSubmit}
          isLoading={isCreating}
          disabled={isGenerating || !canSubmit}
          title={
            personas.length === aiCrewCount
              ? undefined
              : `還差 ${aiCrewCount - personas.length} 位 Crew 才能建立`
          }
        >
          {personas.length === aiCrewCount
            ? '建立設計專案'
            : `建立設計專案（${personas.length}/${aiCrewCount}）`}
        </Button>
      </div>
    </div>
  )
}
