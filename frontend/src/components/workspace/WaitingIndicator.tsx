import { Hourglass } from 'lucide-react'
import { useHumanGateStore } from '../../stores/humanGateStore'
import type { WaitingState } from '../../stores/humanGateStore'

/**
 * Phase 42 A3（WP5 / spec 05 Flow 4）：「等待真人輸入中…」狀態列。
 *
 * 回合鎖凍結（`waiting_for_human`）時顯示——顯式狀態、不靠聊天流暗示；
 * 解鎖／推進後端發 `turn_state` → store 清除。required 旗標＋mode 組合語意
 * （all=都要、any=擇一）由後端計算下發，前端只渲染文案（spec 20 §5.6）。
 */

function requiredText(w: WaitingState): string {
  const labels: string[] = []
  if (w.required.note) labels.push('貼一張便條')
  if (w.required.chat) labels.push('到聊天說想法')
  if (w.required.move) labels.push('把便條搬到位')
  if (w.required.confirm) labels.push('做個確認')
  if (labels.length === 0) return '回應一下'
  if (labels.length === 1) return labels[0]
  return w.required.mode === 'all' ? labels.join('，也要') : labels.join('，或')
}

export function WaitingIndicator() {
  const waiting = useHumanGateStore((s) => s.waiting)
  if (!waiting) return null

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="waiting-indicator"
      className="flex items-center gap-2 border-b border-sky-200 bg-sky-50 px-4 py-1.5"
    >
      <Hourglass size={14} className="shrink-0 animate-pulse text-sky-700" />
      <span className="text-sm text-sky-900">
        等待真人輸入中——{requiredText(waiting)}
      </span>
    </div>
  )
}
