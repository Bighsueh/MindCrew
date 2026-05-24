/**
 * NoteAuthorOverlay — Shows a tiny dot on every note + author badge on hover.
 *
 * Default: 6px dot in top-left corner (AI=taupe, Human=terracotta)
 * Hover: Author name badge fades in above the note
 * Moving: Shows "正在移動..." badge instead of author (Feature C)
 *
 * Phase 24：新增 Activity Highlight overlay — 當 chat 或 note 觸發 activity，
 * 同作者 + 時間窗內的便利貼會疊一個 2px 邊框。hover/click 便利貼也會
 * 反向推 store，讓對應的聊天氣泡同步高亮。
 */
import { useEffect } from 'react'
import { useEditor } from '@tldraw/tldraw'
import { track, useValue } from '@tldraw/state-react'
import type { TLShape, TLShapeId } from '@tldraw/tldraw'
import { getColorScheme } from '../../colors/sticky'
import {
  computeNoteHighlightStyle,
  noteActivityKey,
  parseCreatedAt,
} from './activityHighlight'
import {
  selectActiveAnchor,
  useActivityHighlightStore,
} from '../../stores/activityHighlightStore'

export function parseAuthor(raw: unknown): { name: string; type: 'ai' | 'human' } {
  if (raw && typeof raw === 'object' && 'name' in raw) {
    const obj = raw as { name: unknown; type?: unknown }
    const name = typeof obj.name === 'string' && obj.name.length > 0 ? obj.name : '?'
    const type = obj.type === 'human' ? 'human' : 'ai'
    return { name, type }
  }
  if (typeof raw !== 'string') {
    return { name: '?', type: 'ai' }
  }
  const m = raw.match(/^(.+?)\((ai|human)\)$/)
  if (m) return { name: m[1], type: m[2] as 'ai' | 'human' }
  return { name: raw || '?', type: 'ai' }
}

export const NoteAuthorOverlay = track(function NoteAuthorOverlay() {
  const editor = useEditor()
  const hoveredId = useValue('hoveredShapeId', () => editor.getHoveredShapeId(), [editor])
  const selectedIds = useValue<TLShapeId[]>(
    'selectedShapeIds',
    () => editor.getSelectedShapeIds(),
    [editor],
  )

  const active = useActivityHighlightStore(selectActiveAnchor)
  const setHover = useActivityHighlightStore((s) => s.setHover)
  const clearHover = useActivityHighlightStore((s) => s.clearHover)
  const togglePinned = useActivityHighlightStore((s) => s.togglePinned)

  const shapes = editor.getCurrentPageShapes().filter(
    (s): s is TLShape => s.type === 'note' && !!(s.meta as Record<string, unknown>).author,
  )

  // Phase 24：hovered note → 推 hover anchor
  useEffect(() => {
    if (!hoveredId) {
      clearHover()
      return
    }
    const shape = shapes.find((s) => s.id === hoveredId)
    if (!shape) return
    const meta = shape.meta as Record<string, unknown>
    const key = noteActivityKey(meta.author)
    const anchorMs = parseCreatedAt(meta.created_at)
    setHover({ key, anchorMs, source: 'note' })
    // 不在 deps 放 shapes（每次 reactive tick 都會重算）；只看 id 變化
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredId])

  // Phase 24：selected note → 推 pinned anchor（只在 selection 變化時 toggle）
  useEffect(() => {
    if (!selectedIds || selectedIds.length === 0) return
    // 只處理單選 note；多選不切 pin（避免誤觸）
    if (selectedIds.length !== 1) return
    const sid = selectedIds[0]
    const shape = shapes.find((s) => s.id === sid)
    if (!shape || shape.type !== 'note') return
    const meta = shape.meta as Record<string, unknown>
    const key = noteActivityKey(meta.author)
    const anchorMs = parseCreatedAt(meta.created_at)
    togglePinned({ key, anchorMs, source: 'note' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds?.join(',')])

  if (shapes.length === 0) return null

  const zoom = editor.getZoomLevel()

  return (
    <>
      {/* Phase 24: activity highlight rings — render first so dots stack above */}
      {active &&
        shapes.map((shape) => {
          const meta = shape.meta as Record<string, unknown>
          const noteKey = noteActivityKey(meta.author)
          const noteCreatedAtMs = parseCreatedAt(meta.created_at)
          const noteColor = (shape.props as { color?: string } | undefined)?.color
          const scheme = getColorScheme(noteColor ?? null)
          const highlight = computeNoteHighlightStyle({
            noteKey,
            noteCreatedAtMs,
            active,
            accentColor: scheme.accent,
            zoom,
          })
          if (!highlight) return null
          const point = editor.pageToViewport({ x: shape.x, y: shape.y })
          return (
            <div
              key={`activity-${shape.id}`}
              className="pointer-events-none absolute z-10"
              style={{
                left: point.x - 3 * zoom,
                top: point.y - 3 * zoom,
                width: (200 + 6) * zoom,
                height: (150 + 6) * zoom,
                borderRadius: 6 * zoom,
                ...highlight,
              }}
            />
          )
        })}

      {/* Dots on every note */}
      {shapes.map((shape) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        const meta = shape.meta as Record<string, unknown>
        const { type } = parseAuthor(meta.author)
        const movingBy = typeof meta._moving_by === 'string' ? meta._moving_by : ''
        // Phase 22：dot 用便利貼自身的色，與聊天氣泡一致
        const noteColor = (shape.props as { color?: string } | undefined)?.color
        const scheme = getColorScheme(noteColor ?? null)
        const dotColor = noteColor
          ? scheme.accent
          : (type === 'ai' ? '#5A4D41' : '#8B4B2A')

        return (
          <div
            key={`dot-${shape.id}`}
            className="pointer-events-none absolute z-20"
            style={{
              left: point.x + 4 * zoom,
              top: point.y + 4 * zoom,
            }}
          >
            {/* Author identification dot — colored by note color */}
            <div
              className="rounded-full ring-1 ring-white/60"
              style={{
                width: Math.max(4, 6 * zoom),
                height: Math.max(4, 6 * zoom),
                backgroundColor: dotColor,
              }}
            />
            {/* Moving glow indicator (Feature C) */}
            {movingBy && (
              <div
                className="note-move-glow pointer-events-none absolute"
                style={{
                  left: -4 * zoom,
                  top: -4 * zoom,
                  width: 200 * zoom,
                  height: 150 * zoom,
                  border: '2px solid rgba(189,108,72,0.6)',
                  borderRadius: 4 * zoom,
                  boxShadow: '0 0 12px rgba(189,108,72,0.25)',
                }}
              />
            )}
          </div>
        )
      })}

      {/* Hover badge — only for the hovered shape */}
      {hoveredId && (() => {
        const shape = shapes.find((s) => s.id === hoveredId)
        if (!shape) return null

        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        const meta = shape.meta as Record<string, unknown>
        const movingBy = typeof meta._moving_by === 'string' ? meta._moving_by : ''

        if (movingBy) {
          // Show "moving by" badge instead of author
          return (
            <div
              key="move-badge"
              className="note-move-badge pointer-events-none absolute z-30"
              style={{
                left: point.x,
                top: point.y - 24 * zoom,
              }}
            >
              <span
                className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full px-1.5 py-0.5 font-medium leading-none shadow-sm"
                style={{
                  fontSize: `${Math.max(8, 10 * zoom)}px`,
                  backgroundColor: '#F2DED2',
                  color: '#BD6C48',
                }}
              >
                {movingBy} 正在移動...
              </span>
            </div>
          )
        }

        // Show author badge
        const { name, type } = parseAuthor(meta.author)
        return (
          <div
            key="author-badge"
            className="note-author-badge pointer-events-none absolute z-30"
            style={{
              left: point.x,
              top: point.y - 24 * zoom,
            }}
          >
            <span
              className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full px-1.5 py-0.5 font-medium leading-none shadow-sm"
              style={{
                fontSize: `${Math.max(8, 10 * zoom)}px`,
                backgroundColor: type === 'ai' ? 'rgba(156,142,124,0.15)' : 'rgba(189,108,72,0.15)',
                color: type === 'ai' ? '#8a7a6a' : '#bd6c48',
              }}
            >
              {type === 'ai' ? '🤖' : '👤'} {name}
            </span>
          </div>
        )
      })()}
    </>
  )
})
