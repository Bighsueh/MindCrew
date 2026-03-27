import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import type { Project } from '../../types/models'

const STAGE_LABELS = {
  discover: '🔍 發現',
  define: '📌 定義',
  develop: '💡 發展',
  deliver: '🚀 交付',
  completed: '✅ 完成',
}

const STATUS_LABELS = {
  active: '進行中',
  completed: '已完成',
  archived: '已封存',
}

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate()

  return (
    <div
      className="group cursor-pointer rounded-xl border border-gray-200 bg-white p-6 shadow-sm
                 transition-all duration-200 hover:border-blue-300 hover:shadow-md"
      onClick={() => navigate(`/projects/${project.id}/lobby`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="truncate text-base font-semibold text-gray-900 group-hover:text-blue-600">
            {project.name}
          </h3>
          {project.description && (
            <p className="mt-1 line-clamp-2 text-sm text-gray-500">{project.description}</p>
          )}
        </div>
        <span
          className={[
            'flex-shrink-0 rounded-full px-2.5 py-1 text-xs font-medium',
            project.status === 'active'
              ? 'bg-green-100 text-green-700'
              : project.status === 'completed'
                ? 'bg-gray-100 text-gray-600'
                : 'bg-yellow-100 text-yellow-700',
          ].join(' ')}
        >
          {STATUS_LABELS[project.status]}
        </span>
      </div>

      <div className="mt-4 flex items-center gap-4 text-sm text-gray-500">
        <span>{STAGE_LABELS[project.current_stage]}</span>
        {project.seat_summary && (
          <span>
            👥 {project.seat_summary.human} 人類 / 🤖 {project.seat_summary.ai} AI
          </span>
        )}
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { projects, isLoading, fetchProjects } = useProjectStore()
  const { user } = useAuthStore()

  const canCreateProject =
    user?.role === 'teacher' || user?.can_create_project

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">🧠 MindCrew</h1>
            <p className="text-sm text-gray-500">設計思考 AI 協作平台</p>
          </div>
          <div className="flex items-center gap-3">
            {user?.role === 'teacher' && (
              <Link to="/teacher/dashboard">
                <Button variant="ghost" size="sm">
                  📊 教師儀表板
                </Button>
              </Link>
            )}
            <span className="text-sm text-gray-600">{user?.display_name}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => useAuthStore.getState().logout()}
            >
              登出
            </Button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">我的專案</h2>
          {canCreateProject && (
            <Link to="/projects/new">
              <Button>+ 新增專案</Button>
            </Link>
          )}
        </div>

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loading text="載入專案中…" />
          </div>
        ) : projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 bg-white py-16 text-center">
            <div className="text-5xl mb-4">📋</div>
            <h3 className="text-base font-medium text-gray-700">尚無專案</h3>
            <p className="mt-1 text-sm text-gray-400">
              {canCreateProject ? '點擊「新增專案」開始你的設計思考之旅。' : '等待老師邀請你加入專案。'}
            </p>
            {canCreateProject && (
              <Link to="/projects/new" className="mt-4">
                <Button>建立第一個專案</Button>
              </Link>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
