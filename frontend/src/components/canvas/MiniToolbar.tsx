import { useEditor } from '@tldraw/tldraw'
import { useValue } from '@tldraw/state-react'
import { MousePointer2, Hand, StickyNote } from 'lucide-react'
import { cn } from '../../lib/utils'

const TOOLS = [
  { id: 'select', icon: MousePointer2, label: '選取', kbd: 'V' },
  { id: 'hand', icon: Hand, label: '拖曳', kbd: 'H' },
  { id: 'note', icon: StickyNote, label: '便利貼', kbd: 'N' },
] as const

// 手動選色已移除：每個角色只有一個專屬便條色，由作者席位色決定（見 HumanNoteColorInjector），
// 使用者不可把便條改成別色，以維持「便條色 = 聊天色 = 角色身分」一致性。

export function MiniToolbar() {
  const editor = useEditor()
  const currentToolId = useValue('current tool', () => editor.getCurrentToolId(), [editor])

  // readonly（觀察者 / 座位未就緒）時不可建立便條。否則按便利貼 → createShape no-op →
  // tldraw 在 note 工具取 undefined.id 崩潰（見 CanvasPanel readonly 同步註解）。
  const isReadonly = useValue('readonly', () => editor.getInstanceState().isReadonly, [editor])

  return (
    <div className="absolute bottom-4 left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-border bg-surface/95 px-2 py-1.5 shadow-lg backdrop-blur-sm">
      {TOOLS.map(({ id, icon: Icon, label, kbd }) => {
        const isActive = currentToolId === id
        // 便利貼在 readonly 時停用（觀察者不可建立便條；亦封住 readonly 殘留視窗的崩潰）。
        const disabled = isReadonly && id === 'note'
        return (
          <button
            key={id}
            onClick={() => { if (!disabled) editor.setCurrentTool(id) }}
            disabled={disabled}
            title={disabled ? `${label}（觀察模式無法新增便條）` : `${label} (${kbd})`}
            className={cn(
              'flex items-center justify-center rounded-lg p-2 transition-colors',
              disabled
                ? 'cursor-not-allowed text-text-muted/40'
                : 'cursor-pointer',
              !disabled && isActive
                ? 'bg-primary text-text-inverse shadow-sm'
                : !disabled
                  ? 'text-text-muted hover:bg-surface-hover hover:text-text'
                  : '',
            )}
          >
            <Icon size={18} strokeWidth={isActive ? 2.5 : 2} />
          </button>
        )
      })}
    </div>
  )
}
