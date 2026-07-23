/**
 * NoteHighlightOverlay — Phase 42 A3（WP7，#34 / spec 05 §10.1）。
 *
 * 組長指認便條（`note_highlight` 事件）或任務相關便條（`user_task.anchor_note_ids`）
 * 時，對目標便條畫高亮外框；ttl 到期自動退場。取代「用顏色指認」——便條色＝
 * 作者身分色，語意不得用顏色表達。對不上的 shape id 直接忽略（LLM 幻覺 id 防護）。
 */
import { useEffect } from 'react'
import { useEditor } from '@tldraw/tldraw'
import { track } from '@tldraw/state-react'
import { useNoteHighlightStore } from '../../stores/noteHighlightStore'

// 便條基準尺寸（與 NoteAuthorOverlay 同口徑）。
const NOTE_W = 200
const NOTE_H = 150

export const NoteHighlightOverlay = track(function NoteHighlightOverlay() {
  const editor = useEditor()
  const shapeIds = useNoteHighlightStore((s) => s.shapeIds)
  const expiresAt = useNoteHighlightStore((s) => s.expiresAt)
  const clear = useNoteHighlightStore((s) => s.clear)

  // ttl 到期自動清除。
  useEffect(() => {
    if (!expiresAt) return
    const remain = expiresAt - Date.now()
    if (remain <= 0) {
      clear()
      return
    }
    const timer = window.setTimeout(clear, remain)
    return () => window.clearTimeout(timer)
  }, [expiresAt, clear])

  if (shapeIds.length === 0) return null

  const targets = new Set(shapeIds)
  const shapes = editor
    .getCurrentPageShapes()
    .filter((s) => s.type === 'note' && targets.has(s.id))
  if (shapes.length === 0) return null

  const zoom = editor.getZoomLevel()

  return (
    <>
      {shapes.map((shape) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        return (
          <div
            key={`hl-${shape.id}`}
            data-testid="note-highlight"
            className="pointer-events-none absolute z-20 animate-pulse"
            style={{
              left: point.x - 5 * zoom,
              top: point.y - 5 * zoom,
              width: (NOTE_W + 10) * zoom,
              height: (NOTE_H + 10) * zoom,
              border: `${Math.max(2, 3 * zoom)}px solid rgba(217,119,6,0.85)`,
              borderRadius: 8 * zoom,
              boxShadow: '0 0 16px rgba(217,119,6,0.35)',
            }}
          />
        )
      })}
    </>
  )
})
