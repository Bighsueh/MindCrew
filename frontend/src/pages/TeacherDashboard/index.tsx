import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getTeacherProjects, createStudent, listStudents } from '../../services/teacherService'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import type { TeacherProjectSummary, User } from '../../types/models'

const STAGE_LABELS = {
  discover: '🔍 發現',
  define: '📌 定義',
  develop: '💡 發展',
  deliver: '🚀 交付',
  completed: '✅ 完成',
}

function ProjectRow({ project }: { project: TeacherProjectSummary }) {
  const navigate = useNavigate()

  const lastActivity = new Date(project.last_activity).toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3">
        <p className="font-medium text-gray-900">{project.name}</p>
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {STAGE_LABELS[project.current_stage]}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        👤 {project.seat_summary.human} / 🤖 {project.seat_summary.ai}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {project.note_count} 張便條
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">{lastActivity}</td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => navigate(`/projects/${project.id}/lobby`)}
          >
            觀察
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => navigate(`/teacher/projects/${project.id}/record`)}
          >
            紀錄
          </Button>
        </div>
      </td>
    </tr>
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Link to="/projects" className="text-sm text-gray-500 hover:text-gray-700">
                ← 返回
              </Link>
              <span className="text-gray-300">|</span>
              <h1 className="text-xl font-bold text-gray-900">📊 教師儀表板</h1>
            </div>
            <p className="text-sm text-gray-500">{user?.display_name} 老師</p>
          </div>
          <Link to="/projects/new">
            <Button>+ 建立新專案</Button>
          </Link>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex gap-0">
            {(['projects', 'students'] as const).map((tab) => (
              <button
                key={tab}
                className={[
                  'px-5 py-3 text-sm font-medium border-b-2 transition-colors',
                  activeTab === tab
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700',
                ].join(' ')}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'projects' ? '專案監控' : '學生管理'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main */}
      <main className="mx-auto max-w-6xl px-6 py-6">
        {/* Projects tab */}
        {activeTab === 'projects' && (
          <div>
            {isLoadingProjects ? (
              <div className="flex justify-center py-16">
                <Loading text="載入專案…" />
              </div>
            ) : projects.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 bg-white py-16">
                <p className="text-gray-500">尚無專案。</p>
                <Link to="/projects/new" className="mt-4">
                  <Button>建立第一個專案</Button>
                </Link>
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="w-full text-left">
                  <thead className="border-b border-gray-200 bg-gray-50">
                    <tr>
                      {['專案名稱', '目前階段', '席位', '便條紙', '最近活動', '操作'].map((h) => (
                        <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {projects.map((p) => (
                      <ProjectRow key={p.id} project={p} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Students tab */}
        {activeTab === 'students' && (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-800">學生帳號</h2>
              <Button size="sm" onClick={() => setShowAddStudent(true)}>
                + 新增學生
              </Button>
            </div>

            {isLoadingStudents ? (
              <Loading text="載入學生列表…" />
            ) : students.length === 0 ? (
              <div className="rounded-xl border-2 border-dashed border-gray-300 bg-white py-12 text-center">
                <p className="text-gray-500">尚無學生帳號。</p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="w-full text-left">
                  <thead className="border-b border-gray-200 bg-gray-50">
                    <tr>
                      {['顯示名稱', '電子郵件', '可建立專案', '建立時間'].map((h) => (
                        <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {students.map((s) => (
                      <tr key={s.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{s.display_name}</td>
                        <td className="px-4 py-3 text-sm text-gray-600">{s.email}</td>
                        <td className="px-4 py-3">
                          <span className={[
                            'rounded-full px-2.5 py-0.5 text-xs font-medium',
                            s.can_create_project
                              ? 'bg-green-100 text-green-700'
                              : 'bg-gray-100 text-gray-500',
                          ].join(' ')}>
                            {s.can_create_project ? '是' : '否'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-500">
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
      </main>

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
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={studentForm.canCreateProject}
              onChange={(e) =>
                setStudentForm((f) => ({ ...f, canCreateProject: e.target.checked }))
              }
              className="h-4 w-4 rounded border-gray-300 text-blue-600"
            />
            <span>允許建立專案</span>
          </label>

          {addStudentError && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
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
    </div>
  )
}
