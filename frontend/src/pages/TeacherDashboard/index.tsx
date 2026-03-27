import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTeacherProjects, createStudent, listStudents } from '../../services/teacherService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { CreateProjectDialog } from '../../components/project/CreateProjectDialog'
import { Eye, LogIn, Users, Bot, Plus } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { TeacherProjectSummary, User } from '../../types/models'

function ProjectCard({ project }: { project: TeacherProjectSummary }) {
  const navigate = useNavigate()

  const lastActivity = new Date(project.last_activity).toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-text truncate">{project.name}</h3>
          <p className="text-xs text-text-muted mt-0.5">最近活動：{lastActivity}</p>
        </div>
        <PhaseIndicator phase={project.current_stage} />
      </div>

      <div className="flex items-center gap-3 text-sm text-text-muted mb-4">
        <span className="flex items-center gap-1"><Users size={14} />{project.seat_summary.human} 人類</span>
        <span className="flex items-center gap-1"><Bot size={14} />{project.seat_summary.ai} AI</span>
        <span>{project.note_count} 張便條</span>
      </div>

      <div className="flex gap-2">
        <Button
          size="sm"
          variant="ghost"
          className="flex-1 gap-1"
          onClick={() => navigate(`/projects/${project.id}/lobby`)}
        >
          <Eye size={14} />
          觀察
        </Button>
        <Button
          size="sm"
          variant="secondary"
          className="flex-1 gap-1"
          onClick={() => navigate(`/projects/${project.id}/lobby`)}
        >
          <LogIn size={14} />
          進入
        </Button>
      </div>
    </div>
  )
}

interface NewStudentFormData {
  displayName: string
  email: string
  password: string
  canCreateProject: boolean
}

export function TeacherDashboardPage() {
  const { user } = useAuthStore()
  const [projects, setProjects] = useState<TeacherProjectSummary[]>([])
  const [students, setStudents] = useState<User[]>([])
  const [isLoadingProjects, setIsLoadingProjects] = useState(true)
  const [isLoadingStudents, setIsLoadingStudents] = useState(false)
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

  useEffect(() => {
    getTeacherProjects()
      .then(setProjects)
      .finally(() => setIsLoadingProjects(false))
  }, [])

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
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text">教師儀表板</h1>
          <p className="text-sm text-text-muted">{user?.display_name} 老師</p>
        </div>
        <Button onClick={() => setShowCreateProject(true)}>
          <Plus size={16} />
          建立新專案
        </Button>
      </div>

      {/* Tabs */}
      <div className="border-b border-border mb-6">
        <div className="flex gap-0">
          {(['projects', 'students'] as const).map((tab) => (
            <button
              key={tab}
              className={cn(
                'px-5 py-3 text-sm font-medium border-b-2 transition-colors cursor-pointer',
                activeTab === tab
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-muted hover:text-text',
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'projects' ? '專案監控' : '學生管理'}
            </button>
          ))}
        </div>
      </div>

      {/* Projects tab */}
      {activeTab === 'projects' && (
        <div>
          {isLoadingProjects ? (
            <div className="flex justify-center py-16">
              <Loading text="載入專案…" />
            </div>
          ) : projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-surface py-16">
              <p className="text-text-muted">尚無專案。</p>
              <Button className="mt-4" onClick={() => setShowCreateProject(true)}>
                建立第一個專案
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((p) => (
                <ProjectCard key={p.id} project={p} />
              ))}
            </div>
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
            <div className="rounded-xl border-2 border-dashed border-border bg-surface py-12 text-center">
              <p className="text-text-muted">尚無學生帳號。</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
              <table className="w-full text-left">
                <thead className="border-b border-border bg-bg">
                  <tr>
                    {['顯示名稱', '電子郵件', '可建立專案', '建立時間'].map((h) => (
                      <th key={h} className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {students.map((s) => (
                    <tr key={s.id} className="hover:bg-surface-hover">
                      <td className="px-4 py-3 font-medium text-text">{s.display_name}</td>
                      <td className="px-4 py-3 text-sm text-text-muted">{s.email}</td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          'rounded-full px-2.5 py-0.5 text-xs font-medium',
                          s.can_create_project
                            ? 'bg-success-bg text-success'
                            : 'bg-secondary/30 text-text-muted',
                        )}>
                          {s.can_create_project ? '是' : '否'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-text-muted">
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
          getTeacherProjects().then(setProjects)
        }}
      />
    </div>
  )
}
