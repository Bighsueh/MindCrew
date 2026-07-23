import { AlertTriangle, Hourglass, PauseCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'
import type { RoomPauseReason } from '../../types/ws'

/**
 * 全房暫停 banner——由 `room_paused` / `room_resumed` WS 事件驅動
 * （state 在 `projectStore.roomPauseReason`）。唯讀狀態列、無操作按鈕。
 *
 *  - "llm_down"（紅，Phase 42 D5 / spec 20 §13.3）：AI 服務中斷自動暫停，恢復後自動續跑。
 *  - "teacher"（琥珀）：老師手動暫停。
 *  - "awaiting_human"（藍，Phase 43 / spec 20 §3/§11.7）：你離席或被點名未回應的全房
 *    休眠——回個訊息或重新開啟工作區，就會從原處（同 sub_phase、同計時位置）繼續。
 */
interface BannerStyle {
  className: string
  icon: LucideIcon
  text: string
}

const BANNER_CONFIG: Record<RoomPauseReason, BannerStyle> = {
  llm_down: {
    className: 'border-error/30 bg-error-bg text-error',
    icon: AlertTriangle,
    text: 'AI 服務暫時異常，活動暫停中——恢復後會自動繼續，請稍候。',
  },
  teacher: {
    className: 'border-amber-200 bg-amber-50 text-amber-800',
    icon: PauseCircle,
    text: '活動已由老師暫停。',
  },
  awaiting_human: {
    className: 'border-blue-200 bg-blue-50 text-blue-800',
    icon: Hourglass,
    text: '活動已暫停，等你回來——回個訊息或重新開啟工作區，我們就從這裡繼續。',
  },
}

export function RoomPausedBanner() {
  const reason = useProjectStore((s) => s.roomPauseReason)
  if (!reason) return null

  const { className, icon: Icon, text } = BANNER_CONFIG[reason]

  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="room-paused-banner"
      className={`flex items-center justify-center gap-2 border-b px-4 py-2 text-sm font-medium ${className}`}
    >
      <Icon size={16} className="shrink-0" />
      <span>{text}</span>
    </div>
  )
}
