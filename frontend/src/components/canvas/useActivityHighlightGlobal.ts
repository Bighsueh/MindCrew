/**
 * Phase 24 — workspace 全域 click-outside / Esc 清除 activity pin。
 *
 * 點到非 chat row / 非 tldraw shape 區域 → clearAll；按 Esc → 同樣清除。
 * Hover 行為仍由各元件 onMouseEnter/Leave 維護。
 */
import { useEffect } from 'react'
import { useActivityHighlightStore } from '../../stores/activityHighlightStore'

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  // ChatMessage 標了 data-activity-highlight="chat"
  if (target.closest('[data-activity-highlight="chat"]')) return true
  // tldraw shape 點擊（含內部子元素）
  if (target.closest('.tl-shape, .tl-container')) return true
  return false
}

export function useActivityHighlightGlobal(): void {
  const clearAll = useActivityHighlightStore((s) => s.clearAll)

  useEffect(() => {
    const handleMouseDown = (e: MouseEvent): void => {
      if (!isInteractiveTarget(e.target)) {
        clearAll()
      }
    }
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        clearAll()
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [clearAll])
}
