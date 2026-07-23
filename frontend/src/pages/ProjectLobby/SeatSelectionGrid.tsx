import { Bot, User, Crown, Lock, Hourglass } from 'lucide-react'
import { cn } from '../../lib/utils'
import { SeatIcon } from '../../lib/seatIcons'
import type { Seat } from '../../types/models'

interface SeatSelectionGridProps {
  seats: Seat[]
  currentUserId: string | undefined
  /** creator → 顯示「已就位」引導；observer / null → 唯讀旁觀文案。 */
  viewerRole: 'creator' | 'observer' | null
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
  const humanSeat = seats.find((s) => s.seat_role === 'human_creator')
  // AI 組員 = 既非 supervisor 也非真人席的 crew_*。
  const aiCrew = seats.filter(
    (s) => s.seat_role !== 'supervisor' && s.seat_role !== 'human_creator',
  )
  // 真人專屬席只有一個名額；已入座 = occupant_type==='human' 且有 user_id。
  const humanOccupied = !!(
    humanSeat && humanSeat.occupant_type === 'human' && humanSeat.user_id
  )
  const aiActiveCount = aiCrew.filter(
    (s) => s.occupant_type === 'ai' && !isDormant(s),
  ).length
  const aiPendingCount = aiCrew.filter(
    (s) => s.occupant_type === 'ai' && isDormant(s),
  ).length
  return {
    supervisorActive: supervisor ? !isDormant(supervisor) : false,
    humanCount: humanOccupied ? 1 : 0,
    humanCapacity: 1,
    aiActiveCount,
    aiPendingCount,
    totalSeats: seats.length,
  }
}

export function SeatSelectionGrid({
  seats,
  currentUserId,
  viewerRole,
}: SeatSelectionGridProps) {
  const supervisorSeat = seats.find((s) => s.seat_role === 'supervisor')
  const crewSeats = seats.filter((s) => s.seat_role !== 'supervisor')

  const summary = summarize(seats)
  const crewCount = summary.aiActiveCount + summary.aiPendingCount

  // v4.21：席位由系統固定編排，無需選擇；加入動作統一在右側「加入討論」卡。
  const subtitle =
    viewerRole === 'creator'
      ? `AI 組長與 ${crewCount} 位組員已就位，點右側「加入討論」即可開始。`
      : '以觀察者身份查看團隊席位佈局。'

  return (
    <div className="overflow-hidden rounded-2xl bg-surface shadow-md">
      {/* Header */}
      <div className="border-b border-border-light px-6 py-5">
        <h2 className="text-lg font-semibold text-text">你的設計團隊</h2>
        <p className="mt-0.5 text-sm text-text-muted">{subtitle}</p>
        <LobbyCounts summary={summary} />
      </div>

      {/* Supervisor section — locked: AI-only seat */}
      {supervisorSeat && <SupervisorRow seat={supervisorSeat} />}

      {/* Crew section */}
      <div className="divide-y divide-border-light">
        {crewSeats.map((seat) => (
          <CrewRow
            key={seat.seat_role}
            seat={seat}
            currentUserId={currentUserId}
          />
        ))}
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

function SupervisorRow({ seat }: { seat: Seat }) {
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
}: {
  seat: Seat
  currentUserId: string | undefined
}) {
  // 真人專屬席空置（occupant_type==='human' 但無 user_id）→ 保留給 creator 的列。
  const isVacantHuman = seat.occupant_type === 'human' && !seat.user_id
  const isMyCurrentSeat =
    seat.occupant_type === 'human' &&
    !!seat.user_id &&
    seat.user_id === currentUserId
  const isHumanOccupied =
    seat.occupant_type === 'human' && !!seat.user_id && !isMyCurrentSeat
  const isAI = seat.occupant_type === 'ai'
  const dormant = isAI && isDormant(seat)

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-5 py-3.5',
        isMyCurrentSeat && 'bg-primary/5',
        isHumanOccupied && 'bg-accent/5',
      )}
    >
      <SeatAvatar
        isAI={isAI}
        isMe={isMyCurrentSeat}
        isSupervisor={false}
        isDormant={dormant}
        isVacant={isVacantHuman}
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
            isVacant={isVacantHuman}
            displayName={seat.display_name}
          />
        </div>
      </div>
    </div>
  )
}

/* ── Shared Sub-components ── */

function SeatAvatar({
  isAI,
  isMe,
  isSupervisor,
  isDormant: dormant,
  isVacant,
  seatRole,
}: {
  isAI: boolean
  isMe: boolean
  isSupervisor: boolean
  isDormant?: boolean
  isVacant?: boolean
  seatRole?: string
}) {
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
        (isAI || isVacant) && 'border-2 border-dashed border-border text-text-muted',
        isAI && !dormant && 'animate-pulse-slow',
        ((isAI && dormant) || isVacant) && 'opacity-50',
        isMe && isSupervisor && 'border-2 border-supervisor bg-supervisor/10 text-supervisor',
        isMe && !isSupervisor && 'border-2 border-primary bg-primary/10 text-primary',
        !isAI && !isMe && !isVacant && 'border-2 border-accent bg-accent/10 text-accent',
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
      ) : isVacant ? (
        <Hourglass size={16} />
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
  isVacant,
  displayName,
}: {
  isAI: boolean
  isMe: boolean
  isOtherHuman: boolean
  isDormant?: boolean
  isVacant?: boolean
  displayName?: string
}) {
  // 空置的真人專屬席：保留給 creator（入座 CTA 在右側卡，這裡只標示狀態）。
  if (isVacant) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-bg-warm px-2 py-0.5 text-[11px] text-text-muted">
        <Hourglass size={10} />
        你的座位 · 保留中
      </span>
    )
  }
  if (isAI) {
    if (dormant) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-bg-warm px-2 py-0.5 text-[11px] text-text-muted">
          <Hourglass size={10} />
          待命中 · 等你上線
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
