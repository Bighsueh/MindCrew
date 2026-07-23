import { useEffect, useState } from 'react'
import { Toast } from '../common/Toast'
import { useHumanGateStore } from '../../stores/humanGateStore'

/**
 * Phase 42 A3（WP5，#5 / spec 20 §12.5）：輸入退回提示 toast。
 *
 * `input_bounced` 事件 → 顯示退回原因＋「怎樣才算」教練式提示（內容層白話，
 * 不含機制名）。訊息本身照常顯示於聊天流——被退回的只是解鎖效力。
 * 同文案連續退回也要重新觸發（store 以 seq 區分）。
 */
export function InputBouncedToast() {
  const bounce = useHumanGateStore((s) => s.bounce)
  const clearBounce = useHumanGateStore((s) => s.clearBounce)
  const [visibleSeq, setVisibleSeq] = useState<number | null>(null)

  useEffect(() => {
    if (bounce) setVisibleSeq(bounce.seq)
  }, [bounce])

  if (!bounce || visibleSeq !== bounce.seq) return null

  return (
    <Toast
      key={bounce.seq}
      message={`${bounce.reasonZh} ${bounce.hintZh}`}
      variant="info"
      autoCloseMs={6000}
      onClose={() => {
        setVisibleSeq(null)
        clearBounce()
      }}
    />
  )
}
