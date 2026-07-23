import { useState } from 'react'
import {
  Copy,
  Check,
  Link as LinkIcon,
  X,
  GraduationCap,
  ChevronDown,
} from 'lucide-react'
import { Button } from '../../components/common/Button'
import { Input } from '../../components/common/Input'
import { cn } from '../../lib/utils'
import { linkTeacher, unlinkTeacher } from '../../services/projectService'
import { useAuthStore } from '../../stores/authStore'
import { useProjectStore } from '../../stores/projectStore'
import type { Project } from '../../types/models'

interface Props {
  project: Project
}

type ViewState =
  | { kind: 'student_unlinked' }
  | { kind: 'student_linked' }
  | { kind: 'teacher_view' }
  | { kind: 'hidden' }

/** Phase 22 / UX revamp：邀請老師指導
 *
 * 整塊以「獨立一條橫向 bar」呈現，貼在活動標題下方。
 *
 *  A student_unlinked  學生 creator、未列管 → headline + 兩條路徑（左右並排，中間「或」）
 *  B student_linked    學生 creator、已列管 → 狀態 chip + 活動碼小字 + 解除
 *  C teacher_view      老師（creator 或 linked） → 狀態 chip + 解除指導
 *  D hidden            旁觀者 → 不顯示
 */
export function LobbyEnrollmentRow({ project }: Props) {
  const { user } = useAuthStore()
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject)

  const [copied, setCopied] = useState(false)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // 未列管時整塊預設收合——這是選填動作，不該佔據大廳主視線。
  const [expanded, setExpanded] = useState(false)

  const isCreator = !!user && user.id === project.creator_id
  const isLinkedTeacher = !!user && user.id === project.linked_teacher?.id
  const isTeacherRole = user?.role === 'teacher'

  const view: ViewState = (() => {
    if (isTeacherRole && (isCreator || isLinkedTeacher)) {
      return { kind: 'teacher_view' }
    }
    if (isCreator) {
      return project.linked_teacher
        ? { kind: 'student_linked' }
        : { kind: 'student_unlinked' }
    }
    return { kind: 'hidden' }
  })()

  if (view.kind === 'hidden') return null

  const handleCopy = async () => {
    if (!project.invite_code) return
    try {
      await navigator.clipboard.writeText(project.invite_code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* ignore */
    }
  }

  const handleLink = async () => {
    const trimmed = code.trim().toUpperCase()
    if (trimmed.length < 4) {
      setError('請輸入老師代碼')
      return
    }
    setError('')
    setBusy(true)
    try {
      const updated = await linkTeacher(project.id, trimmed)
      setCurrentProject(updated)
      setCode('')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail ?? '邀請失敗，請確認代碼是否正確')
    } finally {
      setBusy(false)
    }
  }

  const handleUnlink = async () => {
    if (!window.confirm('確定要解除指導關係嗎？解除後老師將不再看到這個活動。')) {
      return
    }
    setBusy(true)
    setError('')
    try {
      const updated = await unlinkTeacher(project.id)
      setCurrentProject(updated)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail ?? '解除失敗')
    } finally {
      setBusy(false)
    }
  }

  // ── A：未列管 → 可摺疊揭示（預設收合，標題列即為展開開關） ──
  if (view.kind === 'student_unlinked') {
    return (
      <div className="rounded-xl border border-border-light bg-surface/60">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1.5 rounded-xl px-5 py-3 text-xs font-semibold uppercase tracking-wide text-text-muted transition-colors hover:text-text"
        >
          <GraduationCap size={14} />
          邀請老師指導這個活動
          <span className="ml-1 text-[11px] font-normal normal-case tracking-normal text-text-muted/60">
            選填
          </span>
          <ChevronDown
            size={16}
            className={cn(
              'ml-auto text-text-muted transition-transform duration-200',
              expanded && 'rotate-180',
            )}
          />
        </button>

        {expanded && (
          <div className="px-5 pb-4">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              {/* 路徑 1：分享我的活動代碼 */}
              <div className="flex flex-1 flex-col gap-1.5">
                <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                  我的活動代碼
                </span>
                <div className="flex items-center gap-2">
                  <code className="rounded-md bg-bg-warm px-2.5 py-1 font-mono text-sm font-semibold tracking-widest text-text">
                    {project.invite_code ?? '—'}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopy}
                    disabled={!project.invite_code}
                    className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-text-muted transition-colors hover:bg-bg-warm hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                    {copied ? '已複製' : '複製'}
                  </button>
                </div>
                <p className="text-[11px] leading-snug text-text-muted">
                  把這個碼給老師，他在儀表板輸入後即可看到這個活動。
                </p>
              </div>

              {/* Divider — 桌面為直線「或」，行動為橫線 */}
              <div className="flex items-center sm:flex-col sm:self-stretch sm:px-1">
                <span className="h-px flex-1 bg-border-light sm:h-auto sm:w-px sm:flex-1" />
                <span className="px-2 text-[11px] uppercase tracking-wider text-text-muted/70 sm:py-1">
                  或
                </span>
                <span className="h-px flex-1 bg-border-light sm:h-auto sm:w-px sm:flex-1" />
              </div>

              {/* 路徑 2：輸入老師代碼 */}
              <div className="flex flex-1 flex-col gap-1.5">
                <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                  輸入老師代碼
                </span>
                <div className="flex items-center gap-2">
                  <Input
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    placeholder="例：MD7K2A"
                    className="h-7 w-36 font-mono text-sm uppercase tracking-widest"
                    maxLength={8}
                  />
                  <Button
                    size="sm"
                    onClick={handleLink}
                    isLoading={busy}
                    disabled={!code.trim()}
                  >
                    <LinkIcon size={14} />
                    邀請
                  </Button>
                </div>
                <p className="text-[11px] leading-snug text-text-muted">
                  如果老師先給了你他的代碼，輸入後即可邀請他指導。
                </p>
                {error && (
                  <span className="text-[11px] text-error">{error}</span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── B / C：已列管 / 老師視角 → 常駐狀態卡（單行狀態，毋須收合） ──
  return (
    <div className="rounded-xl border border-border-light bg-surface/60 px-5 py-4">
      {/* Headline */}
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <GraduationCap size={14} />
        {view.kind === 'student_linked' && '指導老師'}
        {view.kind === 'teacher_view' && '指導關係'}
      </div>

      {/* ── B：學生已列管 ── */}
      {view.kind === 'student_linked' && project.linked_teacher && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="inline-flex h-7 items-center rounded-full bg-success-bg px-3 text-xs font-medium text-success">
            已由 {project.linked_teacher.display_name} 指導
          </span>
          <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
            <span>活動代碼</span>
            <code className="rounded bg-bg-warm px-1.5 py-0.5 font-mono font-semibold tracking-widest text-text">
              {project.invite_code ?? '—'}
            </code>
            <button
              type="button"
              onClick={handleCopy}
              disabled={!project.invite_code}
              className="inline-flex items-center rounded p-0.5 hover:text-text disabled:opacity-40"
              title="複製"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
          </div>
          <button
            type="button"
            onClick={handleUnlink}
            disabled={busy}
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-text-muted transition-colors hover:bg-error-bg hover:text-error"
          >
            <X size={12} />
            解除
          </button>
          {error && (
            <span className="basis-full text-[11px] text-error">{error}</span>
          )}
        </div>
      )}

      {/* ── C：老師 view ── */}
      {view.kind === 'teacher_view' && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="inline-flex h-7 items-center rounded-full bg-success-bg px-3 text-xs font-medium text-success">
            你是這個活動的指導老師
          </span>
          <button
            type="button"
            onClick={handleUnlink}
            disabled={busy || isCreator}
            title={isCreator ? '你是活動建立者，無法解除' : '解除指導'}
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-text-muted transition-colors hover:bg-error-bg hover:text-error disabled:cursor-not-allowed disabled:opacity-40"
          >
            <X size={12} />
            解除指導
          </button>
          {error && (
            <span className="basis-full text-[11px] text-error">{error}</span>
          )}
        </div>
      )}
    </div>
  )
}
