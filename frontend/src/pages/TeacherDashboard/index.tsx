import { useEffect, useState } from 'react'
import { getTeacherProjects, createStudent, listStudents, getProjectsOverview } from '../../services/teacherService'
import { trackProjectByInviteCode } from '../../services/projectService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { StageDistributionBar } from '../../components/teacher/StageDistributionBar'
import { AlertBanner } from '../../components/teacher/AlertBanner'
import { ProjectMonitorCard } from '../../components/teacher/ProjectMonitorCard'
import { Plus, RefreshCw, Copy, Check, Link as LinkIcon } from 'lucide-react'
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
  // Phase 22：複製我的代碼 / 列管活動
  const [copied, setCopied] = useState(false)
  const [trackCode, setTrackCode] = useState('')
  const [trackError, setTrackError] = useState('')
  const [trackSuccess, setTrackSuccess] = useState('')
  const [isTracking, setIsTracking] = useState(false)

  const handleCopyCode = async () => {
    if (!user?.signature_code) return
    try {
      await navigator.clipboard.writeText(user.signature_code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* ignore */
    }
  }

  const handleTrackActivity = async () => {
    const code = trackCode.trim().toUpperCase()
    if (code.length < 4) {
      setTrackError('請輸入學生的活動代碼')
      return
    }
    setTrackError('')
    setTrackSuccess('')
    setIsTracking(true)
    try {
      const project = await trackProjectByInviteCode(code)
      setTrackSuccess(`已加入指導「${project.name}」`)
      setTrackCode('')
      await loadOverview()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setTrackError(detail ?? '加入失敗，請確認代碼是否正確')
    } finally {
      setIsTracking(false)
    }
  }

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
      <div data-tour="teacher-hero" className="mb-4 flex items-center justify-between">
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
            建立新設計專案
          </Button>
        </div>
      </div>

      {/* Phase 22：教師代碼 + 列管活動 */}
      <div className="mb-8 flex flex-col gap-3 rounded-2xl bg-surface px-6 py-5 shadow-sm sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            我的教師代碼
          </span>
          <div className="flex items-center gap-2">
            <code className="rounded-md bg-bg-warm px-3 py-1.5 font-mono text-lg font-semibold tracking-widest text-text">
              {user?.signature_code ?? '—'}
            </code>
            <button
              type="button"
              onClick={handleCopyCode}
              disabled={!user?.signature_code}
              className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs text-text-muted transition-colors hover:bg-bg-warm hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? '已複製' : '複製'}
            </button>
          </div>
          <p className="text-xs text-text-muted">
            學生建立設計專案時輸入此代碼，活動就會出現在你的儀表板。
          </p>
        </div>

        <div className="flex flex-col gap-1.5 sm:items-end">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            加入學生的設計專案
          </span>
          <div className="flex items-center gap-2">
            <Input
              value={trackCode}
              onChange={(e) => setTrackCode(e.target.value.toUpperCase())}
              placeholder="學生的活動代碼，例：QF73TE"
              className="w-36 font-mono uppercase tracking-widest"
            />
            <Button
              size="sm"
              onClick={handleTrackActivity}
              isLoading={isTracking}
              disabled={!trackCode.trim()}
            >
              <LinkIcon size={14} />
              加入指導
            </Button>
          </div>
          {trackError && (
            <span className="text-xs text-error">{trackError}</span>
          )}
          {trackSuccess && (
            <span className="text-xs text-success">{trackSuccess}</span>
          )}
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
              {tab === 'projects' ? '設計專案監控' : '學生管理'}
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
              <p className="text-2xl font-bold text-text">尚無設計專案</p>
              <p className="mt-2 text-base text-text-muted">建立你的第一個 Design Thinking 設計專案</p>
              <Button
                data-tour="teacher-empty-cta"
                className="mt-5 rounded-full px-8"
                onClick={() => setShowCreateProject(true)}
              >
                建立第一個設計專案
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
                    {['顯示名稱', '電子郵件', '可建立活動', '建立時間'].map((h) => (
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
            <span>允許建立設計專案</span>
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
