import { StickyNote, Layers } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { CanvasStateResponse } from '../../types/models'

interface CanvasThumbnailProps {
  canvasState: CanvasStateResponse | null
  embedded?: boolean
}

const NOTE_COLORS: Record<string, string> = {
  yellow: 'bg-yellow-300',
  blue: 'bg-blue-300',
  green: 'bg-green-300',
  pink: 'bg-pink-300',
  violet: 'bg-violet-300',
  red: 'bg-red-300',
  orange: 'bg-orange-300',
  'light-blue': 'bg-sky-300',
}

function getNoteColor(color: string): string {
  return NOTE_COLORS[color] ?? 'bg-yellow-300'
}

export function CanvasThumbnail({ canvasState, embedded = false }: CanvasThumbnailProps) {
  if (!canvasState) {
    return (
      <div className={embedded ? '' : 'rounded-xl border border-border bg-surface p-5 shadow-sm'}>
        <div className="flex items-center gap-2 mb-4">
          <StickyNote size={16} className="text-accent" />
          <h3 className="text-sm font-semibold text-text">白板預覽</h3>
        </div>
        <p className="py-4 text-center text-sm text-text-muted">
          無法載入白板狀態
        </p>
      </div>
    )
  }

  const { total_notes, groups, notes } = canvasState

  return (
    <div className={embedded ? '' : 'rounded-xl border border-border bg-surface p-5 shadow-sm'}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <StickyNote size={16} className="text-accent" />
        <h3 className="text-sm font-semibold text-text">白板預覽</h3>
      </div>

      {/* Stats */}
      <div className="mb-4 flex items-center gap-4 text-xs text-text-muted">
        <span className="flex items-center gap-1">
          <StickyNote size={12} />
          {total_notes} 張便條紙
        </span>
        <span className="flex items-center gap-1">
          <Layers size={12} />
          {groups.length} 個分群
        </span>
      </div>

      {/* Visual representation */}
      {total_notes === 0 ? (
        <div className="flex h-24 items-center justify-center rounded-lg bg-bg">
          <p className="text-xs text-text-muted">尚無便條紙</p>
        </div>
      ) : (
        <div className="rounded-lg bg-bg p-3">
          {/* Grouped notes */}
          {groups.map((group) => (
            <div key={group.name} className="mb-3 last:mb-0">
              <p className="mb-1.5 text-xs font-medium text-text-muted truncate">
                {group.name}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {group.notes.map((noteId) => {
                  const note = notes.find((n) => n.id === noteId)
                  return (
                    <div
                      key={noteId}
                      className={cn(
                        'h-3 w-3 rounded-sm transition-transform hover:scale-150',
                        getNoteColor(note?.color ?? 'yellow'),
                      )}
                      title={note?.content}
                    />
                  )
                })}
              </div>
            </div>
          ))}

          {/* Ungrouped notes */}
          {canvasState.ungrouped.length > 0 && (
            <div className={cn(groups.length > 0 && 'mt-3 pt-3 border-t border-border/50')}>
              <p className="mb-1.5 text-xs font-medium text-text-muted">未分群</p>
              <div className="flex flex-wrap gap-1.5">
                {canvasState.ungrouped.map((noteId) => {
                  const note = notes.find((n) => n.id === noteId)
                  return (
                    <div
                      key={noteId}
                      className={cn(
                        'h-3 w-3 rounded-sm transition-transform hover:scale-150',
                        getNoteColor(note?.color ?? 'yellow'),
                      )}
                      title={note?.content}
                    />
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
