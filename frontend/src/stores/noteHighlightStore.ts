import { create } from 'zustand'

/**
 * Phase 42 A3（WP7，#34）：便條指認高亮狀態。
 *
 * `note_highlight` WS 事件（組長指認）與 `user_task.anchor_note_ids`（任務相關
 * 便條）共用——canvas 的 NoteHighlightOverlay 讀此 store 畫外框，到期自動清除。
 * id 以 `shape:` 前綴正規化（sidecar 產生的 note id 本身即 tldraw shape id）。
 */

interface NoteHighlightState {
  /** 正規化後的 tldraw shape id 集合。 */
  shapeIds: string[]
  /** 到期時間（ms epoch）；Overlay 據此自動退場。 */
  expiresAt: number | null
  highlight: (noteIds: string[], ttlSeconds: number) => void
  clear: () => void
}

export function normalizeShapeId(noteId: string): string {
  return noteId.startsWith('shape:') ? noteId : `shape:${noteId}`
}

export const useNoteHighlightStore = create<NoteHighlightState>((set) => ({
  shapeIds: [],
  expiresAt: null,
  highlight: (noteIds, ttlSeconds) =>
    set({
      shapeIds: noteIds.filter(Boolean).map(normalizeShapeId),
      expiresAt: Date.now() + Math.max(1, ttlSeconds) * 1000,
    }),
  clear: () => set({ shapeIds: [], expiresAt: null }),
}))
