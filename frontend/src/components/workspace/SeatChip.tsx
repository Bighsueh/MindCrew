import { useEffect, useState } from 'react'
import { Bot } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'
import { SeatPopover, type SeatStatus } from './SeatPopover'
import { SeatIcon } from '../../lib/seatIcons'

interface SeatChipProps {
  seat: Seat
  isCurrentUser: boolean
  label: string
  displayName: string
  status: SeatStatus
  speechBubble?: { key: number; preview: string }
  preview?: string
  isPopoverOpen: boolean
  onOpenPopover: () => void
  onClosePopover: () => void
}

export function SeatChip({
  seat,
  isCurrentUser,
  label,
  displayName,
  status,
  speechBubble,
  preview,
  isPopoverOpen,
  onOpenPopover,
  onClosePopover,
}: SeatChipProps) {
  const isAI = seat.occupant_type === 'ai'
  const isSupervisor = seat.seat_role === 'supervisor'
  const isThinking = isAI && status === 'thinking'

  const [bubbleVisible, setBubbleVisible] = useState(false)
  useEffect(() => {
    if (!speechBubble) return
    setBubbleVisible(true)
    const t = window.setTimeout(() => setBubbleVisible(false), 720)
    return () => window.clearTimeout(t)
  }, [speechBubble?.key])


  return (
    <div className="relative flex-shrink-0">
      {bubbleVisible && speechBubble && (
        <span
          key={speechBubble.key}
          className="animate-speech-pop pointer-events-none absolute left-1/2 -top-5 z-40 whitespace-nowrap rounded-full bg-surface px-2 py-0.5 text-[10px] text-text shadow-md"
        >
          {speechBubble.preview}
        </span>
      )}

      <button
        type="button"
        onClick={onOpenPopover}
        className={cn(
          'relative flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition',
          isCurrentUser && isSupervisor && 'bg-supervisor/15 text-supervisor ring-2 ring-supervisor/30',
          isCurrentUser && !isSupervisor && 'bg-accent/15 text-accent ring-2 ring-accent/30',
          !isCurrentUser && isSupervisor && 'bg-supervisor/15 text-supervisor ring-2 ring-supervisor/40',
          !isCurrentUser && !isSupervisor && isAI && 'bg-secondary/30 text-text-muted ring-2 ring-accent/40 ring-dashed',
          !isCurrentUser && !isSupervisor && !isAI && 'bg-accent/15 text-accent',
        )}
        aria-label={`${displayName} - ${label}`}
        aria-haspopup="dialog"
        aria-expanded={isPopoverOpen}
      >
        <SeatIcon
          seatRole={seat.seat_role}
          isAI={isAI}
          isSupervisor={isSupervisor}
          size={12}
        />
        <span>{label}</span>

        {isAI && !isSupervisor && (
          <span
            className={cn(
              'absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-accent text-white',
              isThinking && 'animate-ai-thinking',
            )}
            aria-hidden="true"
          >
            <Bot size={8} />
          </span>
        )}

        <span
          className={cn(
            'absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full ring-2 ring-bg',
            status === 'online' && 'bg-success',
            status === 'typing' && 'bg-accent animate-pulse',
            status === 'thinking' && 'bg-accent animate-pulse',
            status === 'offline' && 'bg-border',
          )}
          aria-hidden="true"
        />
      </button>

      {isPopoverOpen && (
        <SeatPopover
          seat={seat}
          status={status}
          displayName={displayName}
          roleLabel={label}
          preview={preview}
          isCurrentUser={isCurrentUser}
          onClose={onClosePopover}
        />
      )}
    </div>
  )
}
