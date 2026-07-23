/**
 * useHumanDragSync — 真人拖曳便條回寫 Yjs（Phase 42 C0 ⑥(a)，move-delta 前提）。
 *
 * 修復既存斷線：前端原本完全沒有 tldraw→Yjs 回寫，真人手拖只存在本地瀏覽器。
 * 監聽 store source='user' 的 note 位移 → debounce → 只對 sidecar 已存在的便條
 * 回寫 x/y 到 Yjs shapes map（本地草稿便條不回寫，由建立接線 ⑥(b) 處理）。
 *
 * 迴圈安全：遠端變更經 useAnimatedYjsSync 以 mergeRemoteChanges 寫入
 * （source='remote'），不會出現在本 listener → 不回彈。
 */
import { useEffect } from 'react'
import type { TLStore } from '@tldraw/tldraw'
import type * as Y from 'yjs'

const FLUSH_DEBOUNCE_MS = 400

interface PositionedRecord {
  id: string
  typeName: string
  type?: string
  x?: number
  y?: number
}

export function useHumanDragSync(
  shapesMap: Y.Map<unknown> | null,
  store: TLStore,
) {
  useEffect(() => {
    if (!shapesMap) return

    const pending = new Map<string, { x: number; y: number }>()
    let timer = 0

    const flush = () => {
      const doc = shapesMap.doc
      if (!doc || pending.size === 0) {
        pending.clear()
        return
      }
      doc.transact(() => {
        for (const [id, pos] of pending) {
          const existing = shapesMap.get(id)
          if (existing && typeof existing === 'object') {
            shapesMap.set(id, { ...(existing as Record<string, unknown>), x: pos.x, y: pos.y })
          }
        }
      })
      pending.clear()
    }

    const unlisten = store.listen(
      (entry) => {
        for (const [from, to] of Object.values(entry.changes.updated)) {
          const next = to as unknown as PositionedRecord
          const prev = from as unknown as PositionedRecord
          if (next.typeName !== 'shape' || next.type !== 'note') continue
          if (typeof next.x !== 'number' || typeof next.y !== 'number') continue
          if (prev.x === next.x && prev.y === next.y) continue
          // 只回寫 sidecar 已存在的便條（本地草稿交給建立接線）
          if (!shapesMap.has(next.id)) continue
          pending.set(next.id, { x: next.x, y: next.y })
        }
        if (pending.size > 0) {
          clearTimeout(timer)
          timer = window.setTimeout(flush, FLUSH_DEBOUNCE_MS)
        }
      },
      { source: 'user', scope: 'document' },
    )

    return () => {
      clearTimeout(timer)
      unlisten()
    }
  }, [shapesMap, store])
}
