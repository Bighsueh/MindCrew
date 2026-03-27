import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { Plus, Users, Bot } from 'lucide-react'
import type { Project } from '../../types/models'

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate()

  return (
    <div
      className="group cursor-pointer rounded-xl border border-border bg-surface p-6 shadow-sm
                 transition-all duration-200 hover:border-primary/30 hover:shadow-md"
      onClick={() => navigate(`/projects/${project.id}/lobby`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="truncate text-base font-semibold text-text group-hover:text-primary">
            {project.name}
          </h3>
          {project.description && (
            <p className="mt-1 line-clamp-2 text-sm text-text-muted">{project.description}</p>
          )}
        </div>
        <PhaseIndicator phase={project.current_stage} />
      </div>

      <div className="mt-4 flex items-center gap-4 text-sm text-text-muted">
        {project.seat_summary && (
          <>
            <span className="flex items-center gap-1">
              <Users size={14} />
              {project.seat_summary.human} 人類
            </span>
            <span className="flex items-center gap-1">
              <Bot size={14} />
              {project.seat_summary.ai} AI
            </span>
          </>
        )}
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { projects, isLoading, fetchProjects } = useProjectStore()
  const { user } = useAuthStore()
  const [showCreate, setShowCreate] = useState(false)

  const canCreateProject =
    user?.role === 'teacher' || user?.can_create_project

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">我的專案</h2>
        {canCreateProject && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} />
            新增專案
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loading text="載入專案中…" />
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-surface py-16 text-center">
          <h3 className="text-base font-medium text-text">尚無專案</h3>
          <p className="mt-1 text-sm text-text-muted">
            {canCreateProject ? '點擊「新增專案」開始你的設計思考之旅。' : '等待老師邀請你加入專案。'}
          </p>
          {canCreateProject && (
            <Button className="mt-4" onClick={() => setShowCreate(true)}>
              建立第一個專案
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      <CreateProjectDialog
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => { setShowCreate(false); fetchProjects() }}
      />
    </div>
  )
}
