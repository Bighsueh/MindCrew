import { create } from 'zustand'

/**
 * 白板統計（Phase 42 B1，spec 28 v2.0 §3.2）。
 *
 * 暖場「N／目標」計數的前端來源：CanvasPanel 訂閱 tldraw store 變化時，
 * 把 kind=content 的便條數寫進來（label 標題便條不計，與後端口徑一致）；
 * TimerInline 於暖場期間（timer snapshot 帶 warmup_goal）讀取顯示。
 * 桌機／手機雙 CanvasPanel 實例寫同值，無害。
 */
interface CanvasStatsState {
  /** 牆上 kind=content 便條數（含 AI 與真人；去重由後端建立時把關）。 */
  contentNoteCount: number
  setContentNoteCount: (count: number) => void
}

export const useCanvasStatsStore = create<CanvasStatsState>((set) => ({
  contentNoteCount: 0,
  setContentNoteCount: (count) =>
    set((state) =>
      state.contentNoteCount === count ? state : { contentNoteCount: count },
    ),
}))
