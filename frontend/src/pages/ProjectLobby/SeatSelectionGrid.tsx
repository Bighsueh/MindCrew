import {
  Compass,
  Heart,
  LayoutGrid,
  Lightbulb,
  Target,
  Bot,
  User,
  LogIn,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../../components/common/Button'
import type { Seat, SeatRole } from '../../types/models'

interface SeatConfig {
  seatLabel: string
  expertName: string
  expertDesc: string
  icon: LucideIcon
}

const SEAT_CONFIG: Record<string, SeatConfig> = {
  supervisor: {
    seatLabel: '組員 1 席',
    expertName: '引導者',
    expertDesc: '引導討論方向、整理白板、管理進度',
    icon: Compass,
  },
  crew_1: {
    seatLabel: '組員 2 席',
    expertName: '同理心專家',
    expertDesc: '關注使用者感受、需求和痛點',
    icon: Heart,
  },
  crew_2: {
    seatLabel: '組員 3 席',
    expertName: '結構化專家',
    expertDesc: '整理框架、分類觀點、找出邏輯',
    icon: LayoutGrid,
  },
  crew_3: {
    seatLabel: '組員 4 席',
    expertName: '創意專家',
    expertDesc: '跳脫框架、提出新穎連結和角度',
    icon: Lightbulb,
  },
  crew_4: {
    seatLabel: '組員 5 席',
    expertName: '可行性專家',
    expertDesc: '評估落地現實、技術限制和資源',
    icon: Target,
  },
}

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
  return (
    <div className="rounded-xl border border-border bg-surface shadow-sm">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-base font-semibold text-text">選擇席位加入</h2>
        <p className="mt-0.5 text-xs text-text-muted">
          每個席位目前由 AI 專家代理，你可以取代任一位加入討論
        </p>
      </div>

      {joinError && (
        <div className="mx-5 mt-4 rounded-md bg-error-bg px-4 py-3 text-sm text-error">
          {joinError}
        </div>
      )}

      <div className="divide-y divide-border/50">
        {seats.map((seat) => (
          <SeatRow
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

interface SeatRowProps {
  seat: Seat
  currentUserId: string | undefined
  onJoin: (role: SeatRole) => void
  isJoining: boolean
}

function SeatRow({ seat, currentUserId, onJoin, isJoining }: SeatRowProps) {
  const config = SEAT_CONFIG[seat.seat_role]
  const Icon = config?.icon ?? Bot
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
      {/* Icon */}
      <div
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
          isMyCurrentSeat
            ? 'bg-primary/10 text-primary'
            : 'bg-accent/10 text-accent',
        )}
      >
        <Icon size={18} />
      </div>

      {/* Seat info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text">
            {config?.seatLabel ?? seat.seat_role}
          </span>
          <span className="text-xs text-text-muted">
            {isAI && `${config?.expertName ?? 'AI'}`}
            {isMyCurrentSeat && '你'}
            {isHumanOccupied && (seat.display_name ?? '其他成員')}
          </span>
        </div>
        <p className="text-xs text-text-muted/70">{config?.expertDesc}</p>
      </div>

      {/* Occupant badge */}
      <div className="flex shrink-0 items-center gap-1 text-xs text-text-muted">
        {isAI && (
          <>
            <Bot size={12} className="text-accent" />
            <span className="hidden sm:inline">AI 代理中</span>
          </>
        )}
        {isMyCurrentSeat && (
          <>
            <User size={12} className="text-primary" />
            <span className="font-medium text-primary">已加入</span>
          </>
        )}
        {isHumanOccupied && (
          <>
            <User size={12} className="text-accent" />
          </>
        )}
      </div>

      {/* Action */}
      {isAI && (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onJoin(seat.seat_role as SeatRole)}
          disabled={isJoining}
          className="shrink-0"
        >
          {isJoining ? (
            '加入中…'
          ) : (
            <span className="flex items-center gap-1.5">
              <LogIn size={14} />
              取代 AI
            </span>
          )}
        </Button>
      )}
    </div>
  )
}
