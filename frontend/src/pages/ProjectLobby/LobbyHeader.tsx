import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import { LobbyEnrollmentRow } from './LobbyEnrollmentRow'
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
          className="flex items-center gap-1 rounded-md px-2 py-1 hover:text-text hover:bg-surface transition-colors"
        >
          <ChevronLeft size={16} />
          返回設計專案
        </Link>
      </div>

      {/* Title row（活動名 + 階段 + AI 貢獻度） */}
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-text">{project.name}</h1>
          <PhaseIndicator phase={project.current_stage} />
        </div>
        <p className="mt-1.5 text-sm text-text-muted">
          AI 貢獻度：{AI_LABELS[project.ai_contribution] ?? project.ai_contribution}
        </p>
      </div>

      {/* Phase 22 / UX revamp：邀請老師指導（獨立一條橫向 bar） */}
      <div className="mt-5">
        <LobbyEnrollmentRow project={project} />
      </div>

      {/* Double Diamond Progress */}
      <div className="mt-5">
        <DoubleDiamondProgress currentStage={project.current_stage} />
      </div>

      {/* Description */}
      {project.description && (
        <div className="mt-6 rounded-2xl bg-surface p-6 shadow-md">
          <h2 className="mb-2 text-sm font-semibold text-text">工作坊主題</h2>
          <p className="text-sm text-text-muted leading-relaxed">
            {project.description}
          </p>
        </div>
      )}
    </div>
  )
}
