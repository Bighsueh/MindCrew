import { useEffect, useRef } from 'react'
import { Bot, Crown, User } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'

export type SeatStatus = 'online' | 'typing' | 'thinking' | 'offline'

interface SeatPopoverProps {
  seat: Seat
  status: SeatStatus
  displayName: string
  roleLabel: string
  preview?: string
  onClose: () => void
  onDirectMessage?: (seat: Seat) => void
  onProfileClick?: (seat: Seat) => void
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

function getRoleIcon(seat: Seat) {
  if (seat.seat_role === 'supervisor') return <Crown size={14} className="text-supervisor" />
  if (seat.occupant_type === 'ai') return <Bot size={14} className="text-accent" />
  return <User size={14} className="text-text-muted" />
}

export function SeatPopover({
  seat,
  status,
  displayName,
  roleLabel,
  preview,
  onClose,
  onDirectMessage,
  onProfileClick,
}: SeatPopoverProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const idleTimerRef = useRef<number | null>(null)

  useEffect(() => {
    const resetIdle = () => {
      if (idleTimerRef.current !== null) window.clearTimeout(idleTimerRef.current)
      idleTimerRef.current = window.setTimeout(onClose, 6000)
    }
    resetIdle()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onActivity = () => resetIdle()

    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    ref.current?.addEventListener('mousemove', onActivity)
    ref.current?.addEventListener('click', onActivity)

    return () => {
      if (idleTimerRef.current !== null) window.clearTimeout(idleTimerRef.current)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [onClose])

  const isAI = seat.occupant_type === 'ai'

  return (
    <div
      ref={ref}
      role="dialog"
      className={cn(
        'absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2',
        'animate-popover-enter rounded-lg border border-border bg-surface p-3 shadow-lg',
      )}
      style={{ transformOrigin: 'bottom center' }}
    >
      <div className="flex items-center gap-2">
        {getRoleIcon(seat)}
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-semibold text-text">{displayName}</span>
          <span className="text-[11px] text-text-muted">
            {roleLabel} · {getRoleKindLabel(seat)}
          </span>
        </div>
      </div>

      <div className="mt-2 text-xs text-text-muted">
        <span
          className={cn(
            'inline-block h-2 w-2 rounded-full align-middle',
            status === 'online' && 'bg-success',
            status === 'typing' && 'bg-accent',
            status === 'thinking' && 'bg-accent',
            status === 'offline' && 'bg-border',
          )}
        />
        <span className="ml-1.5 align-middle">{STATUS_TEXT[status]}</span>
      </div>

      {preview && (
        <div className="mt-2 line-clamp-1 rounded bg-bg-warm px-2 py-1 text-[11px] text-text-muted">
          {preview}
        </div>
      )}

      <div className="mt-3 flex gap-1.5">
        {isAI && onDirectMessage && (
          <button
            type="button"
            onClick={() => {
              onDirectMessage(seat)
              onClose()
            }}
            className="flex-1 rounded-md bg-accent/15 px-2 py-1 text-xs font-medium text-accent transition hover:bg-accent/25"
          >
            私訊
          </button>
        )}
        {onProfileClick && (
          <button
            type="button"
            onClick={() => {
              onProfileClick(seat)
              onClose()
            }}
            className="flex-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-text-muted transition hover:bg-surface-hover"
          >
            查看簡介
          </button>
        )}
      </div>
    </div>
  )
}
