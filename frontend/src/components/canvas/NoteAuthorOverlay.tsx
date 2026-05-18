/**
 * NoteAuthorOverlay — Shows a tiny dot on every note + author badge on hover.
 *
 * Default: 6px dot in top-left corner (AI=taupe, Human=terracotta)
 * Hover: Author name badge fades in above the note
 * Moving: Shows "正在移動..." badge instead of author (Feature C)
 */
import { useEditor } from '@tldraw/tldraw'
import { track, useValue } from '@tldraw/state-react'
import type { TLShape } from '@tldraw/tldraw'

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

  const shapes = editor.getCurrentPageShapes().filter(
    (s): s is TLShape => s.type === 'note' && !!(s.meta as Record<string, unknown>).author,
  )

  if (shapes.length === 0) return null

  const zoom = editor.getZoomLevel()

  return (
    <>
      {/* Dots on every note */}
      {shapes.map((shape) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        const meta = shape.meta as Record<string, unknown>
        const { type } = parseAuthor(meta.author)
        const movingBy = typeof meta._moving_by === 'string' ? meta._moving_by : ''

        return (
          <div
            key={`dot-${shape.id}`}
            className="pointer-events-none absolute z-20"
            style={{
              left: point.x + 4 * zoom,
              top: point.y + 4 * zoom,
            }}
          >
            {/* Author type dot */}
            <div
              className="rounded-full"
              style={{
                width: Math.max(4, 6 * zoom),
                height: Math.max(4, 6 * zoom),
                backgroundColor: type === 'ai' ? '#5A4D41' : '#8B4B2A',
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
