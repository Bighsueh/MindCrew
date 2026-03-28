import { useEditor } from '@tldraw/tldraw'
import { useValue } from '@tldraw/state-react'
import { ZoomIn, ZoomOut, Maximize } from 'lucide-react'
import { cn } from '../../lib/utils'

const btnClass = cn(
  'flex items-center justify-center rounded-md p-1.5 text-text-muted',
  'hover:bg-surface-hover hover:text-text transition-colors cursor-pointer',
)

export function ZoomControls() {
  const editor = useEditor()
  const zoom = useValue('zoom', () => Math.round(editor.getZoomLevel() * 100), [editor])

  return (
    <div className="absolute bottom-4 left-4 z-40 flex items-center gap-0.5 rounded-lg border border-border bg-surface/95 px-1.5 py-1 shadow-md backdrop-blur-sm">
      <button onClick={() => editor.zoomOut(editor.getViewportScreenCenter(), { animation: { duration: 200 } })} title="縮小" className={btnClass}>
        <ZoomOut size={15} />
      </button>
      <span className="min-w-[3rem] text-center text-xs font-medium tabular-nums text-text-muted">
        {zoom}%
      </span>
      <button onClick={() => editor.zoomIn(editor.getViewportScreenCenter(), { animation: { duration: 200 } })} title="放大" className={btnClass}>
        <ZoomIn size={15} />
      </button>
      <div className="mx-0.5 h-4 w-px bg-border" />
      <button onClick={() => editor.zoomToFit({ animation: { duration: 300 } })} title="自適應" className={btnClass}>
        <Maximize size={15} />
      </button>
    </div>
  )
}
