import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createProject } from '../../services/projectService'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import type { AIContribution } from '../../types/models'

const AI_CONTRIBUTION_OPTIONS: Array<{ value: AIContribution; label: string; description: string }> =
  [
    { value: 'low', label: '低', description: 'AI 較少主動介入，讓人類主導' },
    { value: 'medium', label: '中', description: 'AI 與人類均衡合作（建議）' },
    { value: 'high', label: '高', description: 'AI 積極引導，適合練習用途' },
  ]

export function NewProjectPage() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [aiContribution, setAiContribution] = useState<AIContribution>('medium')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('請輸入專案名稱。')
      return
    }

    setIsLoading(true)

    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
        ai_contribution: aiContribution,
      })
      navigate(`/projects/${project.id}/lobby`)
    } catch {
      setError('建立專案失敗，請稍後再試。')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-12">
      <div className="mx-auto max-w-lg">
        {/* Back link */}
        <Link to="/projects" className="mb-6 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          ← 返回專案列表
        </Link>

        <div className="rounded-2xl bg-white p-8 shadow-sm border border-gray-200">
          <h1 className="mb-6 text-xl font-bold text-gray-900">建立新專案</h1>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <Input
              label="專案名稱"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：永續校園設計挑戰"
              required
            />

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">主題描述</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="簡短描述這個設計思考工作坊的主題與目標…"
                rows={4}
                className={[
                  'rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm',
                  'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                  'placeholder:text-gray-400 resize-none',
                ].join(' ')}
              />
            </div>

            {/* AI contribution */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-gray-700">AI 貢獻度</label>
              <div className="flex gap-2">
                {AI_CONTRIBUTION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setAiContribution(opt.value)}
                    className={[
                      'flex-1 rounded-lg border-2 p-3 text-left transition-all duration-150',
                      aiContribution === opt.value
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300',
                    ].join(' ')}
                  >
                    <p className="text-sm font-semibold text-gray-900">{opt.label}</p>
                    <p className="mt-0.5 text-xs text-gray-500">{opt.description}</p>
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="flex gap-3 mt-2">
              <Link to="/projects" className="flex-1">
                <Button variant="secondary" className="w-full">
                  取消
                </Button>
              </Link>
              <Button type="submit" isLoading={isLoading} className="flex-1">
                建立專案
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
