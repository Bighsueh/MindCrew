/**
 * OverflowHint — Phase 42 D1b（#33，spec 27 §5.5 / 05）。
 *
 * 當白板內容超出目前視野（便條被推到視窗外）時，於畫布底部中央顯示一個
 * 「還有內容在畫面外，縮小看全部」提示鈕，點擊 zoom-to-fit 把所有便條收進視野。
 * 作為 <Tldraw> 子層，用 `track()` 反應式比對「所有內容 bounds」vs「目前視野 bounds」。
 */
import { track } from '@tldraw/state-react'
import { useEditor } from '@tldraw/tldraw'

const MARGIN = 8 // page 單位容差，避免邊界抖動誤觸

export const OverflowHint = track(function OverflowHint() {
  const editor = useEditor()
  const content = editor.getCurrentPageBounds()
  if (!content) return null
  const viewport = editor.getViewportPageBounds()

  const overflow =
    content.minX < viewport.minX - MARGIN ||
    content.minY < viewport.minY - MARGIN ||
    content.maxX > viewport.maxX + MARGIN ||
    content.maxY > viewport.maxY + MARGIN
  if (!overflow) return null

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-4 z-30 flex justify-center">
      <button
        type="button"
        onClick={() => editor.zoomToFit({ animation: { duration: 300 } })}
        className="pointer-events-auto rounded-full border border-border bg-surface/95 px-3 py-1.5 text-xs font-medium text-text-muted shadow-md backdrop-blur transition-colors hover:text-text"
      >
        還有內容在畫面外 — 縮小看全部
      </button>
    </div>
  )
})
