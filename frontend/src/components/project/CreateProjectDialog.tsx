import { useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { createProject } from '../../services/projectService'
import { cn } from '../../lib/utils'
import type { AIContribution } from '../../types/models'

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

export function CreateProjectDialog({ isOpen, onClose, onCreated }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('請輸入專案名稱。')
      return
    }
    setError('')
    setIsLoading(true)

    try {
      await createProject({
        name: name.trim(),
        description: description.trim(),
        ai_contribution: aiContribution,
      })
      setName('')
      setDescription('')
      setAiContribution('medium')
      onCreated()
    } catch {
      setError('建立失敗，請稍後再試。')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="建立新專案">
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
            placeholder="簡述這個設計思考工作坊的主題和目標…"
            rows={3}
            className="rounded-md border border-border px-3 py-2.5 text-sm bg-surface text-text
                       placeholder:text-text-muted resize-none
                       focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
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
          <Button variant="secondary" className="flex-1" onClick={onClose}>
            取消
          </Button>
          <Button className="flex-1" isLoading={isLoading} onClick={handleSubmit}>
            建立專案
          </Button>
        </div>
      </div>
    </Modal>
  )
}
