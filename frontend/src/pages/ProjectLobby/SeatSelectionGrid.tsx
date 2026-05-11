import {
  Bot,
  User,
  LogIn,
  Crown,
  Lock,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../../components/common/Button'
import type { Seat, SeatRole } from '../../types/models'

interface SeatSelectionGridProps {
  seats: Seat[]
  currentUserId: string | undefined
  onJoin: (role: SeatRole) => void
  joiningRole: SeatRole | null
  joinError: string
}

export function SeatSelectionGrid({
  seats,
  currentUserId,
  onJoin,
  joiningRole,
  joinError,
}: SeatSelectionGridProps) {
  const supervisorSeat = seats.find((s) => s.seat_role === 'supervisor')
  const crewSeats = seats.filter((s) => s.seat_role !== 'supervisor')

  return (
    <div className="overflow-hidden rounded-2xl bg-surface shadow-md">
      {/* Header */}
      <div className="border-b border-border-light px-6 py-5">
        <h2 className="text-lg font-semibold text-text">選擇座位</h2>
        <p className="mt-0.5 text-sm text-text-muted">
          選擇一個座位加入討論，或以觀察者身份旁聽
        </p>
      </div>

      {joinError && (
        <div className="mx-6 mt-4 rounded-lg bg-error-bg px-4 py-3 text-sm text-error">
          {joinError}
        </div>
      )}

      {/* Supervisor section — locked: AI-only seat */}
      {supervisorSeat && <SupervisorRow seat={supervisorSeat} />}

      {/* Crew section */}
      <div className="divide-y divide-border-light">
        {crewSeats.map((seat) => (
          <CrewRow
            key={seat.seat_role}
            seat={seat}
            currentUserId={currentUserId}
            onJoin={onJoin}
            isJoining={joiningRole === seat.seat_role}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Supervisor Row ── */

interface SeatRowProps {
  seat: Seat
  currentUserId: string | undefined
  onJoin: (role: SeatRole) => void
  isJoining: boolean
}

interface SupervisorRowProps {
  seat: Seat
}

function SupervisorRow({ seat }: SupervisorRowProps) {
  const agentLabel = seat.display_name?.replace(/^AI\s*/, '') ?? 'AI'

  return (
    <div className="border-b border-border bg-supervisor/5 px-5 py-4">
      <div className="flex items-center gap-3">
        <SeatAvatar isAI isMe={false} isSupervisor />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Crown size={14} className="text-supervisor" />
            <span className="text-sm font-semibold text-text">組長</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-supervisor/15 px-2 py-0.5 text-[11px] font-medium text-supervisor">
              <Bot size={10} />
              {agentLabel} · 代理中
            </span>
          </div>
          <p className="mt-0.5 text-xs text-text-muted">
            引導討論方向、整理白板、管理進度
          </p>
        </div>

        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-secondary/40 px-2.5 py-1 text-xs font-medium text-text-muted">
          <Lock size={12} />
          AI 專屬席位
        </span>
      </div>
    </div>
  )
}

/* ── Crew Row ── */

function CrewRow({ seat, currentUserId, onJoin, isJoining }: SeatRowProps) {
  const isMyCurrentSeat =
    seat.occupant_type === 'human' && seat.user_id === currentUserId
  const isHumanOccupied =
    seat.occupant_type === 'human' && !isMyCurrentSeat
  const isAI = seat.occupant_type === 'ai'

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-5 py-3.5 transition-colors',
        isMyCurrentSeat && 'bg-primary/5',
        isAI && 'hover:bg-surface-hover',
        isHumanOccupied && 'bg-accent/5',
      )}
    >
      <SeatAvatar
        isAI={isAI}
        isMe={isMyCurrentSeat}
        isSupervisor={false}
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text">組員</span>
          <OccupantBadge
            isAI={isAI}
            isMe={isMyCurrentSeat}
            isOtherHuman={isHumanOccupied}
            displayName={seat.display_name}
          />
        </div>
      </div>

      <SeatAction
        isAI={isAI}
        isJoining={isJoining}
        seatRole={seat.seat_role as SeatRole}
        onJoin={onJoin}
      />
    </div>
  )
}

/* ── Shared Sub-components ── */

function SeatAvatar({
  isAI,
  isMe,
  isSupervisor,
}: {
  isAI: boolean
  isMe: boolean
  isSupervisor: boolean
}) {
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
        isAI && 'border-2 border-dashed border-border text-text-muted',
        isAI && 'animate-pulse-slow',
        isMe && isSupervisor && 'border-2 border-supervisor bg-supervisor/10 text-supervisor',
        isMe && !isSupervisor && 'border-2 border-primary bg-primary/10 text-primary',
        !isAI && !isMe && 'border-2 border-accent bg-accent/10 text-accent',
      )}
    >
      {isAI ? (
        <Bot size={16} />
      ) : (
        isMe ? <User size={16} /> : <User size={16} />
      )}
    </div>
  )
}

function OccupantBadge({
  isAI,
  isMe,
  isOtherHuman,
  displayName,
}: {
  isAI: boolean
  isMe: boolean
  isOtherHuman: boolean
  displayName?: string
}) {
  if (isAI) {
    const agentLabel = displayName?.replace(/^AI\s*/, '') ?? 'AI'
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-secondary/40 px-2 py-0.5 text-[11px] text-text-muted">
        <Bot size={10} />
        {agentLabel} · 代理中
      </span>
    )
  }

  if (isMe) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
        <User size={10} />
        你
      </span>
    )
  }

  if (isOtherHuman) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
        <User size={10} />
        {displayName ?? '其他成員'}
      </span>
    )
  }

  return null
}

function SeatAction({
  isAI,
  isJoining,
  seatRole,
  onJoin,
}: {
  isAI: boolean
  isJoining: boolean
  seatRole: SeatRole
  onJoin: (role: SeatRole) => void
}) {
  if (!isAI) return null

  return (
    <Button
      size="sm"
      variant="primary"
      onClick={() => onJoin(seatRole)}
      disabled={isJoining}
      className="shrink-0"
    >
      {isJoining ? (
        '加入中…'
      ) : (
        <span className="flex items-center gap-1.5">
          <LogIn size={14} />
          入座
        </span>
      )}
    </Button>
  )
}
