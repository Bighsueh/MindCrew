import { useEffect, useState } from 'react'
import { getTeacherProjects, createStudent, listStudents, getProjectsOverview } from '../../services/teacherService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { StageDistributionBar } from '../../components/teacher/StageDistributionBar'
import { AlertBanner } from '../../components/teacher/AlertBanner'
import { ProjectMonitorCard } from '../../components/teacher/ProjectMonitorCard'
import { Plus, RefreshCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useTeacherDashboardTourAutoStart } from '../../components/onboarding/useTeacherDashboardTourAutoStart'
import type { TeacherProjectSummary, ProjectOverviewResponse, User } from '../../types/models'

interface NewStudentFormData {
  displayName: string
  email: string
  password: string
  canCreateProject: boolean
}

export function TeacherDashboardPage() {
  const { user } = useAuthStore()
  const [overview, setOverview] = useState<ProjectOverviewResponse | null>(null)
  const [students, setStudents] = useState<User[]>([])
  const [isLoadingProjects, setIsLoadingProjects] = useState(true)
  const [isLoadingStudents, setIsLoadingStudents] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState<'projects' | 'students'>('projects')
  const [showAddStudent, setShowAddStudent] = useState(false)
  const [showCreateProject, setShowCreateProject] = useState(false)
  const [studentForm, setStudentForm] = useState<NewStudentFormData>({
    displayName: '',
    email: '',
    password: '',
    canCreateProject: false,
  })
  const [addStudentError, setAddStudentError] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const loadOverview = async () => {
    try {
      const data = await getProjectsOverview()
      setOverview(data)
    } catch {
      // Fallback: overview API might fail, leave null
      setOverview(null)
    }
  }

  useEffect(() => {
    loadOverview().finally(() => setIsLoadingProjects(false))
  }, [])

  // 首次進入自動跑 driver.js 漫遊（每個 session 一次）
  useTeacherDashboardTourAutoStart({
    isLoading: isLoadingProjects,
    delayMs: 500,
  })

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await loadOverview()
    setIsRefreshing(false)
  }

  const loadStudents = () => {
    setIsLoadingStudents(true)
    listStudents()
      .then(setStudents)
      .finally(() => setIsLoadingStudents(false))
  }

  useEffect(() => {
    if (activeTab === 'students' && students.length === 0) {
      loadStudents()
    }
  }, [activeTab]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleAddStudent = async () => {
    setAddStudentError('')
    if (!studentForm.displayName || !studentForm.email || !studentForm.password) {
      setAddStudentError('請填寫所有必填欄位。')
      return
    }
    setIsSaving(true)
    try {
      const newStudent = await createStudent({
        display_name: studentForm.displayName,
        email: studentForm.email,
        password: studentForm.password,
        can_create_project: studentForm.canCreateProject,
      })
      setStudents((prev) => [...prev, newStudent])
      setShowAddStudent(false)
      setStudentForm({ displayName: '', email: '', password: '', canCreateProject: false })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setAddStudentError(status === 409 ? '此電子郵件已被使用。' : '新增失敗，請稍後再試。')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div>
      {/* Page header */}
      <div data-tour="teacher-hero" className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">教師儀表板</h1>
          <p className="mt-1 text-sm text-text-muted">{user?.display_name} 老師</p>
        </div>
        <div className="flex gap-2">
          {activeTab === 'projects' && (
            <Button variant="ghost" size="sm" onClick={handleRefresh} disabled={isRefreshing}>
              <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
              重新整理
            </Button>
          )}
          <Button
            data-tour="teacher-create"
            className="rounded-full px-6"
            onClick={() => setShowCreateProject(true)}
          >
            <Plus size={16} />
            建立新專案
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div data-tour="teacher-tabs" className="border-b border-border-light mb-8">
        <div className="flex gap-0">
          {(['projects', 'students'] as const).map((tab) => (
            <button
              key={tab}
              className={cn(
                'relative px-5 py-3 text-sm font-medium transition-colors cursor-pointer',
                activeTab === tab
                  ? 'text-primary'
                  : 'text-text-muted hover:text-text',
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'projects' ? '專案監控' : '學生管理'}
              {activeTab === tab && (
                <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-primary" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Projects tab */}
      {activeTab === 'projects' && (
        <div className="space-y-4">
          {isLoadingProjects ? (
            <div className="flex justify-center py-16">
              <Loading text="載入監控資料…" />
            </div>
          ) : overview === null || overview.projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl bg-bg-warm py-16">
              <p className="text-lg font-medium text-text">尚無專案</p>
              <p className="mt-1 text-sm text-text-muted">建立你的第一個 Design Thinking 專案</p>
              <Button
                data-tour="teacher-empty-cta"
                className="mt-5 rounded-full px-8"
                onClick={() => setShowCreateProject(true)}
              >
                建立第一個專案
              </Button>
            </div>
          ) : (
            <>
              <div data-tour="teacher-stage-distribution">
                <StageDistributionBar distribution={overview.stage_distribution} />
              </div>
              <div data-tour="teacher-alerts">
                <AlertBanner projects={overview.projects} />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {overview.projects.map((p, idx) => (
                  <div
                    key={p.id}
                    {...(idx === 0 ? { 'data-tour': 'teacher-monitor-card' } : {})}
                  >
                    <ProjectMonitorCard project={p} onRefresh={handleRefresh} />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Students tab */}
      {activeTab === 'students' && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">學生帳號</h2>
            <Button size="sm" onClick={() => setShowAddStudent(true)}>
              <Plus size={14} />
              新增學生
            </Button>
          </div>

          {isLoadingStudents ? (
            <Loading text="載入學生列表…" />
          ) : students.length === 0 ? (
            <div className="rounded-2xl bg-bg-warm py-12 text-center">
              <p className="text-lg font-medium text-text">尚無學生帳號</p>
              <p className="mt-1 text-sm text-text-muted">新增學生以開始管理課堂</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl bg-surface shadow-md">
              <table className="w-full text-left">
                <thead className="border-b border-border-light bg-bg-warm/50">
                  <tr>
                    {['顯示名稱', '電子郵件', '可建立專案', '建立時間'].map((h) => (
                      <th key={h} className="px-5 py-3.5 text-xs font-semibold text-text-muted uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light">
                  {students.map((s) => (
                    <tr key={s.id} className="transition-colors hover:bg-surface-hover">
                      <td className="px-5 py-3.5 font-medium text-text">{s.display_name}</td>
                      <td className="px-5 py-3.5 text-sm text-text-muted">{s.email}</td>
                      <td className="px-5 py-3.5">
                        <span className={cn(
                          'rounded-full px-2.5 py-0.5 text-xs font-medium',
                          s.can_create_project
                            ? 'bg-success-bg text-success'
                            : 'bg-secondary/30 text-text-muted',
                        )}>
                          {s.can_create_project ? '是' : '否'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-sm text-text-muted">
                        {s.created_at
                          ? new Date(s.created_at).toLocaleDateString('zh-TW')
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Add student modal */}
      <Modal
        isOpen={showAddStudent}
        onClose={() => setShowAddStudent(false)}
        title="新增學生帳號"
      >
        <div className="flex flex-col gap-4">
          <Input
            label="顯示名稱"
            value={studentForm.displayName}
            onChange={(e) => setStudentForm((f) => ({ ...f, displayName: e.target.value }))}
            placeholder="王小明"
            required
          />
          <Input
            label="電子郵件"
            type="email"
            value={studentForm.email}
            onChange={(e) => setStudentForm((f) => ({ ...f, email: e.target.value }))}
            placeholder="student@school.edu.tw"
            required
          />
          <Input
            label="初始密碼"
            type="password"
            value={studentForm.password}
            onChange={(e) => setStudentForm((f) => ({ ...f, password: e.target.value }))}
            placeholder="至少 8 個字元"
            required
          />
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={studentForm.canCreateProject}
              onChange={(e) =>
                setStudentForm((f) => ({ ...f, canCreateProject: e.target.checked }))
              }
              className="h-4 w-4 rounded border-border text-primary"
            />
            <span>允許建立專案</span>
          </label>

          {addStudentError && (
            <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
              {addStudentError}
            </div>
          )}

          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => setShowAddStudent(false)}
            >
              取消
            </Button>
            <Button className="flex-1" isLoading={isSaving} onClick={handleAddStudent}>
              新增
            </Button>
          </div>
        </div>
      </Modal>

      <CreateProjectDialog
        isOpen={showCreateProject}
        onClose={() => setShowCreateProject(false)}
        onCreated={() => {
          setShowCreateProject(false)
          loadOverview()
        }}
      />
    </div>
  )
}
