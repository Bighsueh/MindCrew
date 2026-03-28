import { useEffect, useMemo, useRef, useState } from 'react'
import { Tldraw, TLRecord, createTLStore, defaultShapeUtils } from '@tldraw/tldraw'
import '@tldraw/tldraw/tldraw.css'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'

interface CanvasPanelProps {
  projectId: string
}

// Map sidecar color names to tldraw's TLDefaultColorStyle values
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

// Generate tldraw-compatible fractional index keys (base-62: 0-9A-Za-z)
const BASE62 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
function toIndexKey(n: number): string {
  return `a${BASE62[n % BASE62.length]}`
}

function getYjsWsUrl(): string {
  if (import.meta.env.DEV) {
    return 'ws://localhost:4000/yjs'
  }
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/yjs`
}

export function CanvasPanel({ projectId }: CanvasPanelProps) {
  const [connected, setConnected] = useState(false)
  const store = useMemo(() => createTLStore({ shapeUtils: defaultShapeUtils }), [])
  const providerRef = useRef<WebsocketProvider | null>(null)

  useEffect(() => {
    const doc = new Y.Doc()
    const wsUrl = getYjsWsUrl()
    const provider = new WebsocketProvider(wsUrl, projectId, doc)
    providerRef.current = provider

    const onStatus = ({ status }: { status: string }) => {
      setConnected(status === 'connected')
    }
    provider.on('status', onStatus)

    // Sync Yjs shapes map → tldraw store
    const shapesMap = doc.getMap('shapes')

    const syncToStore = () => {
      try {
        const records: TLRecord[] = []
        let idx = 0
        shapesMap.forEach((value: unknown, key: string) => {
          const shape = value as Record<string, unknown>
          if (!shape || typeof shape !== 'object') return

          const id = key.startsWith('shape:') ? key : `shape:${key}`

          records.push({
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
            meta: {},
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
          } as unknown as TLRecord)
          idx++
        })

        if (records.length > 0) {
          store.mergeRemoteChanges(() => {
            store.put(records)
          })
        }
      } catch (err) {
        console.warn('Failed to sync Yjs shapes to tldraw:', err)
      }
    }

    shapesMap.observe(syncToStore)
    syncToStore()

    return () => {
      shapesMap.unobserve(syncToStore)
      provider.off('status', onStatus)
      provider.disconnect()
      provider.destroy()
      doc.destroy()
      providerRef.current = null
    }
  }, [projectId, store])

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border border-border">
      {!connected && (
        <div className="absolute top-2 left-2 z-50 rounded bg-warning-bg px-2 py-1 text-xs text-warning">
          白板連線中...
        </div>
      )}
      <Tldraw store={store} inferDarkMode={false} hideUi={false} />
    </div>
  )
}
