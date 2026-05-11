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
// Spec 13 — Sticky-Only Strategy overlays
import { ZoneOverlay } from './ZoneOverlay'
import { ParkSidebar } from './ParkSidebar'
import { HmwTabBar } from './HmwTabBar'
import { CommModeIndicator } from './CommModeIndicator'
// Spec 14 + 15 — Timer + Advance vote
import { TimerBadge } from '../timer/TimerBadge'
import { TimerControlPanel } from '../timer/TimerControlPanel'
import { AdvanceVoteBanner } from '../vote/AdvanceVoteBanner'
import { useProjectRealtime } from '@/hooks/useProjectRealtime'

interface CanvasPanelProps {
  projectId: string
  currentStage?: DTStage
  // Spec 13: 由父層注入當前 sub_phase 與 comm_mode
  subPhase?: string | null
  commMode?: 'silent_write' | 'reveal_round' | 'silent_rearrange' | 'discussion'
  subPhaseName?: string
  nextRevealSeat?: string | null
  // Spec 14 + 15: teacher mode + current user id
  isTeacher?: boolean
  currentUserId?: string
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
  subPhase = null,
  commMode = 'discussion',
  subPhaseName,
  nextRevealSeat = null,
  isTeacher = false,
  currentUserId = '',
}: CanvasPanelProps) {
  // Spec 14 + 15: pull timer + vote state
  const { voteSession } = useProjectRealtime(projectId)
  const [connected, setConnected] = useState(false)
  const store = useMemo(() => createTLStore({ shapeUtils: defaultShapeUtils }), [])
  const docRef = useRef<Y.Doc | null>(null)
  const providerRef = useRef<WebsocketProvider | null>(null)
  const [shapesMap, setShapesMap] = useState<Y.Map<unknown> | null>(null)

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
        {/* Spec 13: zone 視覺框 — 相機座標傳 0/0/1，前端 store 內部再對齊 */}
        <ZoneOverlay cameraX={0} cameraY={0} cameraZ={1} />
      </Tldraw>
      <HmwTabBar />
      <CommModeIndicator
        subPhase={subPhase}
        commMode={commMode}
        subPhaseName={subPhaseName}
        nextRevealSeat={nextRevealSeat}
      />
      <ParkSidebar notes={[]} />
      {/* Spec 15: 所有人可見的 timer */}
      <TimerBadge />
      {/* Spec 15: 老師限定 timer 控制 */}
      <TimerControlPanel projectId={projectId} isTeacher={isTeacher} />
      {/* Spec 14 N2: Crew 推進投票 */}
      <AdvanceVoteBanner
        projectId={projectId}
        isTeacher={isTeacher}
        currentUserId={currentUserId}
        session={voteSession}
      />
    </div>
  )
}
