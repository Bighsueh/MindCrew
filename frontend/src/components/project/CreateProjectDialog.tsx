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
import {
  TimerConfigForm,
  buildTimerConfig as buildTimerConfigShared,
  DEFAULT_CUSTOM_BUDGETS,
  type TimerMode,
} from '../timer/TimerConfigForm'
import {
  ConstraintsField,
  EMPTY_SIMPLE_CONSTRAINTS,
  buildSimpleConstraintsText,
  type ConstraintsMode,
  type SimpleConstraints,
} from './ConstraintsField'
import { useAuthStore } from '../../stores/authStore'

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

type RoleCopyKey = 'teacher' | 'student'

const ROLE_COPY: Record<RoleCopyKey, {
  basicsTitle: string
  personasTitle: string
  step1Label: string
  step2Label: string
  descriptionLabel: string
  descriptionPlaceholder: string
  constraintsHelper: string
  aiContributionLabel: string
  aiContributionHint: string
  personasIntro: (n: number) => string
  emptyPersonasHint: (n: number) => string
  submitLabel: string
  submitPartial: (cur: number, total: number) => string
}> = {
  teacher: {
    basicsTitle: '建立新學習活動',
    personasTitle: '設計 AI 隊友',
    step1Label: '1. 活動資訊',
    step2Label: '2. 設計 AI 隊友',
    descriptionLabel: '描述（選填）',
    descriptionPlaceholder: '簡述這個設計思考工作坊的主題、使用者、目標…',
    constraintsHelper:
      '限制不是阻礙，而是激發創意的養分。例：預算極低、使用者多為長者、必須在 3 個月內落地。',
    aiContributionLabel: 'AI 貢獻度',
    aiContributionHint: '你希望 AI 在這次工作坊扮演多重的角色？',
    personasIntro: (n) =>
      `基於你輸入的主題、描述和限制，由 AI 產出跨領域的隊友人設。你可以調整、刪除、手動新增。建立活動前必須備齊 ${n} 位 Crew 隊友。`,
    emptyPersonasHint: (n) => `建立活動前必須備齊 ${n} 位 Crew 隊友。`,
    submitLabel: '建立學習活動',
    submitPartial: (cur, total) => `建立學習活動（${cur}/${total}）`,
  },
  student: {
    basicsTitle: '開啟新探索',
    personasTitle: '挑選你的 AI 夥伴',
    step1Label: '1. 活動資訊',
    step2Label: '2. 挑選 AI 夥伴',
    descriptionLabel: '描述（選填）',
    descriptionPlaceholder: '寫下你想探索的題目、好奇的對象與想解決的事…',
    constraintsHelper:
      '限制能幫你聚焦——想想你的時間、預算、能找到的人與場合。',
    aiContributionLabel: 'AI 參與程度',
    aiContributionHint: '你希望 AI 多幫你一點，還是讓你自己想多一點？',
    personasIntro: (n) =>
      `AI 幫你找了幾個不同角度的夥伴，看看誰能幫到你；可以改、可以換、也可以自己加。開始探索前需要 ${n} 位夥伴。`,
    emptyPersonasHint: (n) => `開始探索前需要 ${n} 位夥伴。`,
    submitLabel: '開始探索',
    submitPartial: (cur, total) => `開始探索（${cur}/${total}）`,
  },
}

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
  const user = useAuthStore((s) => s.user)
  const copy = ROLE_COPY[user?.role === 'student' ? 'student' : 'teacher']

  const [step, setStep] = useState<WizardStep>('basics')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [constraintsMode, setConstraintsMode] = useState<ConstraintsMode>('simple')
  const [simpleConstraints, setSimpleConstraints] = useState<SimpleConstraints>(
    EMPTY_SIMPLE_CONSTRAINTS,
  )
  const [constraints, setConstraints] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  const [aiCrewCount, setAiCrewCount] = useState<number>(DEFAULT_AI_CREW)
  // Phase 22：學生建立活動時可選填教師代碼以列管
  const [teacherSignatureCode, setTeacherSignatureCode] = useState('')

  const resolveConstraintsText = (): string => {
    if (constraintsMode === 'simple') {
      return buildSimpleConstraintsText(simpleConstraints)
    }
    return constraints.trim()
  }

  const [personas, setPersonas] = useState<Persona[]>([])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  // specs/16-timer-system.md：timer 配置（preset 或自訂）
  const [timerMode, setTimerMode] = useState<TimerMode>('preset_2hr')
  const [customMacroBudgets, setCustomMacroBudgets] = useState({ ...DEFAULT_CUSTOM_BUDGETS })

  const [error, setError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const reset = () => {
    setStep('basics')
    setName('')
    setDescription('')
    setConstraintsMode('simple')
    setSimpleConstraints(EMPTY_SIMPLE_CONSTRAINTS)
    setConstraints('')
    setAiContribution('medium')
    setAiCrewCount(DEFAULT_AI_CREW)
    setTeacherSignatureCode('')
    setPersonas([])
    setEditingIndex(null)
    setTimerMode('preset_2hr')
    setCustomMacroBudgets({ ...DEFAULT_CUSTOM_BUDGETS })
    setError('')
    setIsCreating(false)
    setIsGenerating(false)
    setProgressLog([])
    abortRef.current?.abort()
    abortRef.current = null
  }

  const buildTimerConfig = () => buildTimerConfigShared(timerMode, customMacroBudgets)

  const customTotalMinutes =
    customMacroBudgets.discover +
    customMacroBudgets.define +
    customMacroBudgets.develop +
    customMacroBudgets.deliver

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
          constraints: resolveConstraintsText() || undefined,
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

  const isTimerValid = useMemo(
    () => timerMode !== 'custom' || customTotalMinutes >= 30,
    [timerMode, customTotalMinutes],
  )

  const canSubmit = useMemo(
    () =>
      name.trim().length > 0 &&
      personas.length === aiCrewCount &&
      isTimerValid,
    [name, personas.length, aiCrewCount, isTimerValid],
  )

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('請輸入活動名稱。')
      return
    }
    if (personas.length !== aiCrewCount) {
      setError(`必須備齊 ${aiCrewCount} 位 Crew 才能建立。`)
      return
    }
    setError('')
    setIsCreating(true)
    try {
      await createProject({
        name: name.trim(),
        description: description.trim(),
        constraints: resolveConstraintsText() || undefined,
        ai_contribution: aiContribution,
        ai_crew_count: aiCrewCount,
        personas: buildAssignments(personas),
        timer_config: buildTimerConfig(),
        teacher_signature_code:
          teacherSignatureCode.trim().toUpperCase() || undefined,
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
      title={step === 'basics' ? copy.basicsTitle : copy.personasTitle}
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
            {copy.step1Label}
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
            {copy.step2Label}
          </span>
        </div>

        {step === 'basics' && (
          <div className="flex flex-col gap-5">
            <Input
              label="活動名稱"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：校園永續設計工作坊"
              required
            />

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-text">{copy.descriptionLabel}</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={copy.descriptionPlaceholder}
                rows={3}
                className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text placeholder:text-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
            </div>

            <ConstraintsField
              mode={constraintsMode}
              onModeChange={setConstraintsMode}
              simple={simpleConstraints}
              onSimpleChange={setSimpleConstraints}
              advancedText={constraints}
              onAdvancedTextChange={setConstraints}
              helperText={copy.constraintsHelper}
            />

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-text">{copy.aiContributionLabel}</label>
              <p className="text-xs text-text-muted">{copy.aiContributionHint}</p>
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

            {/* specs/16-timer-system.md：老師可挑 preset 或自訂 macro budget */}
            <div className="flex flex-col gap-2">
              <TimerConfigForm
                mode={timerMode}
                customMacroBudgets={customMacroBudgets}
                onModeChange={setTimerMode}
                onCustomChange={setCustomMacroBudgets}
              />
            </div>

            {/* Phase 22：學生可選填教師代碼以將活動列管於該老師 */}
            {user?.role === 'student' && (
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text">
                  邀請老師指導（選填）
                </label>
                <p className="text-xs text-text-muted">
                  輸入老師代碼，活動建立後就會出現在他的儀表板。
                </p>
                <Input
                  value={teacherSignatureCode}
                  onChange={(e) =>
                    setTeacherSignatureCode(e.target.value.toUpperCase())
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
              <Button variant="secondary" className="flex-1" onClick={handleClose}>
                取消
              </Button>
              <Button
                className="flex-1"
                onClick={() => {
                  if (!canAdvanceToPersonas) {
                    setError('請輸入活動名稱。')
                    return
                  }
                  if (!isTimerValid) {
                    setError('時間配置總計需 ≥ 30 分鐘。')
                    return
                  }
                  setError('')
                  setStep('personas')
                }}
                disabled={!canAdvanceToPersonas || !isTimerValid}
              >
                下一步：{copy.personasTitle}
              </Button>
            </div>
          </div>
        )}

        {step === 'personas' && (
          <div className="flex flex-col gap-4">
            <div className="rounded-lg border border-border-light bg-bg-warm/40 p-4 text-sm leading-relaxed text-text-muted">
              {copy.personasIntro(aiCrewCount)}
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
                <span className="text-text">{copy.emptyPersonasHint(aiCrewCount)}</span>
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
                  ? copy.submitLabel
                  : copy.submitPartial(personas.length, aiCrewCount)}
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
