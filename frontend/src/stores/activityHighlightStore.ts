/**
 * Phase 24 — 對話活動高亮 store。
 *
 * - hover：暫態，hover 進入/離開時 set/clear
 * - pinned：click 觸發的持久態；同對象再 click 或 clearAll → 清除
 * - 同時間 active = pinned ?? hover
 */

import { create } from 'zustand'
import type { ActivityAnchor } from '../components/canvas/activityHighlight'

interface ActivityHighlightState {
  hover: ActivityAnchor | null
  pinned: ActivityAnchor | null
  setHover: (anchor: ActivityAnchor | null) => void
  clearHover: () => void
  togglePinned: (anchor: ActivityAnchor) => void
  clearPinned: () => void
  clearAll: () => void
}

function sameAnchor(a: ActivityAnchor | null, b: ActivityAnchor | null): boolean {
  if (!a || !b) return false
  return a.key === b.key && a.anchorMs === b.anchorMs && a.source === b.source
}

export const useActivityHighlightStore = create<ActivityHighlightState>((set) => ({
  hover: null,
  pinned: null,
  setHover: (anchor) =>
    set((s) => (sameAnchor(s.hover, anchor) ? s : { ...s, hover: anchor })),
  clearHover: () => set((s) => (s.hover === null ? s : { ...s, hover: null })),
  togglePinned: (anchor) =>
    set((s) => (sameAnchor(s.pinned, anchor) ? { ...s, pinned: null } : { ...s, pinned: anchor })),
  clearPinned: () => set((s) => (s.pinned === null ? s : { ...s, pinned: null })),
  clearAll: () =>
    set((s) => (s.hover === null && s.pinned === null ? s : { ...s, hover: null, pinned: null })),
}))

/** 取目前生效的 anchor：pinned 優先於 hover。 */
export function selectActiveAnchor(s: ActivityHighlightState): ActivityAnchor | null {
  return s.pinned ?? s.hover
}
