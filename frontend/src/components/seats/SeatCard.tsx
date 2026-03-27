import type { Seat, SeatRole } from '../../types/models'
import { Button } from '../common/Button'

interface SeatCardProps {
  seat: Seat
  currentUserSeatRole?: SeatRole | null
  onJoin?: (seatRole: SeatRole) => void
  isJoining?: boolean
}

const ROLE_LABELS: Record<SeatRole, string> = {
  supervisor: '指導者',
  crew_1: '成員 1',
  crew_2: '成員 2',
  crew_3: '成員 3',
  crew_4: '成員 4',
}

const ROLE_COLORS: Record<SeatRole, string> = {
  supervisor: 'bg-purple-100 border-purple-300 text-purple-800',
  crew_1: 'bg-blue-100 border-blue-300 text-blue-800',
  crew_2: 'bg-green-100 border-green-300 text-green-800',
  crew_3: 'bg-yellow-100 border-yellow-300 text-yellow-800',
  crew_4: 'bg-orange-100 border-orange-300 text-orange-800',
}

export function SeatCard({ seat, currentUserSeatRole, onJoin, isJoining }: SeatCardProps) {
  const isOccupiedByHuman = seat.occupant_type === 'human'
  const isMyCurrentSeat = currentUserSeatRole === seat.seat_role
  const canJoin = !isOccupiedByHuman && !isMyCurrentSeat && onJoin

  return (
    <div
      className={[
        'flex flex-col gap-3 rounded-xl border-2 p-4 transition-all duration-200',
        ROLE_COLORS[seat.seat_role],
        isMyCurrentSeat ? 'ring-2 ring-blue-500 ring-offset-2' : '',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{ROLE_LABELS[seat.seat_role]}</span>
        {isMyCurrentSeat && (
          <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs text-white">
            你的席位
          </span>
        )}
      </div>

      {/* Occupant info */}
      <div className="flex items-center gap-2">
        <span className="text-2xl">{isOccupiedByHuman ? '👤' : '🤖'}</span>
        <div>
          <p className="text-sm font-medium">
            {isOccupiedByHuman ? (seat.display_name ?? '人類成員') : `AI ${ROLE_LABELS[seat.seat_role]}`}
          </p>
          <p className="text-xs opacity-70">
            {isOccupiedByHuman ? '人類' : 'AI Agent'}
          </p>
        </div>
      </div>

      {/* Action */}
      {canJoin && (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onJoin(seat.seat_role)}
          isLoading={isJoining}
          className="w-full"
        >
          加入此席位
        </Button>
      )}
      {isOccupiedByHuman && !isMyCurrentSeat && (
        <p className="text-center text-xs opacity-60">已由人類佔用</p>
      )}
    </div>
  )
}
