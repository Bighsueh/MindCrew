/**
 * NoteCitationTool — 便條點選引用 UI（Phase 42 C0 ⑤，spec 06 v4.25 / #30）。
 *
 * 流程：選取**自己的**便條 → 「引用」鈕 → 進入引用模式，點選其他便條 toggle
 * （外框高亮）→ 確認 → PATCH cites（全量覆蓋）。全程只顯示便條內容、不露 id。
 * 座標換算照 NoteAuthorOverlay 的 pageToViewport 模式。
 */
import { useState } from 'react'
import { useEditor } from '@tldraw/tldraw'
import { track, useValue } from '@tldraw/state-react'
import type { TLShape, TLShapeId } from '@tldraw/tldraw'
import { useAuthStore } from '../../stores/authStore'
import { updateNoteCites } from '../../services/projectService'
import { parseAuthor } from './NoteAuthorOverlay'

const NOTE_W = 200
const NOTE_H = 150

interface CitingState {
  sourceId: string
  selected: Set<string>
}

interface NoteCitationToolProps {
  projectId: string
}

export const NoteCitationTool = track(function NoteCitationTool({
  projectId,
}: NoteCitationToolProps) {
  const editor = useEditor()
  const user = useAuthStore((s) => s.user)
  const [citing, setCiting] = useState<CitingState | null>(null)
  const [saving, setSaving] = useState(false)

  const selectedIds = useValue<TLShapeId[]>(
    'selectedShapeIds',
    () => editor.getSelectedShapeIds(),
    [editor],
  )
  const zoom = editor.getZoomLevel()

  const notes = editor
    .getCurrentPageShapes()
    .filter((s): s is TLShape => s.type === 'note')

  // ── 引用模式 ──
  if (citing) {
    const source = notes.find((s) => s.id === citing.sourceId)
    if (!source) {
      // 來源便條消失（被刪 / 同步重建）→ 退出引用模式
      setCiting(null)
      return null
    }

    const toggle = (id: string) => {
      const next = new Set(citing.selected)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      setCiting({ ...citing, selected: next })
    }

    const confirm = async () => {
      if (saving) return
      setSaving(true)
      try {
        await updateNoteCites(projectId, citing.sourceId, Array.from(citing.selected))
        setCiting(null)
      } catch (err: unknown) {
        console.warn('NoteCitationTool: update cites failed', err)
      } finally {
        setSaving(false)
      }
    }

    return (
      <>
        {/* 可點選的便條覆蓋層（來源便條本身以藍框標示、不可點） */}
        {notes.map((shape) => {
          const point = editor.pageToViewport({ x: shape.x, y: shape.y })
          const isSource = shape.id === citing.sourceId
          const isCited = citing.selected.has(shape.id)
          return (
            <div
              key={`cite-${shape.id}`}
              className="absolute z-30"
              style={{
                left: point.x,
                top: point.y,
                width: NOTE_W * zoom,
                height: NOTE_H * zoom,
                border: isSource
                  ? `${Math.max(2, 3 * zoom)}px solid #2563eb`
                  : isCited
                    ? `${Math.max(2, 3 * zoom)}px solid #16a34a`
                    : `${Math.max(1, 2 * zoom)}px dashed rgba(100,116,139,0.5)`,
                borderRadius: 6 * zoom,
                cursor: isSource ? 'default' : 'pointer',
                background: isCited ? 'rgba(22,163,74,0.08)' : 'transparent',
              }}
              onClick={() => {
                if (!isSource) toggle(shape.id)
              }}
            />
          )
        })}
        {/* 確認 / 取消列 */}
        <div
          className="absolute left-1/2 top-3 z-40 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-border bg-surface/95 px-3 py-2 shadow-lg backdrop-blur-sm"
          role="toolbar"
          aria-label="引用模式"
        >
          <span className="text-xs text-text-muted">
            點選要引用的便條（已選 {citing.selected.size} 張）
          </span>
          <button
            onClick={() => void confirm()}
            disabled={saving}
            className="rounded-md bg-primary px-3 py-1 text-xs font-semibold text-text-inverse disabled:opacity-50"
          >
            {saving ? '儲存中…' : '確認'}
          </button>
          <button
            onClick={() => setCiting(null)}
            disabled={saving}
            className="rounded-md bg-surface-hover px-3 py-1 text-xs text-text"
          >
            取消
          </button>
        </div>
      </>
    )
  }

  // ── 常態：單選自己的便條 → 顯示「引用」鈕 ──
  if (!user || selectedIds.length !== 1) return null
  const shape = notes.find((s) => s.id === selectedIds[0])
  if (!shape) return null
  const meta = shape.meta as Record<string, unknown>
  const { name, type } = parseAuthor(meta.author)
  if (type !== 'human' || name !== user.display_name) return null

  const point = editor.pageToViewport({ x: shape.x, y: shape.y })
  const existingCites = Array.isArray(meta.cites)
    ? (meta.cites as unknown[]).filter((c): c is string => typeof c === 'string')
    : []

  return (
    <button
      className="absolute z-30 rounded-full bg-primary px-2.5 py-1 text-xs font-semibold text-text-inverse shadow-md"
      style={{
        left: point.x + NOTE_W * zoom - 8,
        top: point.y - 12,
      }}
      onClick={() =>
        setCiting({ sourceId: shape.id, selected: new Set(existingCites) })
      }
    >
      引用
    </button>
  )
})
