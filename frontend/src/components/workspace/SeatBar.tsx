import { useEffect, useRef, useState } from 'react'
import type { Seat } from '../../types/models'
import { SeatChip } from './SeatChip'
import type { SeatStatus } from './SeatPopover'

// 重新匯出 SeatStatus 型別，方便 Workspace 等 caller 直接從 SeatBar 取得
export type { SeatStatus } from './SeatPopover'

const SEAT_ROLE_LABELS: Record<string, string> = {
  supervisor: '組長',
  crew_1: '組員 A',
  crew_2: '組員 B',
  crew_3: '組員 C',
  crew_4: '組員 D',
}

// 最近發言者資訊：父層在收到新訊息時更新 timestamp，會觸發 speech-pop 動畫
export interface RecentSpeaker {
  seatId: string
  preview: string
  timestamp: number
}

interface SeatBarProps {
  seats: Seat[]
  currentUserId?: string
  /** 所有頻道中正在輸入的名字（父層將 chatStore.typingUsers 攤平後傳入） */
  typingNames?: string[]
  /** 最近發言者——父層在新訊息抵達時設置，會觸發 speech-pop 動畫 */
  recentSpeaker?: RecentSpeaker
  /** 各座位的最新訊息預覽——顯示在 popover 中 */
  seatPreviews?: Record<string, string>
  /** 開啟與 AI 座位的私人聊天視窗 */
  onDirectMessage?: (seat: Seat) => void
  /** 開啟座位簡介（暫為 stub） */
  onProfileClick?: (seat: Seat) => void
}

function deriveStatus(seat: Seat, typingSet: Set<string>): SeatStatus {
  const occupied = Boolean(seat.user_id || seat.agent_id || seat.display_name)
  if (!occupied) return 'offline'
  const name = seat.display_name
  if (name && typingSet.has(name)) {
    return seat.occupant_type === 'ai' ? 'thinking' : 'typing'
  }
  return 'online'
}

export function SeatBar({
  seats,
  currentUserId,
  typingNames,
  recentSpeaker,
  seatPreviews,
  onDirectMessage,
  onProfileClick,
}: SeatBarProps) {
  const [openSeatId, setOpenSeatId] = useState<string | null>(null)
  const [bubbles, setBubbles] = useState<Map<string, { key: number; preview: string }>>(new Map())
  const lastSpeakerTsRef = useRef<number | null>(null)
  const bubbleKeyRef = useRef(0)

  useEffect(() => {
    if (!recentSpeaker) return
    if (lastSpeakerTsRef.current === recentSpeaker.timestamp) return
    lastSpeakerTsRef.current = recentSpeaker.timestamp
    bubbleKeyRef.current += 1
    const key = bubbleKeyRef.current
    const preview = recentSpeaker.preview.slice(0, 6) || '💬'
    setBubbles((prev) => {
      const next = new Map(prev)
      next.set(recentSpeaker.seatId, { key, preview })
      return next
    })
    const seatId = recentSpeaker.seatId
    const t = window.setTimeout(() => {
      setBubbles((prev) => {
        const cur = prev.get(seatId)
        if (!cur || cur.key !== key) return prev
        const next = new Map(prev)
        next.delete(seatId)
        return next
      })
    }, 720)
    return () => window.clearTimeout(t)
  }, [recentSpeaker?.timestamp, recentSpeaker?.seatId, recentSpeaker?.preview])

  const typingSet = new Set(typingNames ?? [])

  return (
    <div className="flex items-center gap-2 overflow-visible">
      {seats.map((seat) => {
        const isAI = seat.occupant_type === 'ai'
        const isCurrentUser = seat.user_id === currentUserId
        const roleLabel = SEAT_ROLE_LABELS[seat.seat_role] ?? seat.seat_role
        const label = seat.display_name ?? (isAI ? `AI ${roleLabel}` : '人類')
        const displayName = seat.display_name ?? label
        const status = deriveStatus(seat, typingSet)
        const bubble = bubbles.get(seat.id)
        const preview = seatPreviews?.[seat.id]

        return (
          <SeatChip
            key={seat.seat_role}
            seat={seat}
            isCurrentUser={isCurrentUser}
            label={label}
            displayName={displayName}
            status={status}
            speechBubble={bubble}
            preview={preview}
            isPopoverOpen={openSeatId === seat.id}
            onOpenPopover={() => setOpenSeatId(seat.id)}
            onClosePopover={() => setOpenSeatId((cur) => (cur === seat.id ? null : cur))}
            onDirectMessage={onDirectMessage}
            onProfileClick={onProfileClick}
          />
        )
      })}
    </div>
  )
}
