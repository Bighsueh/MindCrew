import { useEffect, useMemo, useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { DeleteProjectDialog } from '../../components/project/DeleteProjectDialog'
import { ProjectCard } from '../../components/project/ProjectCard'
import { cn } from '../../lib/utils'
import { Plus, Search, FolderOpen, Sparkles, CheckCircle2 } from 'lucide-react'
import type { ProjectListItem, DTStage } from '../../types/models'

type StageFilter = 'all' | DTStage

const STAGE_FILTERS: { value: StageFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'discover', label: 'Discover' },
  { value: 'define', label: 'Define' },
  { value: 'develop', label: 'Develop' },
  { value: 'deliver', label: 'Deliver' },
  { value: 'completed', label: '已完成' },
]

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: typeof FolderOpen
  label: string
  value: number
  accent: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-5 py-4">
      <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', accent)}>
        <Icon size={18} />
      </div>
      <div>
        <div className="text-2xl font-bold text-text">{value}</div>
        <div className="text-xs text-text-muted">{label}</div>
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { projects, isLoading, fetchProjects, deleteProject } = useProjectStore()
  const { user } = useAuthStore()
  const [showCreate, setShowCreate] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ProjectListItem | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [stageFilter, setStageFilter] = useState<StageFilter>('all')

  const canCreateProject = user?.role === 'teacher' || user?.can_create_project

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  // Compute stats
  const stats = useMemo(() => {
    const active = projects.filter((p) => p.status === 'active').length
    const completed = projects.filter(
      (p) => p.status === 'completed' || p.current_stage === 'completed',
    ).length
    return { total: projects.length, active, completed }
  }, [projects])

  // Filter projects
  const filteredProjects = useMemo(() => {
    let result = projects
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.description && p.description.toLowerCase().includes(q)),
      )
    }
    if (stageFilter !== 'all') {
      result = result.filter((p) => p.current_stage === stageFilter)
    }
    return result
  }, [projects, searchQuery, stageFilter])

  // Split into active and completed groups
  const { activeProjects, completedProjects } = useMemo(() => {
    const active: ProjectListItem[] = []
    const completed: ProjectListItem[] = []
    for (const p of filteredProjects) {
      if (p.current_stage === 'completed' || p.status === 'completed') {
        completed.push(p)
      } else {
        active.push(p)
      }
    }
    return { activeProjects: active, completedProjects: completed }
  }, [filteredProjects])

  const handleDelete = async () => {
    if (!deleteTarget) return
    await deleteProject(deleteTarget.id)
  }

  const greeting = user?.display_name
    ? `${user.display_name}，歡迎回來`
    : '歡迎回來'

  return (
    <div className="flex flex-col gap-6">
      {/* Welcome + Stats */}
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-xl font-bold text-text">{greeting}</h1>
            <p className="mt-0.5 text-sm text-text-muted">管理你的設計思考專案</p>
          </div>
          {canCreateProject && (
            <Button onClick={() => setShowCreate(true)}>
              <Plus size={16} />
              新增專案
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard icon={FolderOpen} label="全部專案" value={stats.total} accent="bg-primary/10 text-primary" />
          <StatCard icon={Sparkles} label="進行中" value={stats.active} accent="bg-info/10 text-info" />
          <StatCard icon={CheckCircle2} label="已完成" value={stats.completed} accent="bg-success/10 text-success" />
        </div>
      </div>

      {/* Filter + Search */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1.5">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStageFilter(f.value)}
              className={cn(
                'rounded-full px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer',
                stageFilter === f.value
                  ? 'bg-primary text-text-inverse'
                  : 'bg-surface-hover text-text-muted hover:text-text',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="relative max-w-xs flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜尋專案名稱…"
            className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm text-text
                       placeholder:text-text-muted
                       focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loading text="載入專案中…" />
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-surface py-16 text-center">
          <FolderOpen size={40} className="text-text-muted/40" />
          <h3 className="mt-4 text-base font-medium text-text">尚無專案</h3>
          <p className="mt-1 text-sm text-text-muted">
            {canCreateProject ? '點擊「新增專案」開始你的設計思考之旅。' : '等待老師邀請你加入專案。'}
          </p>
          {canCreateProject && (
            <Button className="mt-4" onClick={() => setShowCreate(true)}>
              建立第一個專案
            </Button>
          )}
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-surface py-12 text-center">
          <Search size={32} className="text-text-muted/40" />
          <p className="mt-3 text-sm text-text-muted">找不到符合條件的專案</p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {/* Active projects */}
          {activeProjects.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-muted">
                進行中 ({activeProjects.length})
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {activeProjects.map((project) => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    isOwner={project.creator_id === user?.id}
                    onDelete={setDeleteTarget}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Completed projects */}
          {completedProjects.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-muted">
                已完成 ({completedProjects.length})
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {completedProjects.map((project) => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    isOwner={project.creator_id === user?.id}
                    onDelete={setDeleteTarget}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Dialogs */}
      <CreateProjectDialog
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => { setShowCreate(false); fetchProjects() }}
      />

      {deleteTarget && (
        <DeleteProjectDialog
          isOpen={!!deleteTarget}
          projectName={deleteTarget.name}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
    </div>
  )
}
