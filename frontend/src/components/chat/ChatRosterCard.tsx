import { useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '../../lib/utils'
import { SeatIcon } from '../../lib/seatIcons'
import { useSeatStore } from '../../stores/seatStore'
import { SeatPersonaCard, type SeatStatus } from '../workspace/SeatPersonaCard'
import type { Seat } from '../../types/models'

const SEAT_ROLE_LABELS: Record<string, string> = {
  supervisor: '組長',
  crew_1: '組員 A',
  crew_2: '組員 B',
  crew_3: '組員 C',
  crew_4: '組員 D',
}

const EDITABLE_CREW_ROLES = new Set(['crew_1', 'crew_2', 'crew_3', 'crew_4'])

const ROLE_ORDER: Record<string, number> = {
  supervisor: 0,
  crew_1: 1,
  crew_2: 2,
  crew_3: 3,
  crew_4: 4,
}

// 滑鼠移開後，延遲多久才收合 / 關卡片。
const CLOSE_DELAY_MS = 320

function isOccupied(seat: Seat): boolean {
  return Boolean(seat.user_id || seat.agent_id || seat.display_name)
}

function deriveStatus(seat: Seat): SeatStatus {
  if (!isOccupied(seat)) return 'offline'
  if (seat.occupant_type === 'ai' && seat.is_active === false) return 'offline'
  return 'online'
}

function labelFor(seat: Seat): string {
  const roleLabel = SEAT_ROLE_LABELS[seat.seat_role] ?? seat.seat_role
  return (
    seat.display_name ??
    seat.persona?.name ??
    (seat.occupant_type === 'ai' ? `AI ${roleLabel}` : '人類')
  )
}

interface ChatRosterCardProps {
  projectId: string
  currentUserId?: string
  isCreator: boolean
  onPersonaSaved: (seat: Seat) => void
  /** 對齊聊天視窗寬度。 */
  width: number
  /** 右側讓位給常駐頻道泡泡，預設 12px。 */
  rightPx?: number
}

/**
 * ChatRosterCard — option C：與聊天分離的獨立浮卡，疊在聊天室上方。
 * 預設一條精簡臉堆；hover 整條 → 往左展開出名字（快展、延遲後慢收）。
 * hover 個別頭像 → 下方落出該隊友資料卡（離開後延遲關閉；編輯中不關）。
 */
export function ChatRosterCard({
  projectId,
  currentUserId,
  isCreator,
  onPersonaSaved,
  width,
  rightPx = 12,
}: ChatRosterCardProps) {
  const { seats } = useSeatStore()
  const [activeRole, setActiveRole] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)

  // 編輯中不可被延遲關閉計時器收掉 → 用 ref 讓計時器讀到最新值。
  const editingRef = useRef(editing)
  editingRef.current = editing
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancelClose = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }
  const scheduleClose = () => {
    cancelClose()
    closeTimer.current = setTimeout(() => {
      if (editingRef.current) return // 編輯中：保持開啟
      setExpanded(false)
      setActiveRole(null)
    }, CLOSE_DELAY_MS)
  }
  useEffect(() => cancelClose, [])

  const team = useMemo(
    () =>
      seats
        .filter(isOccupied)
        .slice()
        .sort((a, b) => (ROLE_ORDER[a.seat_role] ?? 9) - (ROLE_ORDER[b.seat_role] ?? 9)),
    [seats],
  )

  const selected = team.find((s) => s.seat_role === activeRole) ?? null

  const openRole = (role: string) => {
    cancelClose()
    setExpanded(true)
    setActiveRole((cur) => {
      if (cur !== role) setEditing(false) // 換人才清編輯態，避免誤丟正在編輯的內容
      return role
    })
  }
  const onPillEnter = () => {
    cancelClose()
    setExpanded(true)
  }
  const closeNow = () => {
    cancelClose()
    setExpanded(false)
    setActiveRole(null)
    setEditing(false)
  }

  return (
    <div
      className="pointer-events-none absolute top-3 z-40 flex flex-col items-end gap-2"
      style={{ width, right: rightPx }}
    >
      {/* 臉堆 pill：hover 整條 → 往左展開名字（快展、延遲慢收）。 */}
      <div
        className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 shadow-lg"
        onMouseEnter={onPillEnter}
        onMouseLeave={scheduleClose}
      >
        <span className="shrink-0 text-[11px] font-medium text-text-muted">隊友</span>
        <div className="flex items-center pl-1">
          {team.map((seat) => (
            <MemberItem
              key={seat.seat_role}
              seat={seat}
              label={labelFor(seat)}
              offline={deriveStatus(seat) === 'offline'}
              active={activeRole === seat.seat_role}
              expanded={expanded}
              onEnter={() => openRole(seat.seat_role)}
              onClick={() => openRole(seat.seat_role)}
            />
          ))}
        </div>
        <span
          className={cn(
            'overflow-hidden text-[11px] tabular-nums text-text-muted transition-all duration-200',
            expanded ? 'ml-0 max-w-0 opacity-0' : 'ml-0.5 max-w-[2rem] opacity-100',
          )}
        >
          {team.length}
        </span>
      </div>

      {/* 點/hover 後落出的資料卡（仍在這張獨立卡內，不進聊天面板）。 */}
      {selected && (
        <div
          className="pointer-events-auto max-h-[62vh] w-full overflow-auto rounded-xl border border-border bg-surface shadow-xl animate-popover-enter"
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <SeatPersonaCard
            key={selected.seat_role}
            seat={selected}
            status={deriveStatus(selected)}
            displayName={labelFor(selected)}
            roleLabel={SEAT_ROLE_LABELS[selected.seat_role] ?? selected.seat_role}
            isCurrentUser={selected.user_id === currentUserId}
            editing={editing}
            onEditingChange={setEditing}
            canEditPersona={
              isCreator &&
              selected.occupant_type === 'ai' &&
              EDITABLE_CREW_ROLES.has(selected.seat_role)
            }
            projectId={projectId}
            onPersonaSaved={onPersonaSaved}
            onClose={closeNow}
          />
        </div>
      )}
    </div>
  )
}

interface MemberItemProps {
  seat: Seat
  label: string
  offline: boolean
  active: boolean
  /** 整條 pill 是否展開（true：頭像散開＋名字展開）。 */
  expanded: boolean
  onEnter: () => void
  onClick: () => void
}

/**
 * MemberItem — 收合時只露重疊頭像；展開時頭像散開、名字從 0 寬長出。
 * 展開快（200ms）、收合慢（500ms）：靠 expanded 狀態切換 duration 做出不對稱過場。
 */
function MemberItem({ seat, label, offline, active, expanded, onEnter, onClick }: MemberItemProps) {
  const isAI = seat.occupant_type === 'ai'
  const isSupervisor = seat.seat_role === 'supervisor'
  return (
    <button
      type="button"
      onMouseEnter={onEnter}
      onClick={onClick}
      aria-label={label}
      className={cn(
        'flex items-center rounded-full transition-all first:ml-0',
        expanded ? 'ml-1 duration-200' : '-ml-1.5 duration-500',
        offline && 'opacity-50',
      )}
    >
      <span
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-2 ring-surface transition-[box-shadow]',
          isSupervisor && 'bg-supervisor/15 text-supervisor',
          !isSupervisor && isAI && 'bg-secondary/40 text-text-muted',
          !isSupervisor && !isAI && 'bg-accent/15 text-accent',
          active && 'ring-primary',
        )}
      >
        <SeatIcon seatRole={seat.seat_role} isAI={isAI} isSupervisor={isSupervisor} size={13} />
      </span>
      <span
        className={cn(
          'overflow-hidden whitespace-nowrap text-xs font-medium transition-all',
          expanded ? 'ml-1 max-w-[5rem] opacity-100 duration-200' : 'ml-0 max-w-0 opacity-0 duration-500',
          active ? 'text-primary' : 'text-text',
        )}
      >
        {label}
      </span>
    </button>
  )
}
