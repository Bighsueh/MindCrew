import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { Toast } from '../../components/common/Toast'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { DeleteProjectDialog } from '../../components/project/DeleteProjectDialog'
import { ProjectCard } from '../../components/project/ProjectCard'
import { ProjectCreatedDialog } from '../../components/project/ProjectCreatedDialog'
import { StickyNoteSVG } from '../../components/landing/StickyNoteSVG'
import { useProjectsTourAutoStart } from '../../components/onboarding/useProjectsTourAutoStart'
import { cn } from '../../lib/utils'
import {
  parseStudyParams,
  readStudySession,
  saveStudySession,
  clearStudySession,
  type StudyConfig,
} from '../../lib/studyParams'
import { Plus, Search, FolderOpen, Sparkles, CheckCircle2 } from 'lucide-react'
import type { ProjectListItem, DTStage } from '../../types/models'

type StageFilter = 'all' | DTStage

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
const STAGE_FILTERS: { value: StageFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'discover', label: '發現' },
  { value: 'define', label: '定義' },
  { value: 'completed', label: '已完成' },
]

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
  delay,
}: {
  icon: typeof FolderOpen
  label: string
  value: number
  accent: string
  delay: number
}) {
  return (
    <div
      className="card-hover flex items-center gap-4 rounded-2xl bg-surface px-6 py-5 shadow-md"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={cn('animate-icon-breathe flex h-11 w-11 items-center justify-center rounded-xl', accent)}>
        <Icon size={20} />
      </div>
      <div>
        <div className="text-2xl font-bold text-text">{value}</div>
        <div className="text-xs font-medium text-text-muted">{label}</div>
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { projects, isLoading, fetchProjects, deleteProject } = useProjectStore()
  const { user } = useAuthStore()
  const [searchParams, setSearchParams] = useSearchParams()

  // Phase 43（spec/29 §3.1）：study 深連結。lazy initializer 純讀（StrictMode 雙跑安全）；
  // URL 沒參數時讀 sessionStorage 鏡像（重整 / 中途離開再回來延續 study 模式）。
  const [studyConfig, setStudyConfig] = useState<StudyConfig | null>(
    () => parseStudyParams(searchParams) ?? readStudySession(),
  )
  // Phase 43：一旦本分頁進過 study 模式就永久 latch——onCreated 清掉 studyConfig 後，tour 的
  // role 會由 null 翻回真實角色；若不 latch，driver.js 導覽會在建立完成時彈出與 ProjectCreatedDialog 搶焦點。
  const wasStudyRef = useRef(studyConfig !== null)
  const [showCreate, setShowCreate] = useState(false)
  const [justCreated, setJustCreated] = useState<{ id: string; name: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProjectListItem | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [stageFilter, setStageFilter] = useState<StageFilter>('all')

  // 跨頁提示：lobby 等頁面導回時，透過 sessionStorage 帶入一次性 notice（如「無權限」）。
  // 掛載時讀取並立即清除，避免重新整理或返回時重複出現。
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    const pending = sessionStorage.getItem('mc_redirect_notice')
    if (pending) {
      setNotice(pending)
      sessionStorage.removeItem('mc_redirect_notice')
    }
  }, [])

  // Phase 43：消費深連結——鏡像持久化、即拆即清 URL（防 F5 重觸發）、自動開精靈。
  useEffect(() => {
    if (!studyConfig) return
    wasStudyRef.current = true
    saveStudySession(studyConfig)
    if (searchParams.has('study')) setSearchParams({}, { replace: true })
    setShowCreate(true)
    // 只需在掛載時消費一次；studyConfig 由 lazy init 決定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const canCreateProject = user?.role === 'teacher' || user?.can_create_project

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  // 首次進入自動跑 driver.js 漫遊（每個 session 一次）
  // 等 fetchProjects 拿到資料 + DOM render 完再啟動，否則 projects-card anchor 還不存在
  // Phase 43：study 模式抑制（深連結常開新分頁，per-tab 導覽會與自動開啟的精靈互搶焦點）
  useProjectsTourAutoStart({
    role:
      !studyConfig &&
      !wasStudyRef.current &&
      (user?.role === 'teacher' || user?.role === 'student')
        ? user.role
        : null,
    delayMs: isLoading ? 800 : 400,
  })

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
    // 依建立時間由新到舊排序：最新建立的活動排在最上面。
    return [...result].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
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
    <div className="flex flex-col gap-8">
      {notice && (
        <Toast
          message={notice}
          variant="error"
          autoCloseMs={8000}
          onClose={() => setNotice(null)}
        />
      )}

      {/* Welcome Hero + Stats */}
      <div className="flex flex-col gap-6">
        <div data-tour="projects-hero" className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold text-text">{greeting}</h1>
            <p className="mt-1 text-base text-text-muted">管理你的設計思考設計專案</p>
          </div>
          {canCreateProject && (
            <Button
              data-tour="projects-create"
              className="rounded-full px-6"
              onClick={() => setShowCreate(true)}
            >
              <Plus size={16} />
              新增設計專案
            </Button>
          )}
        </div>

        {projects.length > 0 && (
          <div data-tour="projects-stats" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard icon={FolderOpen} label="全部活動" value={stats.total} accent="bg-primary/10 text-primary" delay={0} />
            <StatCard icon={Sparkles} label="進行中" value={stats.active} accent="bg-info/10 text-info" delay={100} />
            <StatCard icon={CheckCircle2} label="已完成" value={stats.completed} accent="bg-success/10 text-success" delay={200} />
          </div>
        )}
      </div>

      {/* Filter + Search */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div data-tour="projects-filters" className="flex flex-wrap gap-2">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStageFilter(f.value)}
              className={cn(
                'rounded-full px-4 py-1.5 text-xs font-medium transition-all cursor-pointer',
                stageFilter === f.value
                  ? 'bg-primary text-text-inverse shadow-sm scale-105'
                  : 'bg-surface text-text-muted shadow-sm hover:text-text hover:shadow-md',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div data-tour="projects-search" className="relative max-w-xs flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜尋設計專案名稱…"
            className="w-full rounded-xl border border-border-light bg-surface py-2.5 pl-9 pr-3 text-sm text-text shadow-sm
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
        <div className="flex flex-col items-center justify-center rounded-2xl bg-bg-warm py-16 text-center">
          <div className="flex items-center justify-center gap-4">
            <StickyNoteSVG color="#F5E6C8" rotation={-6} text="痛點" float floatDelay="0s" />
            <StickyNoteSVG color="#D4E4C8" rotation={3} text="點子" float floatDelay="1s" />
            <StickyNoteSVG color="#C8D8E8" rotation={-2} text="方案" float floatDelay="2s" />
          </div>
          <h3 className="mt-6 text-2xl font-bold text-text">尚無設計專案</h3>
          <p className="mt-2 text-base text-text-muted">
            {canCreateProject ? '點擊「新增設計專案」開始你的設計思考之旅。' : '等待老師邀請你加入設計專案。'}
          </p>
          {canCreateProject && (
            <Button
              data-tour="projects-card"
              className="mt-5 rounded-full px-8"
              onClick={() => setShowCreate(true)}
            >
              建立第一個設計專案
            </Button>
          )}
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-bg-warm py-12 text-center">
          <Search size={32} className="text-text-muted/40" />
          <p className="mt-3 text-sm text-text-muted">找不到符合條件的設計專案</p>
        </div>
      ) : (
        <div className="flex flex-col gap-8">
          {/* Active projects */}
          {activeProjects.length > 0 && (
            <section>
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-muted">
                進行中 ({activeProjects.length})
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {activeProjects.map((project, idx) => (
                  <div
                    key={project.id}
                    {...(idx === 0 ? { 'data-tour': 'projects-card' } : {})}
                  >
                    <ProjectCard
                      project={project}
                      isOwner={project.creator_id === user?.id}
                      onDelete={setDeleteTarget}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Completed projects */}
          {completedProjects.length > 0 && (
            <section>
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-muted">
                已完成 ({completedProjects.length})
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {completedProjects.map((project, idx) => (
                  <div
                    key={project.id}
                    {...(idx === 0 && activeProjects.length === 0
                      ? { 'data-tour': 'projects-card' }
                      : {})}
                  >
                    <ProjectCard
                      project={project}
                      isOwner={project.creator_id === user?.id}
                      onDelete={setDeleteTarget}
                    />
                  </div>
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
        study={studyConfig}
        onCreated={(project) => {
          setShowCreate(false)
          fetchProjects()
          setJustCreated(project)
          // Phase 43：實驗專案建立完成即退出 study 模式（再開精靈回正常空白表單）
          if (studyConfig) {
            clearStudySession()
            setStudyConfig(null)
          }
        }}
      />

      {justCreated && (
        <ProjectCreatedDialog
          isOpen={!!justCreated}
          projectId={justCreated.id}
          projectName={justCreated.name}
          onClose={() => setJustCreated(null)}
        />
      )}

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
