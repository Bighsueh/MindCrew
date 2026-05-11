import { useMemo, useRef, useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import {
  createProject,
  generatePersonasStream,
  type PersonaStreamEvent,
} from '../../services/projectService'
import { PersonaCard } from '../persona/PersonaCard'
import { PersonaEditDialog } from '../persona/PersonaEditDialog'
import { emptyPersona } from '../persona/personaUtils'
import { cn } from '../../lib/utils'
import { Plus, Sparkles, RotateCcw, Loader2 } from 'lucide-react'
import type {
  AIContribution,
  CrewPersonaAssignment,
  CrewSeatRole,
  Persona,
} from '../../types/models'

interface CreateProjectDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreated: () => void
}

const AI_LEVELS: { value: AIContribution; label: string; description: string }[] = [
  { value: 'low', label: '低', description: 'AI 輔助較少，以人類主導' },
  { value: 'medium', label: '中', description: 'AI 與人類均衡協作' },
  { value: 'high', label: '高', description: 'AI 積極參與，提供大量洞察' },
]

const CREW_SLOTS: CrewSeatRole[] = ['crew_1', 'crew_2', 'crew_3', 'crew_4']

// Phase 21：教師可選 AI 組員人數（1–4），預設 3。
const MIN_AI_CREW = 1
const MAX_AI_CREW = 4
const DEFAULT_AI_CREW = 3

type WizardStep = 'basics' | 'personas'

function buildAssignments(personas: Persona[]): CrewPersonaAssignment[] {
  return CREW_SLOTS.slice(0, personas.length).map((seat, idx) => ({
    seat_role: seat,
    persona: personas[idx],
  }))
}

export function CreateProjectDialog({
  isOpen,
  onClose,
  onCreated,
}: CreateProjectDialogProps) {
  const [step, setStep] = useState<WizardStep>('basics')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [constraints, setConstraints] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  const [aiCrewCount, setAiCrewCount] = useState<number>(DEFAULT_AI_CREW)

  const [personas, setPersonas] = useState<Persona[]>([])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  const [error, setError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const reset = () => {
    setStep('basics')
    setName('')
    setDescription('')
    setConstraints('')
    setAiContribution('medium')
    setAiCrewCount(DEFAULT_AI_CREW)
    setPersonas([])
    setEditingIndex(null)
    setError('')
    setIsCreating(false)
    setIsGenerating(false)
    setProgressLog([])
    abortRef.current?.abort()
    abortRef.current = null
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const canAdvanceToPersonas = useMemo(() => name.trim().length > 0, [name])

  const appendLog = (line: string) =>
    setProgressLog((prev) => [...prev, line])

  const handleGenerate = async () => {
    setError('')
    setPersonas([])
    setProgressLog([])
    setIsGenerating(true)
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await generatePersonasStream(
        {
          title: name.trim(),
          description: description.trim() || undefined,
          constraints: constraints.trim() || undefined,
          num_personas: aiCrewCount,
        },
        {
          signal: controller.signal,
          onEvent: (event: PersonaStreamEvent) => {
            if (event.type === 'stage') {
              if (event.stage === 'stakeholder_mapping') {
                appendLog(
                  event.status === 'start'
                    ? '🔍 正在盤點利害關係人類別…'
                    : `✓ 找到 ${event.category_count ?? 0} 種利害關係人類別`,
                )
              } else if (event.stage === 'persona_instantiation') {
                if (event.status === 'start') {
                  appendLog('🧩 開始設計跨領域 AI 隊友…')
                }
              }
            } else if (event.type === 'persona') {
              appendLog(`✓ Crew ${event.index + 1}：${event.persona.name}`)
              setPersonas((prev) => {
                const next = [...prev]
                next[event.index] = event.persona
                return next
              })
            } else if (event.type === 'done') {
              appendLog(`✅ 完成（共 ${event.count} 位）`)
            } else if (event.type === 'error') {
              setError(event.detail || '生成失敗，請稍後再試。')
            }
          },
        },
      )
    } catch (err) {
      if ((err as { name?: string }).name === 'AbortError') return
      const message = err instanceof Error ? err.message : '生成失敗，請稍後再試。'
      setError(message)
    } finally {
      setIsGenerating(false)
      abortRef.current = null
    }
  }

  const handleEditSave = (updated: Persona) => {
    if (editingIndex === null) return
    setPersonas((prev) =>
      prev.map((p, idx) => (idx === editingIndex ? updated : p)),
    )
    setEditingIndex(null)
  }

  const handleManualAdd = () => {
    if (personas.length >= aiCrewCount) return
    const nextIndex = personas.length
    setPersonas((prev) => [...prev, emptyPersona()])
    setEditingIndex(nextIndex)
  }

  const handleDelete = (index: number) => {
    setPersonas((prev) => prev.filter((_, idx) => idx !== index))
  }

  // Phase 21：教師改變 AI 組員人數時，截掉超出的 persona（縮小）或保留現有（放大）。
  const handleAiCrewCountChange = (next: number) => {
    const clamped = Math.max(MIN_AI_CREW, Math.min(MAX_AI_CREW, Math.round(next)))
    setAiCrewCount(clamped)
    setPersonas((prev) => (prev.length > clamped ? prev.slice(0, clamped) : prev))
  }

  const canSubmit = useMemo(
    () => name.trim().length > 0 && personas.length === aiCrewCount,
    [name, personas.length, aiCrewCount],
  )

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('請輸入專案名稱。')
      return
    }
    if (personas.length !== aiCrewCount) {
      setError(`必須備齊 ${aiCrewCount} 位 Crew 隊友才能建立專案。`)
      return
    }
    setError('')
    setIsCreating(true)
    try {
      await createProject({
        name: name.trim(),
        description: description.trim(),
        constraints: constraints.trim() || undefined,
        ai_contribution: aiContribution,
        ai_crew_count: aiCrewCount,
        personas: buildAssignments(personas),
      })
      onCreated()
      reset()
    } catch (err) {
      const message = err instanceof Error ? err.message : '建立失敗，請稍後再試。'
      setError(message)
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={step === 'basics' ? '建立新專案' : '設計 AI 隊友'}
      maxWidth={step === 'personas' ? '5xl' : 'xl'}
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2 text-xs font-medium">
          <span
            className={cn(
              'rounded-full px-3 py-1',
              step === 'basics'
                ? 'bg-primary text-text-inverse'
                : 'bg-success/10 text-success',
            )}
          >
            1. 專案資訊
          </span>
          <span className="text-text-muted">→</span>
          <span
            className={cn(
              'rounded-full px-3 py-1',
              step === 'personas'
                ? 'bg-primary text-text-inverse'
                : 'bg-bg-warm text-text-muted',
            )}
          >
            2. 設計 AI 隊友
          </span>
        </div>

        {step === 'basics' && (
          <div className="flex flex-col gap-5">
            <Input
              label="專案名稱"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：校園永續設計工作坊"
              required
            />

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-text">描述（選填）</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="簡述這個設計思考工作坊的主題、使用者、目標…"
                rows={3}
                className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-text">
                專案限制（選填，但強烈建議）
              </label>
              <p className="text-xs text-text-muted">
                限制不是阻礙，而是激發創意的養分。例：預算極低、使用者多為長者、必須在 3 個月內落地。
              </p>
              <textarea
                value={constraints}
                onChange={(e) => setConstraints(e.target.value)}
                placeholder="列出這個專案的關鍵限制條件…"
                rows={3}
                className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-text">AI 貢獻度</label>
              <div className="flex gap-2">
                {AI_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => setAiContribution(level.value)}
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
                每個專案固定有 1 位 AI 組長 + 1 位你（人類），再加上你選的 AI 組員。
              </p>
              <div className="flex gap-2">
                {[1, 2, 3, 4].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => handleAiCrewCountChange(n)}
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

            {error && (
              <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <Button variant="secondary" className="flex-1" onClick={handleClose}>
                取消
              </Button>
              <Button
                className="flex-1"
                onClick={() => {
                  if (!canAdvanceToPersonas) {
                    setError('請輸入專案名稱。')
                    return
                  }
                  setError('')
                  setStep('personas')
                }}
                disabled={!canAdvanceToPersonas}
              >
                下一步：設計 AI 隊友
              </Button>
            </div>
          </div>
        )}

        {step === 'personas' && (
          <div className="flex flex-col gap-4">
            <div className="rounded-lg border border-border-light bg-bg-warm/40 p-4 text-sm leading-relaxed text-text-muted">
              基於你輸入的主題、描述和限制，由 AI 產出跨領域的隊友人設。
              你可以調整、刪除、手動新增。
              <span className="text-text">
                建立專案前必須備齊 {aiCrewCount} 位 Crew 隊友
              </span>
              。
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleGenerate}
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
                  onClick={() => setPersonas([])}
                  disabled={isCreating || isGenerating}
                >
                  <RotateCcw size={14} />
                  清空
                </Button>
              )}
              {personas.length < aiCrewCount && (
                <Button
                  variant="secondary"
                  onClick={handleManualAdd}
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
                  建立專案前必須備齊 {aiCrewCount} 位 Crew 隊友
                </span>
                。
              </div>
            ) : (
              <div className="flex gap-3 overflow-x-auto pb-2">
                {personas.map((persona, idx) => (
                  <div
                    key={`${idx}-${persona.name}`}
                    className="w-72 shrink-0"
                  >
                    <PersonaCard
                      persona={persona}
                      index={idx}
                      onEdit={() => setEditingIndex(idx)}
                      onDelete={() => handleDelete(idx)}
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
                onClick={() => {
                  setError('')
                  setStep('basics')
                }}
                disabled={isCreating}
              >
                上一步
              </Button>
              <Button
                className="flex-1"
                onClick={handleSubmit}
                isLoading={isCreating}
                disabled={isGenerating || !canSubmit}
                title={
                  personas.length === aiCrewCount
                    ? undefined
                    : `還差 ${aiCrewCount - personas.length} 位 Crew 才能建立`
                }
              >
                {personas.length === aiCrewCount
                  ? '建立專案'
                  : `建立專案（${personas.length}/${aiCrewCount}）`}
              </Button>
            </div>
          </div>
        )}
      </div>

      {editingIndex !== null && personas[editingIndex] && (
        <PersonaEditDialog
          isOpen
          initial={personas[editingIndex]}
          title={`編輯 Crew ${editingIndex + 1}`}
          onClose={() => setEditingIndex(null)}
          onSave={handleEditSave}
        />
      )}
    </Modal>
  )
}
