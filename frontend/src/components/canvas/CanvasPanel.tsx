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
// Phase 17 Stream B (Spec 13) — Sticky-Only Strategy overlays
import { ZoneOverlay } from './ZoneOverlay'
import { ParkSidebar } from './ParkSidebar'
import { HmwTabBar } from './HmwTabBar'
import { CommModeIndicator } from './CommModeIndicator'
// Phase 17 Stream B (Spec 14 + 15) — Timer + Advance vote
import { TimerBadge } from '../timer/TimerBadge'
import { TimerControlPanel } from '../timer/TimerControlPanel'
import { AdvanceVoteBanner } from '../vote/AdvanceVoteBanner'
import { useProjectRealtime } from '@/hooks/useProjectRealtime'
// Phase 20 — Empty state for the start-action UX
import { CanvasEmptyState, type StartActionStage } from './CanvasEmptyState'

interface CanvasPanelProps {
  projectId: string
  currentStage?: DTStage
  // Phase 17 Stream B: parent injects current sub_phase + comm_mode
  subPhase?: string | null
  commMode?: 'silent_write' | 'reveal_round' | 'silent_rearrange' | 'discussion'
  subPhaseName?: string
  nextRevealSeat?: string | null
  // Phase 17 Stream B: teacher mode + current user id for vote / timer
  isTeacher?: boolean
  currentUserId?: string
  // Phase 20: EmptyState action callback. Stable string actionId.
  onEmptyStateAction?: (actionId: string) => void
  // Phase 20: notify parent when shape count changes (for EmptyState toggle / tour)
  onShapeCountChange?: (count: number) => void
  // Phase 20: parent override for EmptyState visibility; fallback = shapeCount === 0
  emptyStateVisible?: boolean
}

// Phase 20: narrow DTStage to the 4 stages the EmptyState recognises (matches STAGE_ACTIONS keys)
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
  // Phase 17 Stream B
  subPhase = null,
  commMode = 'discussion',
  subPhaseName,
  nextRevealSeat = null,
  isTeacher = false,
  currentUserId = '',
  // Phase 20
  onEmptyStateAction,
  onShapeCountChange,
  emptyStateVisible,
}: CanvasPanelProps) {
  // Phase 17 Stream B (Spec 14 + 15): pull timer + vote state
  const { voteSession } = useProjectRealtime(projectId)
  const [connected, setConnected] = useState(false)
  const store = useMemo(() => createTLStore({ shapeUtils: defaultShapeUtils }), [])
  const docRef = useRef<Y.Doc | null>(null)
  const providerRef = useRef<WebsocketProvider | null>(null)
  const [shapesMap, setShapesMap] = useState<Y.Map<unknown> | null>(null)
  // Phase 20: track shape count for EmptyState visibility fallback
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

  // Phase 20: subscribe to tldraw store for shape-count changes (used by EmptyState).
  // Deliberately outside <Tldraw> children because tldraw renders children twice.
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
        {/* Phase 17 Stream B (Spec 13): zone overlay. Camera coords passthrough — store internal aligns. */}
        <ZoneOverlay cameraX={0} cameraY={0} cameraZ={1} />
      </Tldraw>
      {/* Phase 17 Stream B (Spec 13) overlays — outside Tldraw to avoid double-render */}
      <HmwTabBar />
      <CommModeIndicator
        subPhase={subPhase}
        commMode={commMode}
        subPhaseName={subPhaseName}
        nextRevealSeat={nextRevealSeat}
      />
      <ParkSidebar notes={[]} />
      {/* Phase 17 Stream B (Spec 15): everyone-visible timer */}
      <TimerBadge />
      {/* Phase 17 Stream B (Spec 15): teacher-only timer control */}
      <TimerControlPanel projectId={projectId} isTeacher={isTeacher} />
      {/* Phase 17 Stream B (Spec 14 N2): Crew advance vote */}
      <AdvanceVoteBanner
        projectId={projectId}
        isTeacher={isTeacher}
        currentUserId={currentUserId}
        session={voteSession}
      />
      {/* Phase 20: EmptyState must be a <Tldraw> sibling, not a child (tldraw double-renders children).
          Only mount when parent registered onEmptyStateAction, to avoid surprising pre-wired callers. */}
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
