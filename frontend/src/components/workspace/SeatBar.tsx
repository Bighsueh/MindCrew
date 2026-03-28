import { Bot, User } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'

const SEAT_ROLE_LABELS: Record<string, string> = {
  supervisor: '組長',
  crew_1: '組員 A',
  crew_2: '組員 B',
  crew_3: '組員 C',
  crew_4: '組員 D',
}

interface SeatBarProps {
  seats: Seat[]
  currentUserId?: string
}

export function SeatBar({ seats, currentUserId }: SeatBarProps) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      {seats.map((seat) => {
        const isAI = seat.occupant_type === 'ai'
        const isCurrentUser = seat.user_id === currentUserId
        const label = seat.display_name ?? (isAI ? `AI ${SEAT_ROLE_LABELS[seat.seat_role] ?? seat.seat_role}` : '人類')

        return (
          <div
            key={seat.seat_role}
            className={cn(
              'flex flex-shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
              isCurrentUser && seat.seat_role === 'supervisor' && 'bg-supervisor/15 text-supervisor ring-2 ring-supervisor/30',
              isCurrentUser && seat.seat_role !== 'supervisor' && 'bg-accent/15 text-accent ring-2 ring-accent/30',
              !isCurrentUser && seat.seat_role === 'supervisor' && 'bg-supervisor/15 text-supervisor',
              !isCurrentUser && seat.seat_role !== 'supervisor' && isAI && 'bg-secondary/30 text-text-muted',
              !isCurrentUser && seat.seat_role !== 'supervisor' && !isAI && 'bg-accent/15 text-accent',
            )}
          >
            {isAI ? <Bot size={12} /> : <User size={12} />}
            <span>{label}</span>
          </div>
        )
      })}
    </div>
  )
}
