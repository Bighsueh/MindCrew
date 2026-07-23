import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import { LobbyEnrollmentRow } from './LobbyEnrollmentRow'
import type { Project } from '../../types/models'

interface LobbyHeaderProps {
  project: Project
}

/** 大廳 Hero：返回鈕 + 活動名/階段 + Double Diamond 進度 + 邀請老師（可摺疊）。 */
export function LobbyHeader({ project }: LobbyHeaderProps) {
  return (
    <div className="mb-6">
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

      {/* Title row（活動名 + 階段） */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-bold text-text">{project.name}</h1>
        <PhaseIndicator phase={project.current_stage} />
      </div>

      {/* Double Diamond Progress（lobby 用 md，含目前 micro phase） */}
      <div className="mt-5">
        <DoubleDiamondProgress
          currentStage={project.current_stage}
          currentMicroPhase={project.current_micro_phase}
          size="md"
        />
      </div>

      {/* 邀請老師指導（可摺疊橫向 bar，預設收合） */}
      <div className="mt-5">
        <LobbyEnrollmentRow project={project} />
      </div>
    </div>
  )
}
