import { useEffect, useMemo, useRef, useState } from 'react'
import { Modal } from '../common/Modal'
import {
  createProject,
  generatePersonasStream,
  suggestStakeholders,
  type PersonaStreamEvent,
} from '../../services/projectService'
import { PersonaEditDialog } from '../persona/PersonaEditDialog'
import { emptyPersona } from '../persona/personaUtils'
import { cn } from '../../lib/utils'
import type {
  AIContribution,
  CrewPersonaAssignment,
  CrewSeatRole,
  Persona,
  StakeholderSuggestion,
} from '../../types/models'
import type { StakeholderSelectionInput } from '../../types/api'
import {
  buildTimerConfig as buildTimerConfigShared,
  DEFAULT_CUSTOM_BUDGETS,
  type TimerMode,
} from '../timer/TimerConfigForm'
import { BriefStep } from './BriefStep'
import { StakeholdersStep } from './StakeholdersStep'
import { PersonasStep } from './PersonasStep'
import { useAuthStore } from '../../stores/authStore'

interface CreateProjectDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreated: () => void
}

const CREW_SLOTS: CrewSeatRole[] = ['crew_1', 'crew_2', 'crew_3', 'crew_4']
const MIN_AI_CREW = 1
const MAX_AI_CREW = 4
const DEFAULT_AI_CREW = 3

type WizardStep = 'brief' | 'stakeholders' | 'personas'

const STEP_LABELS: Record<WizardStep, string> = {
  brief: '1. 設計簡報',
  stakeholders: '2. 利害關係人地圖',
  personas: '3. 設計 AI 隊友',
}

function buildAssignments(personas: Persona[]): CrewPersonaAssignment[] {
  return CREW_SLOTS.slice(0, personas.length).map((seat, idx) => ({
    seat_role: seat,
    persona: personas[idx],
  }))
}

function toSelectionInput(s: StakeholderSuggestion): StakeholderSelectionInput {
  return { id: s.id, name: s.name, role: s.role, relevance: s.relevance }
}

export function CreateProjectDialog({
  isOpen,
  onClose,
  onCreated,
}: CreateProjectDialogProps) {
  const user = useAuthStore((s) => s.user)

  const [step, setStep] = useState<WizardStep>('brief')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [constraints, setConstraints] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  const [aiCrewCount, setAiCrewCount] = useState<number>(DEFAULT_AI_CREW)
  const [teacherSignatureCode, setTeacherSignatureCode] = useState('')

  // Phase 27 Step 2 state
  const [stakeholderSuggestions, setStakeholderSuggestions] = useState<
    StakeholderSuggestion[]
  >([])
  const [selectedStakeholders, setSelectedStakeholders] = useState<
    StakeholderSuggestion[]
  >([])
  const [isLoadingStakeholders, setIsLoadingStakeholders] = useState(false)
  const [stakeholdersFetchedOnce, setStakeholdersFetchedOnce] = useState(false)

  const [personas, setPersonas] = useState<Persona[]>([])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  const [timerMode, setTimerMode] = useState<TimerMode>('preset_2hr')
  const [customMacroBudgets, setCustomMacroBudgets] = useState({
    ...DEFAULT_CUSTOM_BUDGETS,
  })

  const [error, setError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const reset = () => {
    setStep('brief')
    setName('')
    setDescription('')
    setConstraints('')
    setAiContribution('medium')
    setAiCrewCount(DEFAULT_AI_CREW)
    setTeacherSignatureCode('')
    setStakeholderSuggestions([])
    setSelectedStakeholders([])
    setIsLoadingStakeholders(false)
    setStakeholdersFetchedOnce(false)
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

  const buildTimerConfig = () =>
    buildTimerConfigShared(timerMode, customMacroBudgets)

  const customTotalMinutes =
    customMacroBudgets.discover +
    customMacroBudgets.define +
    customMacroBudgets.develop +
    customMacroBudgets.deliver

  const handleClose = () => {
    reset()
    onClose()
  }

  const appendLog = (line: string) =>
    setProgressLog((prev) => [...prev, line])

  const fetchStakeholders = async () => {
    setError('')
    setIsLoadingStakeholders(true)
    try {
      const result = await suggestStakeholders({
        title: name.trim(),
        description: description.trim() || undefined,
        constraints: constraints.trim() || undefined,
        existing_names: stakeholderSuggestions.map((s) => s.name),
      })
      setStakeholderSuggestions((prev) => {
        const existingIds = new Set(prev.map((s) => s.id))
        const merged = [...prev]
        for (const item of result) {
          if (!existingIds.has(item.id)) merged.push(item)
        }
        return merged
      })
      setStakeholdersFetchedOnce(true)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : '取得利害關係人建議失敗。'
      setError(message)
    } finally {
      setIsLoadingStakeholders(false)
    }
  }

  useEffect(() => {
    if (
      step === 'stakeholders' &&
      !stakeholdersFetchedOnce &&
      !isLoadingStakeholders &&
      name.trim()
    ) {
      void fetchStakeholders()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

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
          stakeholders: selectedStakeholders.map(toSelectionInput),
        },
        {
          signal: controller.signal,
          onEvent: (event: PersonaStreamEvent) => {
            if (event.type === 'stage') {
              if (event.stage === 'stakeholder_mapping') {
                appendLog(
                  event.status === 'start'
                    ? '🔍 對齊勾選的利害關係人…'
                    : `✓ 已對齊 ${event.category_count ?? selectedStakeholders.length} 位`,
                )
              } else if (event.stage === 'persona_instantiation') {
                if (event.status === 'start') {
                  appendLog('🧩 開始把利害關係人實體化為 AI 隊友…')
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
      const message =
        err instanceof Error ? err.message : '生成失敗，請稍後再試。'
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

  const handleAiCrewCountChange = (next: number) => {
    const clamped = Math.max(
      MIN_AI_CREW,
      Math.min(MAX_AI_CREW, Math.round(next)),
    )
    setAiCrewCount(clamped)
    setPersonas((prev) => (prev.length > clamped ? prev.slice(0, clamped) : prev))
    setSelectedStakeholders((prev) =>
      prev.length > clamped ? prev.slice(0, clamped) : prev,
    )
  }

  const isTimerValid = useMemo(
    () => timerMode !== 'custom' || customTotalMinutes >= 30,
    [timerMode, customTotalMinutes],
  )

  const canAdvanceToStakeholders = useMemo(
    () => name.trim().length > 0 && isTimerValid,
    [name, isTimerValid],
  )

  const canAdvanceToPersonas = useMemo(
    () => selectedStakeholders.length === aiCrewCount,
    [selectedStakeholders.length, aiCrewCount],
  )

  const canSubmit = useMemo(
    () =>
      name.trim().length > 0 &&
      personas.length === aiCrewCount &&
      selectedStakeholders.length === aiCrewCount &&
      isTimerValid,
    [
      name,
      personas.length,
      selectedStakeholders.length,
      aiCrewCount,
      isTimerValid,
    ],
  )

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('請輸入設計專案名稱。')
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
        constraints: constraints.trim() || undefined,
        stakeholders: selectedStakeholders.map(toSelectionInput),
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
      const message =
        err instanceof Error ? err.message : '建立失敗，請稍後再試。'
      setError(message)
    } finally {
      setIsCreating(false)
    }
  }

  const stepTitle =
    step === 'brief'
      ? '建立新設計專案'
      : step === 'stakeholders'
        ? '利害關係人地圖'
        : '設計 AI 隊友'

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={stepTitle}
      maxWidth={step === 'personas' ? '5xl' : 'xl'}
    >
      <div className="flex flex-col gap-5">
        <StepIndicator current={step} />

        {step === 'brief' && (
          <BriefStep
            name={name}
            onNameChange={setName}
            description={description}
            onDescriptionChange={setDescription}
            constraints={constraints}
            onConstraintsChange={setConstraints}
            aiContribution={aiContribution}
            onAiContributionChange={setAiContribution}
            aiCrewCount={aiCrewCount}
            onAiCrewCountChange={handleAiCrewCountChange}
            timerMode={timerMode}
            onTimerModeChange={setTimerMode}
            customMacroBudgets={customMacroBudgets}
            onCustomMacroBudgetsChange={setCustomMacroBudgets}
            teacherSignatureCode={teacherSignatureCode}
            onTeacherSignatureCodeChange={setTeacherSignatureCode}
            userRole={user?.role}
            error={error}
            onCancel={handleClose}
            onNext={() => {
              if (!name.trim()) {
                setError('請輸入設計專案名稱。')
                return
              }
              if (!isTimerValid) {
                setError('時間配置總計需 ≥ 30 分鐘。')
                return
              }
              setError('')
              setStep('stakeholders')
            }}
            canAdvance={canAdvanceToStakeholders}
          />
        )}

        {step === 'stakeholders' && (
          <StakeholdersStep
            suggestions={stakeholderSuggestions}
            selected={selectedStakeholders}
            onChange={setSelectedStakeholders}
            requiredCount={aiCrewCount}
            isLoading={isLoadingStakeholders}
            onRefetch={() => void fetchStakeholders()}
            error={error}
            onBack={() => {
              setError('')
              setStep('brief')
            }}
            onNext={() => {
              setError('')
              setStep('personas')
            }}
            canAdvance={canAdvanceToPersonas}
          />
        )}

        {step === 'personas' && (
          <PersonasStep
            selectedStakeholderCount={selectedStakeholders.length}
            aiCrewCount={aiCrewCount}
            personas={personas}
            isGenerating={isGenerating}
            isCreating={isCreating}
            progressLog={progressLog}
            error={error}
            onGenerate={handleGenerate}
            onClear={() => setPersonas([])}
            onManualAdd={handleManualAdd}
            onEdit={(idx) => setEditingIndex(idx)}
            onDelete={handleDelete}
            onBack={() => {
              setError('')
              setStep('stakeholders')
            }}
            onSubmit={handleSubmit}
            canSubmit={canSubmit}
          />
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

// ── Internal: 3-step indicator ──────────────────────────────────────────────

interface StepIndicatorProps {
  current: WizardStep
}

function StepIndicator({ current }: StepIndicatorProps) {
  const steps: WizardStep[] = ['brief', 'stakeholders', 'personas']
  const currentIdx = steps.indexOf(current)
  return (
    <div className="flex items-center gap-1.5 text-xs font-medium flex-wrap">
      {steps.map((s, idx) => {
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
            {idx < steps.length - 1 && (
              <span className="text-text-muted">→</span>
            )}
          </span>
        )
      })}
    </div>
  )
}
