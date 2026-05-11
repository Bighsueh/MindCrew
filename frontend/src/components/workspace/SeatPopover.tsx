import { useEffect, useRef } from 'react'
import { Bot, Crown, Hourglass, User, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'
import {
  AXIS_LABEL,
  AXIS_TONE,
  LENS_LABEL,
  LensBar,
} from '../persona/personaLabels'

export type SeatStatus = 'online' | 'typing' | 'thinking' | 'offline'

interface SeatPopoverProps {
  seat: Seat
  status: SeatStatus
  displayName: string
  roleLabel: string
  preview?: string
  isCurrentUser: boolean
  onClose: () => void
}

const STATUS_TEXT: Record<SeatStatus, string> = {
  online: '在線',
  typing: '正在輸入…',
  thinking: '正在思考…',
  offline: '離線',
}

function getRoleKindLabel(seat: Seat): string {
  if (seat.seat_role === 'supervisor') return '老師'
  return seat.occupant_type === 'ai' ? 'AI 助理' : '人類學員'
}

function AvatarCircle({ seat, dormant }: { seat: Seat; dormant: boolean }) {
  const isSupervisor = seat.seat_role === 'supervisor'
  const isAI = seat.occupant_type === 'ai'
  const Icon = isSupervisor ? Crown : isAI ? Bot : User
  return (
    <div
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
        isSupervisor && 'border-2 border-supervisor bg-supervisor/10 text-supervisor',
        !isSupervisor && isAI && 'border-2 border-dashed border-border text-text-muted',
        !isSupervisor && !isAI && 'border-2 border-accent bg-accent/10 text-accent',
        dormant && 'opacity-50',
      )}
    >
      <Icon size={18} />
    </div>
  )
}

export function SeatPopover({
  seat,
  status,
  displayName,
  roleLabel,
  preview,
  isCurrentUser,
  onClose,
}: SeatPopoverProps) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [onClose])

  const isAI = seat.occupant_type === 'ai'
  const isHuman = seat.occupant_type === 'human'
  const dormant = isAI && seat.is_active === false
  const persona = seat.persona ?? null
  const axisLabel = persona ? AXIS_LABEL[persona.personality_axis] : null
  const axisTone = persona ? AXIS_TONE[persona.personality_axis] : null

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={`${displayName} 資料卡`}
      className={cn(
        'absolute bottom-full left-1/2 z-50 mb-2 w-80 -translate-x-1/2',
        'animate-popover-enter rounded-xl border border-border bg-surface shadow-xl',
        'max-h-[70vh] overflow-auto',
      )}
      style={{ transformOrigin: 'bottom center' }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-4 pb-3 pt-4">
        <AvatarCircle seat={seat} dormant={dormant} />
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-text">{displayName}</span>
            {isCurrentUser && (
              <span className="inline-flex items-center rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                你
              </span>
            )}
            {dormant && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-bg-warm px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                <Hourglass size={9} />
                尚未上線
              </span>
            )}
          </div>
          <span className="mt-0.5 text-[11px] text-text-muted">
            {roleLabel} · {getRoleKindLabel(seat)}
          </span>
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-text-muted">
            <span
              className={cn(
                'inline-block h-2 w-2 rounded-full',
                status === 'online' && 'bg-success',
                status === 'typing' && 'animate-pulse bg-accent',
                status === 'thinking' && 'animate-pulse bg-accent',
                status === 'offline' && 'bg-border',
              )}
            />
            <span>{STATUS_TEXT[status]}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="關閉資料卡"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <X size={14} />
        </button>
      </div>

      {/* Persona section (AI only) */}
      {isAI && persona && (
        <div className="border-t border-border-light px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {axisLabel && axisTone && (
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                  axisTone,
                )}
              >
                {axisLabel}
              </span>
            )}
            {persona.role && (
              <span className="text-xs text-text-muted">{persona.role}</span>
            )}
          </div>

          {persona.expertise && (
            <PersonaField label="專長">{persona.expertise}</PersonaField>
          )}
          {persona.personality_desc && (
            <PersonaField label="個性">{persona.personality_desc}</PersonaField>
          )}
          {persona.backstory && (
            <PersonaField label="背景">
              <span className="line-clamp-3">{persona.backstory}</span>
            </PersonaField>
          )}

          <div className="mt-3 flex flex-col gap-1.5 border-t border-border-light/60 pt-2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              認知透鏡
            </div>
            <div className="flex flex-col gap-1">
              {(Object.keys(LENS_LABEL) as Array<keyof typeof LENS_LABEL>).map(
                (lens) => (
                  <LensBar
                    key={lens}
                    label={LENS_LABEL[lens]}
                    value={persona.lens_affinities[lens]}
                    compact
                  />
                ),
              )}
            </div>
          </div>
        </div>
      )}

      {/* Human placeholder section */}
      {isHuman && (
        <div className="border-t border-border-light px-4 py-3 text-[11px] text-text-muted">
          人類成員——尚未提供個人簡介
        </div>
      )}

      {/* Recent preview */}
      {preview && (
        <div className="border-t border-border-light px-4 py-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            最近發言
          </div>
          <div className="line-clamp-2 rounded bg-bg-warm px-2 py-1.5 text-[11px] leading-relaxed text-text-muted">
            {preview}
          </div>
        </div>
      )}

    </div>
  )
}

interface PersonaFieldProps {
  label: string
  children: React.ReactNode
}

function PersonaField({ label, children }: PersonaFieldProps) {
  return (
    <div className="mt-2 flex flex-col gap-0.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className="text-xs leading-snug text-text">{children}</div>
    </div>
  )
}
