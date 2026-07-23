import { useEffect, useMemo, useRef, useState } from 'react'
import '../../lib/tldrawColorPatch'
import { Tldraw, TLComponents, createTLStore, defaultShapeUtils } from '@tldraw/tldraw'
import type { Editor } from '@tldraw/tldraw'
import '@tldraw/tldraw/tldraw.css'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import type { DTStage, MicroPhaseId } from '../../types/models'
import { MiniToolbar } from './MiniToolbar'
import { ZoomControls } from './ZoomControls'
import { NoteAuthorOverlay } from './NoteAuthorOverlay'
import { NoteHighlightOverlay } from './NoteHighlightOverlay'
import { HumanNoteColorInjector } from './HumanNoteColorInjector'
import { AnimatedYjsBridge } from './AnimatedYjsBridge'
import { WhiteboardErrorFallback } from './WhiteboardErrorFallback'
// Phase 42 C0：真人建立便條接線（gate + RejectToast）、引用 UI、違規 badge
import { HumanNoteCreateSync } from './HumanNoteCreateSync'
import { NoteCitationTool } from './NoteCitationTool'
import { GateViolationOverlay } from './GateViolationOverlay'
// Phase 42 C2：設計題目（2.7）外框＋角標（kind 驅動、不用顏色，spec 23 §2.4 / 25 §3.3）
import { DesignQuestionOverlay } from './DesignQuestionOverlay'
import { OverflowHint } from './OverflowHint'
// Phase 17 Stream B (Spec 13) — Sticky-Only Strategy overlays
import { ZoneOverlay } from './ZoneOverlay'
import { HmwTabBar } from './HmwTabBar'
// Phase 17 Stream B (Spec 15) — Timer（v4.15：advance vote 已移除）
import { TimerControlPanel } from '../timer/TimerControlPanel'
import { useProjectRealtime } from '@/hooks/useProjectRealtime'
import { useCanvasStatsStore } from '@/stores/canvasStatsStore'
// Phase 20 — Empty state for the start-action UX
import { CanvasEmptyState, type StartActionStage } from './CanvasEmptyState'

interface CanvasPanelProps {
  projectId: string
  currentStage?: DTStage
  // Phase 17 Stream B: teacher mode + current user id for vote / timer
  isTeacher?: boolean
  currentUserId?: string
  // Phase 20: EmptyState action callback. Stable string actionId.
  onEmptyStateAction?: (actionId: string) => void
  // Phase 20: notify parent when shape count changes (for EmptyState toggle / tour)
  onShapeCountChange?: (count: number) => void
  // Phase 20: parent override for EmptyState visibility; fallback = shapeCount === 0
  emptyStateVisible?: boolean
  // 當 EmptyState 退場動畫（飛入「起頭」chip）完成時觸發 → 父層用來同步 chip flash
  onEmptyStateHide?: () => void
  // micro-phase 細粒度 hint（1.1–2.3, Phase 29 縮為第一鑽石）
  currentMicroPhase?: MicroPhaseId | null
  // Observer mode → render tldraw in read-only mode
  isObserver?: boolean
}

// Phase 20: narrow DTStage to the stages the EmptyState recognises (matches STAGE_ACTIONS keys).
// Phase 29 (spec/04-06 §4.10): only discover / define remain.
function asStartActionStage(s: DTStage | undefined): StartActionStage {
  if (s === 'discover' || s === 'define') return s
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
  // 容錯隔離：單張便條渲染失敗只隱藏那一張，不再升級成整面白板崩潰。
  ShapeErrorFallback: () => null,
  ShapeIndicatorErrorFallback: () => null,
}

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
const STAGE_BG: Record<string, string> = {
  discover: 'bg-[#fefce8]',
  define: 'bg-[#fef3e2]',
  completed: 'bg-[#faf0e6]',
}

export function CanvasPanel({
  projectId,
  currentStage,
  isTeacher = false,
  // currentUserId 仍保留在 props 介面（callers 相容），advance vote 移除後不再使用
  // Phase 20
  onEmptyStateAction,
  onShapeCountChange,
  emptyStateVisible,
  onEmptyStateHide,
  currentMicroPhase,
  isObserver = false,
}: CanvasPanelProps) {
  // Spec 15: pull timer state（每 5s polling 寫進 timerStore）
  useProjectRealtime(projectId)
  const [connected, setConnected] = useState(false)
  const store = useMemo(() => createTLStore({ shapeUtils: defaultShapeUtils }), [])
  const editorRef = useRef<Editor | null>(null)
  const docRef = useRef<Y.Doc | null>(null)
  const providerRef = useRef<WebsocketProvider | null>(null)
  const [shapesMap, setShapesMap] = useState<Y.Map<unknown> | null>(null)
  // Phase 20: track shape count for EmptyState visibility fallback
  const [shapeCount, setShapeCount] = useState(0)
  // 暫態渲染崩潰後，用 remount（換 key）原地復原白板，不必整頁 refresh、不丟資料。
  const [tldrawKey, setTldrawKey] = useState(0)
  const components = useMemo<TLComponents>(
    () => ({
      ...TLDRAW_COMPONENTS,
      ErrorFallback: ({ error }) => (
        <WhiteboardErrorFallback
          error={error}
          onReload={() => setTldrawKey((k) => k + 1)}
        />
      ),
    }),
    [],
  )

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
      const shapes = records.filter((r) => r.typeName === 'shape')
      const next = shapes.length
      setShapeCount(next)
      onShapeCountChange?.(next)
      // Phase 42 B1（spec 28 §3.2）：暖場「N／目標」計數——kind=content 便條數
      // （label 標題不計；meta 沒帶 kind 的本地人類便條視為 content）。
      const contentNotes = shapes.filter((r) => {
        const rec = r as unknown as { type?: string; meta?: Record<string, unknown> }
        if (rec.type !== 'note') return false
        const kind = rec.meta?.kind
        return kind === undefined || kind === '' || kind === 'content'
      }).length
      useCanvasStatsStore.getState().setContentNoteCount(contentNotes)
    }
    update()
    const unlisten = store.listen(update, { source: 'all', scope: 'document' })
    return unlisten
  }, [store, onShapeCountChange])

  // 讓 editor 的 readonly 隨 isObserver 持續同步（不能只靠 onMount）。
  // 根因：seats 非同步載入，canvas 掛載當下 isObserver=true（座位還沒回）→ onMount 把
  // editor 設成 readonly；座位載入後 isObserver 翻 false，但 onMount 不會重跑 → editor
  // 永久卡 readonly → 入座學生按便利貼時 createShape 變 no-op、tldraw 取 undefined.id 崩潰。
  useEffect(() => {
    editorRef.current?.updateInstanceState({ isReadonly: isObserver })
  }, [isObserver])

  const stageBg = currentStage ? STAGE_BG[currentStage] ?? '' : ''

  return (
    <div className={`relative h-full w-full overflow-hidden ${stageBg}`}>
      {!connected && (
        <div className="absolute top-2 left-2 z-50 rounded bg-warning-bg px-2 py-1 text-xs text-warning">
          白板連線中...
        </div>
      )}
      <Tldraw
        key={tldrawKey}
        store={store}
        inferDarkMode={false}
        components={components}
        onMount={(editor) => {
          editorRef.current = editor
          editor.updateInstanceState({ isReadonly: isObserver })
        }}
      >
        <AnimatedYjsBridge shapesMap={shapesMap} store={store} />
        <MiniToolbar />
        <ZoomControls />
        <NoteAuthorOverlay />
        {/* Phase 42 A3（WP7，#34）：組長指認便條高亮（ttl 自動退場） */}
        <NoteHighlightOverlay />
        {/* Phase 22：人類新貼便利貼時自動套席位鎖定色 */}
        <HumanNoteColorInjector />
        {/* Phase 42 C0 ⑥(b)：真人建便條 → POST gate → RejectToast / force_publish */}
        {!isObserver && (
          <HumanNoteCreateSync projectId={projectId} shapesMap={shapesMap} />
        )}
        {/* Phase 42 C0 ⑤：選自己的便條 → 點選引用 */}
        {!isObserver && <NoteCitationTool projectId={projectId} />}
        {/* Phase 42 C0：force_publish 違規標記 badge */}
        <GateViolationOverlay />
        {/* Phase 42 C2：設計題目專屬外框＋角標（依文字句型辨識） */}
        <DesignQuestionOverlay />
        {/* Phase 17 Stream B (Spec 13): zone overlay. Camera coords passthrough — store internal aligns. */}
        <ZoneOverlay cameraX={0} cameraY={0} cameraZ={1} />
        {/* Phase 42 D1b（#33）：內容超出視野時的「縮小看全部」提示鈕 */}
        <OverflowHint />
      </Tldraw>
      {/* Phase 17 Stream B (Spec 13) overlays — outside Tldraw to avoid double-render */}
      <HmwTabBar />
      {/* Phase 17 Stream B (Spec 16 §6.5.3): Timer 改放 Workspace navbar（TimerInline）。
          這裡保留註解便於追蹤；舊浮動 TimerBadge 已下架避免與 navbar 重複。 */}
      {/* Phase 17 Stream B (Spec 15): teacher-only timer control */}
      <TimerControlPanel projectId={projectId} isTeacher={isTeacher} />
      {/* Phase 20: EmptyState must be a <Tldraw> sibling, not a child (tldraw double-renders children).
          Only mount when parent registered onEmptyStateAction, to avoid surprising pre-wired callers. */}
      {onEmptyStateAction !== undefined && (
        <CanvasEmptyState
          stage={asStartActionStage(currentStage)}
          currentMicroPhase={currentMicroPhase}
          visible={emptyStateVisible ?? shapeCount === 0}
          onActionClick={onEmptyStateAction}
          onHide={onEmptyStateHide}
        />
      )}
    </div>
  )
}
