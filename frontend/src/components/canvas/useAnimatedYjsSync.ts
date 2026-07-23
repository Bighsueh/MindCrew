/**
 * useAnimatedYjsSync — Pure Yjs-to-tldraw sync with CSS transition trigger.
 *
 * All position changes go through store.put() instantly (correct final state).
 * When AI-initiated position changes are detected, toggles a CSS class on the
 * tldraw container to enable CSS transition on .tl-shape elements.
 * The browser's CSS transition engine handles smooth interpolation — no
 * conflict with the store, no two-writer problem.
 */
import { useEffect, useRef } from 'react'
import type { TLRecord, TLStore } from '@tldraw/tldraw'
import type * as Y from 'yjs'

interface ShapePosition {
  x: number
  y: number
}

const COLOR_MAP: Record<string, string> = {
  yellow: 'yellow',
  blue: 'blue',
  green: 'green',
  red: 'red',
  orange: 'orange',
  violet: 'violet',
  // 補齊 8 色池剩餘 token（tldraw 原生支援），避免靜默 fallback 成 yellow。
  'light-blue': 'light-blue',
  'light-green': 'light-green',
  pink: 'violet',
  purple: 'light-violet',
}

function toTldrawColor(color: unknown): string {
  if (typeof color !== 'string') return 'yellow'
  return COLOR_MAP[color] ?? 'yellow'
}

const BASE62 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
function toIndexKey(n: number): string {
  return `a${BASE62[n % BASE62.length]}`
}

/**
 * 只接受有限數字（擋掉 undefined / null / 字串 / NaN / Infinity）。
 * 注意：刻意保留合法的 0 —— 舊版用 `value || fallback` 會把座標 0 誤判成 falsy 而被換掉。
 */
function finiteOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

// Exported for unit testing（純函式，無 DOM 依賴）。
export function buildRecord(
  key: string,
  shape: Record<string, unknown>,
  idx: number,
): TLRecord {
  const id = key.startsWith('shape:') ? key : `shape:${key}`
  return {
    id: id as TLRecord['id'],
    typeName: 'shape',
    type: 'note',
    x: finiteOr(shape.x, 100 + idx * 30),
    y: finiteOr(shape.y, 100 + idx * 30),
    rotation: 0,
    parentId: 'page:page' as TLRecord['id'],
    index: toIndexKey(idx),
    isLocked: false,
    opacity: 1,
    meta: {
      author: typeof shape.author === 'string' ? shape.author : '',
      _moving_by: (shape._moving_by as string) || '',
      // Phase 24：把 sidecar 寫入的 createdAt 帶進 tldraw meta，
      // 供 Activity Highlight（聊天氣泡 ⇄ 便利貼）時間配對使用。
      created_at: typeof shape.createdAt === 'string' ? shape.createdAt : '',
      // Spec 27 (Phase 36)：便條欄位帶進 meta（kind / group_id）。
      kind: typeof shape.kind === 'string' ? shape.kind : 'content',
      group_id: typeof shape.group_id === 'string' ? shape.group_id : '',
      // Phase 42 C0 (spec 06 v4.25)：引用鏈 + 強推標記；gate_violation 供違規 badge。
      cites: Array.isArray(shape.cites)
        ? (shape.cites.filter((c) => typeof c === 'string') as string[])
        : [],
      time_box_forced: shape.time_box_forced === true,
      gate_violation:
        shape.gate_violation && typeof shape.gate_violation === 'object'
          ? JSON.stringify(shape.gate_violation)
          : '',
    },
    props: {
      text: (shape.content as string) || '',
      color: toTldrawColor(shape.color),
      size: 'm' as const,
      font: 'sans' as const,
      align: 'middle' as const,
      verticalAlign: 'middle' as const,
      growY: 0,
      fontSizeAdjustment: 0,
      url: '',
      scale: 1,
    },
  } as unknown as TLRecord
}

export function useAnimatedYjsSync(
  shapesMap: Y.Map<unknown> | null,
  store: TLStore,
  onPositionChange: () => void,
  onPositionChangeEnd: () => void,
) {
  const positionsRef = useRef<Map<string, ShapePosition>>(new Map())

  useEffect(() => {
    if (!shapesMap) return

    const syncToStore = () => {
      try {
        const records: TLRecord[] = []
        const positions = positionsRef.current
        let hasMoved = false
        let idx = 0

        shapesMap.forEach((value: unknown, key: string) => {
          // 逐張隔離：單張便條建構失敗只跳過它，不讓整批同步中斷。
          try {
            const shape = value as Record<string, unknown>
            if (!shape || typeof shape !== 'object') return

            const record = buildRecord(key, shape, idx)
            const id = record.id as string
            // record 為 note shape，x/y 不在 TLRecord union 的共同欄位上，明確取出。
            const pos = record as unknown as { x: number; y: number }
            const newX = pos.x
            const newY = pos.y

            const prev = positions.get(id)
            if (prev && (prev.x !== newX || prev.y !== newY)) {
              hasMoved = true
            }
            positions.set(id, { x: newX, y: newY })
            records.push(record)
            idx++
          } catch (err) {
            console.warn('useAnimatedYjsSync: skipped malformed shape', key, err)
          }
        })

        // Enable CSS transition BEFORE updating store
        if (hasMoved) {
          onPositionChange()
        }

        // Write final positions to store (instant in store, CSS animates visually).
        // 批次 put 若因單張 record 通不過 tldraw 驗證而 throw，降級為逐張 put，
        // 跳過壞的那張、保住其餘便條 —— 避免「一張壞便條讓整面白板的便條全部消失」。
        if (records.length > 0) {
          store.mergeRemoteChanges(() => {
            try {
              store.put(records)
            } catch (batchErr) {
              console.warn('useAnimatedYjsSync: batch put failed, falling back to per-record', batchErr)
              for (const r of records) {
                try {
                  store.put([r])
                } catch (recErr) {
                  console.warn('useAnimatedYjsSync: skipped invalid record', r.id, recErr)
                }
              }
            }
          })
        }

        // Schedule transition removal after animation completes
        if (hasMoved) {
          onPositionChangeEnd()
        }
      } catch (err) {
        console.warn('useAnimatedYjsSync: sync failed', err)
      }
    }

    shapesMap.observe(syncToStore)
    syncToStore()

    return () => {
      shapesMap.unobserve(syncToStore)
    }
  }, [shapesMap, store, onPositionChange, onPositionChangeEnd])
}
