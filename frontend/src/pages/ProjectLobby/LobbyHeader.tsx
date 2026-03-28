import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import type { Project } from '../../types/models'

const AI_LABELS: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

interface LobbyHeaderProps {
  project: Project
}

export function LobbyHeader({ project }: LobbyHeaderProps) {
  return (
    <div className="mb-8">
      {/* Breadcrumb */}
      <div className="mb-4 flex items-center gap-2 text-sm text-text-muted">
        <Link
          to="/projects"
          className="flex items-center gap-1 hover:text-text transition-colors"
        >
          <ChevronLeft size={16} />
          返回專案列表
        </Link>
      </div>

      {/* Title row */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-text">{project.name}</h1>
            <PhaseIndicator phase={project.current_stage} />
          </div>
          <p className="mt-1 text-sm text-text-muted">
            AI 貢獻度：{AI_LABELS[project.ai_contribution] ?? project.ai_contribution}
          </p>
        </div>
      </div>

      {/* Double Diamond Progress */}
      <div className="mt-4">
        <DoubleDiamondProgress currentStage={project.current_stage} />
      </div>

      {/* Description */}
      {project.description && (
        <div className="mt-5 rounded-xl bg-surface p-5 border border-border shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-text">工作坊主題</h2>
          <p className="text-sm text-text-muted leading-relaxed">
            {project.description}
          </p>
        </div>
      )}
    </div>
  )
}
