import { useCallback, useMemo, useState } from 'react'
import type { Message, Seat } from '../../types/models'
import { useChatChannel } from '../../stores/chatStore'
import type { RecentSpeaker } from '../../components/workspace/SeatBar'

interface UseWorkspaceCoachStateOptions {
  seats: Seat[]
}

interface UseWorkspaceCoachStateResult {
  /** 來自 group channel 的 typing 名單，攤平給 SeatBar 顯示打字狀態。 */
  typingNames: string[]
  /** 最近發言者（含 seatId + preview + timestamp）；由 markRecentSpeaker 設定。 */
  recentSpeaker: RecentSpeaker | undefined
  /** 各座位最近一則訊息預覽，供 SeatPopover 顯示。 */
  seatPreviews: Record<string, string>
  /** Workspace WS handler 收到 chat_message 時呼叫；推導出 seatId 後更新 recentSpeaker。 */
  markRecentSpeaker: (message: Message) => void
}

/**
 * 整理 SeatBar 需要的衍生狀態：typingNames / recentSpeaker / seatPreviews。
 *
 * 為什麼不放在 chatStore？這些是「派生視圖」（derive view），會隨 seat 對應關係變化，
 * 屬於 Workspace 頁面層的編排責任，不該污染 chatStore。
 */
export function useWorkspaceCoachState({
  seats,
}: UseWorkspaceCoachStateOptions): UseWorkspaceCoachStateResult {
  const group = useChatChannel('group')

  const [recentSpeaker, setRecentSpeaker] = useState<RecentSpeaker | undefined>(undefined)

  // group typing users → 名字陣列；SeatBar 內以「名字」對齊 seat.display_name。
  const typingNames = useMemo(
    () => Object.values(group.typingUsers),
    [group.typingUsers],
  )

  // 從 group.messages 最近一條 per seat 推出 preview。
  const seatPreviews = useMemo<Record<string, string>>(() => {
    const previews: Record<string, string> = {}
    // 從尾往前掃；first-hit 即最新一則。
    for (let i = group.messages.length - 1; i >= 0; i -= 1) {
      const msg = group.messages[i]
      const seat = seats.find(
        (s) => s.user_id === msg.sender_id || s.agent_id === msg.sender_id,
      )
      if (seat && !(seat.id in previews)) {
        previews[seat.id] = msg.content.slice(0, 40)
      }
    }
    return previews
  }, [group.messages, seats])

  // 訊息抵達時：推導 seatId → 設定 recentSpeaker（觸發 speech-pop 動畫）。
  const markRecentSpeaker = useCallback(
    (message: Message) => {
      const seat = seats.find(
        (s) => s.user_id === message.sender_id || s.agent_id === message.sender_id,
      )
      if (!seat) return
      setRecentSpeaker({
        seatId: seat.id,
        preview: message.content.slice(0, 12),
        timestamp: Date.now(),
      })
    },
    [seats],
  )

  return { typingNames, recentSpeaker, seatPreviews, markRecentSpeaker }
}
