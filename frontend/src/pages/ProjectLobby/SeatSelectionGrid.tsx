import {
  Bot,
  User,
  LogIn,
  Crown,
  Lock,
  Hourglass,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../../components/common/Button'
import { SeatIcon } from '../../lib/seatIcons'
import type { Seat, SeatRole } from '../../types/models'

interface SeatSelectionGridProps {
  seats: Seat[]
  currentUserId: string | undefined
  onJoin: (role: SeatRole) => void
  joiningRole: SeatRole | null
  joinError: string
  isLocked: boolean
  hideJoinButtons?: boolean
  hideObserverHint?: boolean
}

// Phase 21：dormant 表示「AI 還沒被啟動」——第一位真人入座前的 lobby 狀態。
function isDormant(seat: Seat): boolean {
  // 後端帶來 is_active=false 是權威來源；舊資料以 state==='dormant' 兜底。
  return seat.is_active === false || seat.state === 'dormant'
}

interface LobbySummary {
  supervisorActive: boolean
  humanCount: number
  humanCapacity: number
  aiActiveCount: number
  aiPendingCount: number
  totalSeats: number
}

function summarize(seats: Seat[]): LobbySummary {
  const supervisor = seats.find((s) => s.seat_role === 'supervisor')
  const crew = seats.filter((s) => s.seat_role !== 'supervisor')
  const humanCount = crew.filter((s) => s.occupant_type === 'human').length
  const aiActiveCount = crew.filter(
    (s) => s.occupant_type === 'ai' && !isDormant(s),
  ).length
  const aiPendingCount = crew.filter(
    (s) => s.occupant_type === 'ai' && isDormant(s),
  ).length
  return {
    supervisorActive: supervisor ? !isDormant(supervisor) : false,
    humanCount,
    humanCapacity: crew.length,
    aiActiveCount,
    aiPendingCount,
    totalSeats: seats.length,
  }
}

export function SeatSelectionGrid({
  seats,
  currentUserId,
  onJoin,
  joiningRole,
  joinError,
  isLocked,
  hideJoinButtons = false,
  hideObserverHint = false,
}: SeatSelectionGridProps) {
  const supervisorSeat = seats.find((s) => s.seat_role === 'supervisor')
  const crewSeats = seats.filter((s) => s.seat_role !== 'supervisor')

  // Phase 21：一個人類一個專案只能佔一席。若使用者已在任一席位 → 鎖掉所有「入座」鈕。
  const userHasSeat = seats.some(
    (s) => s.occupant_type === 'human' && s.user_id === currentUserId,
  )

  const summary = summarize(seats)

  return (
    <div className="overflow-hidden rounded-2xl bg-surface shadow-md">
      {/* Header */}
      <div className="border-b border-border-light px-6 py-5">
        <h2 className="text-lg font-semibold text-text">選擇座位</h2>
        <p className="mt-0.5 text-sm text-text-muted">
          {hideObserverHint
            ? '系統會自動為你安排席位'
            : '查看席位佈局，或以觀察者身份進入工作區'}
        </p>
        <LobbyCounts summary={summary} />
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
        {crewSeats.map((seat) => {
          const isJoining = joiningRole === seat.seat_role
          let disabledReason: string | undefined
          if (userHasSeat) {
            disabledReason = '你已經在這個學習活動中佔有一個席位'
          } else if (isLocked && !isJoining) {
            disabledReason = '正在加入其他席位…'
          }
          return (
            <CrewRow
              key={seat.seat_role}
              seat={seat}
              currentUserId={currentUserId}
              onJoin={onJoin}
              isJoining={isJoining}
              disabledReason={disabledReason}
              hideJoinButton={hideJoinButtons || userHasSeat}
            />
          )
        })}
      </div>
    </div>
  )
}

/* ── Lobby counts (Phase 21) ── */

function LobbyCounts({ summary }: { summary: LobbySummary }) {
  const {
    supervisorActive,
    humanCount,
    humanCapacity,
    aiActiveCount,
    aiPendingCount,
    totalSeats,
  } = summary
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
      <span className="inline-flex items-center gap-1">
        <Crown size={12} className="text-supervisor" />
        組長：{supervisorActive ? '已上線' : '待人類入座後上線'}
      </span>
      <span className="inline-flex items-center gap-1">
        <User size={12} className="text-primary" />
        人類：{humanCount}/{humanCapacity}
      </span>
      <span className="inline-flex items-center gap-1">
        <Bot size={12} className="text-text-muted" />
        AI 組員：{aiActiveCount} 已上線
        {aiPendingCount > 0 && `、${aiPendingCount} 待加入`}
      </span>
      <span className="ml-auto rounded-full bg-bg-warm px-2 py-0.5 text-[11px] font-medium text-text">
        共 {totalSeats} 個席位
      </span>
    </div>
  )
}

/* ── Supervisor Row ── */

interface SeatRowProps {
  seat: Seat
  currentUserId: string | undefined
  onJoin: (role: SeatRole) => void
  isJoining: boolean
  disabledReason?: string
}

interface SupervisorRowProps {
  seat: Seat
}

function SupervisorRow({ seat }: SupervisorRowProps) {
  const dormant = isDormant(seat)
  const agentLabel = seat.display_name?.replace(/^AI\s*/, '') ?? 'AI'

  return (
    <div className="border-b border-border bg-supervisor/5 px-5 py-4">
      <div className="flex items-center gap-3">
        <SeatAvatar isAI isMe={false} isSupervisor isDormant={dormant} seatRole={seat.seat_role} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Crown size={14} className="text-supervisor" />
            <span className="text-sm font-semibold text-text">組長</span>
            {dormant ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-bg-warm px-2 py-0.5 text-[11px] font-medium text-text-muted">
                <Hourglass size={10} />
                待人類入座後上線
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-supervisor/15 px-2 py-0.5 text-[11px] font-medium text-supervisor">
                <Bot size={10} />
                AI · {agentLabel} · 代理中
              </span>
            )}
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

function CrewRow({
  seat,
  currentUserId,
  onJoin,
  isJoining,
  disabledReason,
  hideJoinButton,
}: SeatRowProps & { hideJoinButton?: boolean }) {
  const isMyCurrentSeat =
    seat.occupant_type === 'human' && seat.user_id === currentUserId
  const isHumanOccupied =
    seat.occupant_type === 'human' && !isMyCurrentSeat
  const isAI = seat.occupant_type === 'ai'
  const dormant = isAI && isDormant(seat)

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-5 py-3.5 transition-colors',
        isMyCurrentSeat && 'bg-primary/5',
        isAI && !disabledReason && 'hover:bg-surface-hover',
        isHumanOccupied && 'bg-accent/5',
      )}
    >
      <SeatAvatar
        isAI={isAI}
        isMe={isMyCurrentSeat}
        isSupervisor={false}
        isDormant={dormant}
        seatRole={seat.seat_role}
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text">組員</span>
          <OccupantBadge
            isAI={isAI}
            isMe={isMyCurrentSeat}
            isOtherHuman={isHumanOccupied}
            isDormant={dormant}
            displayName={seat.display_name}
          />
        </div>
      </div>

      {!hideJoinButton && (
        <SeatAction
          isAI={isAI}
          isJoining={isJoining}
          seatRole={seat.seat_role as SeatRole}
          onJoin={onJoin}
          disabledReason={disabledReason}
        />
      )}
    </div>
  )
}

/* ── Shared Sub-components ── */

function SeatAvatar({
  isAI,
  isMe,
  isSupervisor,
  isDormant: dormant,
  seatRole,
}: {
  isAI: boolean
  isMe: boolean
  isSupervisor: boolean
  isDormant?: boolean
  seatRole?: string
}) {
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
        isAI && 'border-2 border-dashed border-border text-text-muted',
        isAI && !dormant && 'animate-pulse-slow',
        isAI && dormant && 'opacity-50',
        isMe && isSupervisor && 'border-2 border-supervisor bg-supervisor/10 text-supervisor',
        isMe && !isSupervisor && 'border-2 border-primary bg-primary/10 text-primary',
        !isAI && !isMe && 'border-2 border-accent bg-accent/10 text-accent',
      )}
    >
      {isAI ? (
        dormant ? (
          <Hourglass size={16} />
        ) : (
          <SeatIcon
            seatRole={seatRole ?? 'crew_1'}
            isAI
            isSupervisor={isSupervisor}
            size={16}
          />
        )
      ) : (
        <User size={16} />
      )}
    </div>
  )
}

function OccupantBadge({
  isAI,
  isMe,
  isOtherHuman,
  isDormant: dormant,
  displayName,
}: {
  isAI: boolean
  isMe: boolean
  isOtherHuman: boolean
  isDormant?: boolean
  displayName?: string
}) {
  if (isAI) {
    if (dormant) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-bg-warm px-2 py-0.5 text-[11px] text-text-muted">
          <Hourglass size={10} />
          保留給人類 · 請就座
        </span>
      )
    }
    const agentLabel = displayName?.replace(/^AI\s*/, '') ?? 'AI'
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-secondary/40 px-2 py-0.5 text-[11px] text-text-muted">
        <Bot size={10} />
        AI · {agentLabel} · 代理中
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
  disabledReason,
}: {
  isAI: boolean
  isJoining: boolean
  seatRole: SeatRole
  onJoin: (role: SeatRole) => void
  disabledReason?: string
}) {
  if (!isAI) return null

  return (
    <Button
      size="sm"
      variant="primary"
      onClick={() => onJoin(seatRole)}
      disabled={isJoining || Boolean(disabledReason)}
      title={disabledReason}
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
