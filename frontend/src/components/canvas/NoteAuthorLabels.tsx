import { useEditor } from '@tldraw/tldraw'
import { track } from '@tldraw/state-react'
import type { TLShape } from '@tldraw/tldraw'

function parseAuthor(raw: string): { name: string; type: 'ai' | 'human' } {
  const m = raw.match(/^(.+?)\((ai|human)\)$/)
  if (m) return { name: m[1], type: m[2] as 'ai' | 'human' }
  return { name: raw || '?', type: 'ai' }
}

export const NoteAuthorLabels = track(function NoteAuthorLabels() {
  const editor = useEditor()
  const shapes = editor.getCurrentPageShapes().filter(
    (s): s is TLShape => s.type === 'note' && !!(s.meta as Record<string, string>).author,
  )

  if (shapes.length === 0) return null

  return (
    <>
      {shapes.map((shape) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        const zoom = editor.getZoomLevel()
        const { name, type } = parseAuthor((shape.meta as Record<string, string>).author)

        return (
          <div
            key={shape.id}
            className="pointer-events-none absolute z-20"
            style={{
              left: point.x,
              top: point.y - 18 * zoom,
            }}
          >
            <span
              className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none shadow-sm"
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
      })}
    </>
  )
})
