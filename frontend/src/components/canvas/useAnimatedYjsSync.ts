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
  pink: 'light-red',
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

function buildRecord(
  key: string,
  shape: Record<string, unknown>,
  idx: number,
): TLRecord {
  const id = key.startsWith('shape:') ? key : `shape:${key}`
  return {
    id: id as TLRecord['id'],
    typeName: 'shape',
    type: 'note',
    x: (shape.x as number) || 100 + idx * 30,
    y: (shape.y as number) || 100 + idx * 30,
    rotation: 0,
    parentId: 'page:page' as TLRecord['id'],
    index: toIndexKey(idx),
    isLocked: false,
    opacity: 1,
    meta: {
      author: typeof shape.author === 'string' ? shape.author : '',
      _moving_by: (shape._moving_by as string) || '',
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
          const shape = value as Record<string, unknown>
          if (!shape || typeof shape !== 'object') return

          const record = buildRecord(key, shape, idx)
          const id = record.id as string
          const newX = record.x as number
          const newY = record.y as number

          const prev = positions.get(id)
          if (prev && (prev.x !== newX || prev.y !== newY)) {
            hasMoved = true
          }
          positions.set(id, { x: newX, y: newY })
          records.push(record)
          idx++
        })

        // Enable CSS transition BEFORE updating store
        if (hasMoved) {
          onPositionChange()
        }

        // Write final positions to store (instant in store, CSS animates visually)
        if (records.length > 0) {
          store.mergeRemoteChanges(() => {
            store.put(records)
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
