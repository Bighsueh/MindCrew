import { useMemo, useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { Loading } from '../common/Loading'
import { createProject, generatePersonas } from '../../services/projectService'
import { PersonaCard } from '../persona/PersonaCard'
import { PersonaEditDialog } from '../persona/PersonaEditDialog'
import { emptyPersona } from '../persona/personaUtils'
import { cn } from '../../lib/utils'
import { Plus, Sparkles, RotateCcw } from 'lucide-react'
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

  const [personas, setPersonas] = useState<Persona[]>([])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  const [error, setError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)

  const reset = () => {
    setStep('basics')
    setName('')
    setDescription('')
    setConstraints('')
    setAiContribution('medium')
    setPersonas([])
    setEditingIndex(null)
    setError('')
    setIsCreating(false)
    setIsGenerating(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const canAdvanceToPersonas = useMemo(() => name.trim().length > 0, [name])

  const handleGenerate = async () => {
    setError('')
    setIsGenerating(true)
    try {
      const generated = await generatePersonas({
        title: name.trim(),
        description: description.trim() || undefined,
        constraints: constraints.trim() || undefined,
        num_personas: 4,
      })
      if (generated.length === 0) {
        setError('AI 沒有生成任何人設，請手動新增或調整主題。')
        return
      }
      setPersonas(generated.slice(0, 4))
    } catch (err) {
      const message = err instanceof Error ? err.message : '生成失敗，請稍後再試。'
      setError(message)
    } finally {
      setIsGenerating(false)
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
    if (personas.length >= 4) return
    const nextIndex = personas.length
    setPersonas((prev) => [...prev, emptyPersona()])
    setEditingIndex(nextIndex)
  }

  const handleDelete = (index: number) => {
    setPersonas((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('請輸入專案名稱。')
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
        personas: personas.length > 0 ? buildAssignments(personas) : undefined,
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
      maxWidth="xl"
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
              你可以調整、刪除、手動新增，或直接跳過使用系統預設。
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleGenerate}
                isLoading={isGenerating}
                disabled={isCreating}
              >
                <Sparkles size={14} />
                {personas.length === 0 ? '由 AI 生成 4 位隊友' : '重新生成'}
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
              {personas.length < 4 && (
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

            {isGenerating ? (
              <div className="flex justify-center py-10">
                <Loading text="AI 正在生成跨領域隊友…" />
              </div>
            ) : personas.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border-light bg-surface/40 p-8 text-center text-sm text-text-muted">
                還沒有 AI 隊友。點「由 AI 生成」或「手動新增」開始設計。
                <br />
                跳過此步將使用系統預設（同理 / 結構 / 創意 / 可行性）4 位通用隊友。
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {personas.map((persona, idx) => (
                  <PersonaCard
                    key={`${idx}-${persona.name}`}
                    persona={persona}
                    index={idx}
                    onEdit={() => setEditingIndex(idx)}
                    onDelete={() => handleDelete(idx)}
                  />
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
                disabled={isGenerating}
              >
                建立專案
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
