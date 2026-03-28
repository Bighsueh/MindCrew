import { useEditor, DefaultColorStyle } from '@tldraw/tldraw'
import { useValue } from '@tldraw/state-react'
import { MousePointer2, Hand, StickyNote } from 'lucide-react'
import { cn } from '../../lib/utils'

const TOOLS = [
  { id: 'select', icon: MousePointer2, label: '選取', kbd: 'V' },
  { id: 'hand', icon: Hand, label: '拖曳', kbd: 'H' },
  { id: 'note', icon: StickyNote, label: '便利貼', kbd: 'N' },
] as const

type NoteColor = 'black' | 'yellow' | 'orange' | 'red' | 'blue' | 'green' | 'violet' | 'light-violet'

const NOTE_COLORS: { id: NoteColor; hex: string; label: string }[] = [
  { id: 'black', hex: '#1d1d1d', label: '黑色' },
  { id: 'yellow', hex: '#f1ac4b', label: '黃色' },
  { id: 'orange', hex: '#e16919', label: '橘色' },
  { id: 'red', hex: '#e03131', label: '紅色' },
  { id: 'blue', hex: '#4465e9', label: '藍色' },
  { id: 'green', hex: '#099268', label: '綠色' },
  { id: 'violet', hex: '#ae3ec9', label: '紫色' },
  { id: 'light-violet', hex: '#e085f4', label: '淡紫' },
]

export function MiniToolbar() {
  const editor = useEditor()
  const currentToolId = useValue('current tool', () => editor.getCurrentToolId(), [editor])

  const showColors = useValue('show colors', () => {
    if (editor.getCurrentToolId() === 'note') return true
    const selected = editor.getSelectedShapes()
    return selected.length > 0 && selected.some((s) => s.type === 'note')
  }, [editor])

  const activeColor = useValue('active color', () => {
    const shared = editor.getSharedStyles().get(DefaultColorStyle)
    if (shared && shared.type === 'shared') return shared.value as string
    return editor.getStyleForNextShape(DefaultColorStyle) as string
  }, [editor])

  const handleColorChange = (color: NoteColor) => {
    editor.setStyleForSelectedShapes(DefaultColorStyle, color)
    editor.setStyleForNextShapes(DefaultColorStyle, color)
  }

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

      {showColors && (
        <>
          <div className="mx-1 h-5 w-px bg-border" />
          {NOTE_COLORS.map(({ id, hex, label }) => (
            <button
              key={id}
              onClick={() => handleColorChange(id)}
              title={label}
              className={cn(
                'flex items-center justify-center rounded-full p-0.5 transition-all cursor-pointer',
                activeColor === id
                  ? 'ring-2 ring-offset-1 ring-primary scale-110'
                  : 'hover:scale-110',
              )}
            >
              <span
                className="block h-4 w-4 rounded-full border border-black/10"
                style={{ backgroundColor: hex }}
              />
            </button>
          ))}
        </>
      )}
    </div>
  )
}
