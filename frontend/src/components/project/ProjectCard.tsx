import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, Bot, MoreVertical, Trash2, Clock } from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatRelativeTime } from '../../utils/formatters'
import type { ProjectListItem, DTStage } from '../../types/models'

interface ProjectCardProps {
  project: ProjectListItem
  isOwner: boolean
  onDelete: (project: ProjectListItem) => void
}

const STAGE_ORDER: DTStage[] = ['discover', 'define', 'develop', 'deliver']

const STAGE_BORDER_COLORS: Record<DTStage, string> = {
  discover: 'bg-primary',
  define: 'bg-accent',
  develop: 'bg-warning',
  deliver: 'bg-success',
  completed: 'bg-success',
}

const STAGE_BG_TINTS: Record<DTStage, string> = {
  discover: 'hover:bg-[#fefce8]/40',
  define: 'hover:bg-[#fef3e2]/40',
  develop: 'hover:bg-[#fdf5ee]/40',
  deliver: 'hover:bg-[#faf0e6]/40',
  completed: 'hover:bg-[#f0fdf4]/30',
}

const STAGE_LABELS: Record<DTStage, string> = {
  discover: 'Discover',
  define: 'Define',
  develop: 'Develop',
  deliver: 'Deliver',
  completed: '已完成',
}

const STAGE_TAG_COLORS: Record<DTStage, string> = {
  discover: 'bg-primary/10 text-primary',
  define: 'bg-accent/20 text-accent',
  develop: 'bg-warning/10 text-warning',
  deliver: 'bg-success/10 text-success',
  completed: 'bg-success/10 text-success',
}


function StageProgressBar({ currentStage }: { currentStage: DTStage }) {
  const currentIdx = currentStage === 'completed'
    ? STAGE_ORDER.length
    : STAGE_ORDER.indexOf(currentStage)

  return (
    <div className="flex gap-1">
      {STAGE_ORDER.map((stage, i) => (
        <div
          key={stage}
          className={cn(
            'h-1 flex-1 rounded-full transition-colors',
            i <= currentIdx ? STAGE_BORDER_COLORS[stage] : 'bg-border/50',
          )}
        />
      ))}
    </div>
  )
}

export function ProjectCard({ project, isOwner, onDelete }: ProjectCardProps) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen])

  return (
    <div
      className={cn(
        'card-hover-warm group relative flex cursor-pointer overflow-hidden rounded-2xl border border-border-light',
        'bg-surface shadow-md transition-all',
        STAGE_BG_TINTS[project.current_stage],
      )}
      onClick={() => navigate(`/projects/${project.id}/lobby`)}
    >
      {/* Left color accent bar */}
      <div className={cn('w-1.5 shrink-0', STAGE_BORDER_COLORS[project.current_stage])} />

      <div className="flex flex-1 flex-col gap-3 p-5">
        {/* Header row: title + menu */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-semibold text-text group-hover:text-primary">
              {project.name}
            </h3>
            {project.description && (
              <p className="mt-0.5 line-clamp-1 text-sm text-text-muted">
                {project.description}
              </p>
            )}
          </div>

          {/* Context menu */}
          {isOwner && (
            <div ref={menuRef} className="relative shrink-0">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setMenuOpen((prev) => !prev)
                }}
                className={cn(
                  'rounded-md p-1.5 text-text-muted transition-colors cursor-pointer',
                  'hover:bg-surface-hover hover:text-text',
                  menuOpen ? 'bg-surface-hover text-text' : 'opacity-0 group-hover:opacity-100',
                )}
                aria-label="活動選單"
              >
                <MoreVertical size={16} />
              </button>

              {menuOpen && (
                <div
                  className="absolute right-0 top-full z-20 mt-1 w-36 overflow-hidden rounded-lg
                             border border-border bg-surface py-1 shadow-lg"
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuOpen(false)
                      onDelete(project)
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-error
                               hover:bg-error-bg transition-colors cursor-pointer"
                  >
                    <Trash2 size={14} />
                    刪除活動
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Stage progress bar */}
        <StageProgressBar currentStage={project.current_stage} />

        {/* Footer: stage tag + stats + time */}
        <div className="flex items-center gap-3 text-xs text-text-muted">
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 font-medium',
              STAGE_TAG_COLORS[project.current_stage],
            )}
          >
            {STAGE_LABELS[project.current_stage]}
          </span>

          <span className="flex items-center gap-1">
            <Users size={12} />
            {project.seat_summary.human}
          </span>
          <span className="flex items-center gap-1">
            <Bot size={12} />
            {project.seat_summary.ai}
          </span>

          <span className="ml-auto flex items-center gap-1">
            <Clock size={12} />
            {formatRelativeTime(project.updated_at)}
          </span>
        </div>
      </div>
    </div>
  )
}
