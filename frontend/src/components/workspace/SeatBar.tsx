import { Bot, User } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'

const SEAT_ROLE_LABELS: Record<string, string> = {
  supervisor: 'Supervisor',
  crew_1: 'Crew 1',
  crew_2: 'Crew 2',
  crew_3: 'Crew 3',
  crew_4: 'Crew 4',
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
            key={seat.id}
            className={cn(
              'flex flex-shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
              isAI && 'bg-secondary/30 text-text-muted',
              !isAI && !isCurrentUser && 'bg-accent/15 text-accent',
              isCurrentUser && 'bg-primary/10 text-primary ring-2 ring-primary/30',
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
