import { useEffect, useMemo, useRef, useState } from 'react'
import { Tldraw, TLComponents, createTLStore, defaultShapeUtils } from '@tldraw/tldraw'
import '@tldraw/tldraw/tldraw.css'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import type { DTStage } from '../../types/models'
import { MiniToolbar } from './MiniToolbar'
import { ZoomControls } from './ZoomControls'
import { NoteAuthorOverlay } from './NoteAuthorOverlay'
import { AnimatedYjsBridge } from './AnimatedYjsBridge'
import { CanvasEmptyState, type StartActionStage } from './CanvasEmptyState'

interface CanvasPanelProps {
  projectId: string
  currentStage?: DTStage
  /** 透傳給 EmptyState 的動作回呼。actionId 是穩定字串。 */
  onEmptyStateAction?: (actionId: string) => void
  /** 白板 shape 數量變動時通知父層，父層可據此控制 EmptyState 顯示／教學動畫等。 */
  onShapeCountChange?: (count: number) => void
  /** 父層強制控制 banner 是否顯示；未提供時 fallback 為 shape 數量為 0。 */
  emptyStateVisible?: boolean
}

// 將 DTStage 收斂成 EmptyState 認得的 4 階段（與 STAGE_ACTIONS key 對齊）
function asStartActionStage(s: DTStage | undefined): StartActionStage {
  if (s === 'discover' || s === 'define' || s === 'develop' || s === 'deliver') return s
  return 'discover'
}

function getYjsWsUrl(): string {
  if (import.meta.env.DEV) {
    return 'ws://localhost:4000/yjs'
  }
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/yjs`
}

const TLDRAW_COMPONENTS: TLComponents = {
  StylePanel: null,
  Toolbar: null,
  PageMenu: null,
  ActionsMenu: null,
  HelpMenu: null,
  DebugPanel: null,
  DebugMenu: null,
  NavigationPanel: null,
  Minimap: null,
  MenuPanel: null,
}

const STAGE_BG: Record<string, string> = {
  discover: 'bg-[#fefce8]',
  define: 'bg-[#fef3e2]',
  develop: 'bg-[#fdf5ee]',
  deliver: 'bg-[#faf0e6]',
}

export function CanvasPanel({
  projectId,
  currentStage,
  onEmptyStateAction,
  onShapeCountChange,
  emptyStateVisible,
}: CanvasPanelProps) {
  const [connected, setConnected] = useState(false)
  const store = useMemo(() => createTLStore({ shapeUtils: defaultShapeUtils }), [])
  const docRef = useRef<Y.Doc | null>(null)
  const providerRef = useRef<WebsocketProvider | null>(null)
  const [shapesMap, setShapesMap] = useState<Y.Map<unknown> | null>(null)
  // 追蹤白板上 shape 數量；用於決定 EmptyState 是否顯示（fallback 條件）
  const [shapeCount, setShapeCount] = useState(0)

  useEffect(() => {
    const doc = new Y.Doc()
    docRef.current = doc
    const wsUrl = getYjsWsUrl()
    const provider = new WebsocketProvider(wsUrl, projectId, doc)
    providerRef.current = provider

    const onStatus = ({ status }: { status: string }) => {
      setConnected(status === 'connected')
    }
    provider.on('status', onStatus)

    setShapesMap(doc.getMap('shapes'))

    return () => {
      setShapesMap(null)
      provider.off('status', onStatus)
      provider.disconnect()
      provider.destroy()
      doc.destroy()
      docRef.current = null
      providerRef.current = null
    }
  }, [projectId])

  // 訂閱 tldraw store 的 shape 數量變化（用於 EmptyState 顯示判斷）。
  // 注意：故意不放在 <Tldraw> children 內，因為 tldraw 會 render children 兩次。
  useEffect(() => {
    const update = () => {
      const records = store.allRecords()
      const next = records.filter((r) => r.typeName === 'shape').length
      setShapeCount(next)
      onShapeCountChange?.(next)
    }
    update()
    const unlisten = store.listen(update, { source: 'all', scope: 'document' })
    return unlisten
  }, [store, onShapeCountChange])

  const stageBg = currentStage ? STAGE_BG[currentStage] ?? '' : ''

  return (
    <div className={`relative h-full w-full overflow-hidden ${stageBg}`}>
      {!connected && (
        <div className="absolute top-2 left-2 z-50 rounded bg-warning-bg px-2 py-1 text-xs text-warning">
          白板連線中...
        </div>
      )}
      <Tldraw
        store={store}
        inferDarkMode={false}
        components={TLDRAW_COMPONENTS}
      >
        <AnimatedYjsBridge shapesMap={shapesMap} store={store} />
        <MiniToolbar />
        <ZoomControls />
        <NoteAuthorOverlay />
      </Tldraw>
      {/* EmptyState 必須是 <Tldraw> 的 sibling，不能放進 children（tldraw 會雙重渲染）。
          只有當父層註冊 onEmptyStateAction 時才掛載，避免在未連線 wire 時干擾既有畫面。 */}
      {onEmptyStateAction !== undefined && (
        <CanvasEmptyState
          stage={asStartActionStage(currentStage)}
          visible={emptyStateVisible ?? shapeCount === 0}
          onActionClick={onEmptyStateAction}
        />
      )}
    </div>
  )
}
