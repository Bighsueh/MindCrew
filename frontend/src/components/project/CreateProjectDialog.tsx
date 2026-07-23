import { useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { Modal } from '../common/Modal'
import {
  createProject,
  generatePersonasStream,
  suggestStakeholders,
  type PersonaStreamEvent,
} from '../../services/projectService'
import { PersonaEditDialog } from '../persona/PersonaEditDialog'
import { useStudyAutofill } from '../../hooks/useStudyAutofill'
import type { StudyConfig } from '../../lib/studyParams'
import type {
  AIContribution,
  CrewPersonaAssignment,
  CrewSeatRole,
  Persona,
  StakeholderSuggestion,
  TurnPolicy,
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
import { StepIndicator, WIZARD_TITLES, type WizardStep } from './StepIndicator'
import { StudyNarrationBanner } from './StudyNarrationBanner'
import { useAuthStore } from '../../stores/authStore'

interface CreateProjectDialogProps {
  isOpen: boolean
  onClose: () => void
  /** Phase 43（spec/29）：study 深連結設定；非 null 時啟動幽靈代填＋鎖定 */
  study?: StudyConfig | null
  /** 建立成功後回呼，帶入剛建立的活動（供父層詢問是否直接進入）。 */
  onCreated: (project: { id: string; name: string }) => void
}

const CREW_SLOTS: CrewSeatRole[] = ['crew_1', 'crew_2', 'crew_3', 'crew_4']
const MIN_AI_CREW = 1
const MAX_AI_CREW = 4
const DEFAULT_AI_CREW = 3

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
  study = null,
  onCreated,
}: CreateProjectDialogProps) {
  const user = useAuthStore((s) => s.user)

  const [step, setStep] = useState<WizardStep>('brief')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [constraints, setConstraints] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  // Phase 28：建立時的輪流規則；DB server_default='cued' 兜底，但 UI 預設讓使用者明確選擇。
  const [turnPolicy, setTurnPolicy] = useState<TurnPolicy>('cued')
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

  const [timerMode, setTimerMode] = useState<TimerMode>('preset_40min')
  const [customMacroBudgets, setCustomMacroBudgets] = useState<{ discover: number; define: number }>({
    ...DEFAULT_CUSTOM_BUDGETS,
  })

  const [error, setError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Phase 43（spec/29 §3.2）：study 模式的幽靈代填——當著受試者的面填好受控欄位並鎖定
  const autofill = useStudyAutofill({
    config: study,
    active: isOpen && step === 'brief',
    setters: {
      setName,
      setDescription,
      setTurnPolicy,
      setAiContribution,
      // study 的 crew 已過 allowlist（1–4），不需 handleAiCrewCountChange 的 clamp/裁切
      setAiCrewCount,
      setTimerMode,
    },
  })

  const reset = () => {
    setStep('brief')
    setName('')
    setDescription('')
    setConstraints('')
    setAiContribution('medium')
    setTurnPolicy('cued')
    setAiCrewCount(DEFAULT_AI_CREW)
    setTeacherSignatureCode('')
    setStakeholderSuggestions([])
    setSelectedStakeholders([])
    setIsLoadingStakeholders(false)
    setStakeholdersFetchedOnce(false)
    setPersonas([])
    setEditingIndex(null)
    setTimerMode('preset_40min')
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

  // Phase 29 (spec/16-timer-system §2.1): develop / deliver budgets removed.
  const customTotalMinutes =
    customMacroBudgets.discover + customMacroBudgets.define

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
                if (event.status === 'start') {
                  appendLog('🔍 對齊你勾選的利害關係人…')
                } else {
                  const count = event.category_count ?? selectedStakeholders.length
                  appendLog(`✓ 已對齊 ${count} 位`)
                }
              } else if (event.stage === 'persona_instantiation') {
                if (event.status === 'start') {
                  // Phase 28 narrative：點名第一位 stakeholder 增加可讀性
                  const first = selectedStakeholders[0]
                  if (first) {
                    appendLog(`🧩 正在從「${first.name}」生成 AI 隊友…`)
                  } else {
                    appendLog('🧩 開始把利害關係人實體化為 AI 隊友…')
                  }
                }
              }
            } else if (event.type === 'persona') {
              // Phase 28 narrative：呈現「stakeholder → persona」對應關係
              const src = selectedStakeholders[event.index]
              if (src) {
                appendLog(
                  `✓ 「${src.name}」→ ${event.persona.name} (Crew ${event.index + 1})`,
                )
                // 預先點名下一位，讓 progress log 更像實況轉播
                const next = selectedStakeholders[event.index + 1]
                if (next) {
                  appendLog(`🧩 正在從「${next.name}」生成 AI 隊友…`)
                }
              } else {
                appendLog(`✓ Crew ${event.index + 1}：${event.persona.name}`)
              }
              setPersonas((prev) => {
                const arr = [...prev]
                arr[event.index] = event.persona
                return arr
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

  // 進到第三步即自動生成 AI 隊友(對應第二步進入時自動盤點利害關係人的模式)。
  // 使用者只能編輯生成結果,不能手動新增。
  useEffect(() => {
    if (
      step === 'personas' &&
      personas.length === 0 &&
      !isGenerating &&
      selectedStakeholders.length > 0
    ) {
      void handleGenerate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  const handleEditSave = (updated: Persona) => {
    if (editingIndex === null) return
    setPersonas((prev) =>
      prev.map((p, idx) => (idx === editingIndex ? updated : p)),
    )
    setEditingIndex(null)
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
      const created = await createProject({
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
        turn_policy: turnPolicy,
      })
      onCreated({ id: created.id, name: created.name })
      reset()
    } catch (err) {
      let message = '建立失敗，請稍後再試。'
      if (
        isAxiosError(err) &&
        (!err.response ||
          err.code === 'ECONNABORTED' ||
          err.message === 'Network Error')
      ) {
        // 網路/逾時：精靈狀態都還在（未 reset），引導使用者直接再按一次
        message = '網路或伺服器忙線，建立可能已逾時，請稍候再按一次「建立」。'
      } else if (isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        message = err.response.data.detail
      } else if (err instanceof Error && err.message) {
        message = err.message
      }
      setError(message)
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={WIZARD_TITLES[step]}
      maxWidth="7xl"
    >
      <div className="flex flex-col gap-5">
        <StepIndicator current={step} />

        {/* Phase 43：幽靈代填 narration（精靈層級敘事，spec/29 §3.2） */}
        {step === 'brief' && autofill.narration && (
          <StudyNarrationBanner
            narration={autofill.narration}
            isAnimating={autofill.isAnimating}
          />
        )}

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
            turnPolicy={turnPolicy}
            onTurnPolicyChange={setTurnPolicy}
            timerMode={timerMode}
            onTimerModeChange={setTimerMode}
            customMacroBudgets={customMacroBudgets}
            onCustomMacroBudgetsChange={setCustomMacroBudgets}
            teacherSignatureCode={teacherSignatureCode}
            onTeacherSignatureCodeChange={setTeacherSignatureCode}
            userRole={user?.role}
            study={autofill.ui}
            error={error}
            onCancel={handleClose}
            onNext={() => {
              if (autofill.isAnimating) return
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
            canAdvance={canAdvanceToStakeholders && !autofill.isAnimating}
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
            selectedStakeholders={selectedStakeholders}
            aiCrewCount={aiCrewCount}
            personas={personas}
            isGenerating={isGenerating}
            isCreating={isCreating}
            progressLog={progressLog}
            error={error}
            onGenerate={handleGenerate}
            onEdit={(idx) => setEditingIndex(idx)}
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

