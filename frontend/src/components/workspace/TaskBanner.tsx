import { useCallback, useEffect, useState } from 'react'
import { ClipboardCheck } from 'lucide-react'
import { useHumanGateStore } from '../../stores/humanGateStore'
import type { UserTaskActionKind } from '../../types/ws'
import type { WSClientMessage } from '../../types/ws'

/**
 * Phase 42 A3（WP7，#24 / spec 05 Flow 12）：「你的任務」釘住 banner。
 *
 * 釘在聊天面板上方、非聊天流訊息——洗版不消失；由 `user_task` WS 事件驅動
 * （後到覆蓋、task_text=null 清除、換關清除，生命週期在 humanGateStore）。
 * `action_kind=confirm` 時提供按鈕（「可以」「我想改」），點擊走既有聊天發送
 * 路徑——後端 confirm 白名單（spec 20 §12.4）放行短確認、計入該關真人 gate。
 */

const ACTION_LABELS: Record<UserTaskActionKind, string> = {
  chat: '到聊天室說',
  note: '貼便條',
  move: '搬便條＋說明',
  confirm: '確認',
}

interface TaskBannerProps {
  sendWS: (msg: WSClientMessage) => void
  /** 只有專案的真人成員看得到 confirm 按鈕（旁觀者唯讀）。 */
  isHumanParticipant: boolean
}

export function TaskBanner({ sendWS, isHumanParticipant }: TaskBannerProps) {
  const task = useHumanGateStore((s) => s.task)
  const [sentSeq, setSentSeq] = useState<string | null>(null)

  // 任務更換時重置按鈕已送出狀態。
  useEffect(() => {
    setSentSeq(null)
  }, [task?.taskText, task?.subPhase])

  const sendConfirm = useCallback(
    (text: string) => {
      sendWS({ type: 'chat_message', payload: { content: text } })
      setSentSeq(text)
    },
    [sendWS],
  )

  if (!task) return null

  const confirmable = task.actionKind === 'confirm' && isHumanParticipant

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="task-banner"
      className="flex items-center gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2"
    >
      <ClipboardCheck size={18} className="shrink-0 text-amber-700" />
      <div className="min-w-0 flex-1">
        <span className="mr-2 rounded bg-amber-200/70 px-1.5 py-0.5 text-xs font-semibold text-amber-900">
          你的任務
        </span>
        <span className="text-sm text-amber-900">{task.taskText}</span>
        <span className="ml-2 text-xs text-amber-700/80">
          （{ACTION_LABELS[task.actionKind]}）
        </span>
      </div>
      {confirmable && (
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={sentSeq !== null}
            onClick={() => sendConfirm('可以')}
            className="rounded-lg bg-amber-600 px-3 py-1 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            可以
          </button>
          <button
            type="button"
            disabled={sentSeq !== null}
            onClick={() => sendConfirm('我想改')}
            className="rounded-lg border border-amber-600 px-3 py-1 text-sm font-medium text-amber-700 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            我想改
          </button>
        </div>
      )}
    </div>
  )
}
