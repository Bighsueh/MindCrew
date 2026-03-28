import { useEditor } from '@tldraw/tldraw'
import { useValue } from '@tldraw/state-react'
import { MousePointer2, Hand, StickyNote } from 'lucide-react'
import { cn } from '../../lib/utils'

const TOOLS = [
  { id: 'select', icon: MousePointer2, label: '選取', kbd: 'V' },
  { id: 'hand', icon: Hand, label: '拖曳', kbd: 'H' },
  { id: 'note', icon: StickyNote, label: '便利貼', kbd: 'N' },
] as const

export function MiniToolbar() {
  const editor = useEditor()
  const currentToolId = useValue('current tool', () => editor.getCurrentToolId(), [editor])

  return (
    <div className="absolute bottom-4 left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-border bg-surface/95 px-2 py-1.5 shadow-lg backdrop-blur-sm">
      {TOOLS.map(({ id, icon: Icon, label, kbd }) => {
        const isActive = currentToolId === id
        return (
          <button
            key={id}
            onClick={() => editor.setCurrentTool(id)}
            title={`${label} (${kbd})`}
            className={cn(
              'flex items-center justify-center rounded-lg p-2 transition-colors cursor-pointer',
              isActive
                ? 'bg-primary text-text-inverse shadow-sm'
                : 'text-text-muted hover:bg-surface-hover hover:text-text',
            )}
          >
            <Icon size={18} strokeWidth={isActive ? 2.5 : 2} />
          </button>
        )
      })}
    </div>
  )
}
