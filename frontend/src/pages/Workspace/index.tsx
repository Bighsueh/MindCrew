import { useEffect, useCallback, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useChatStore } from '../../stores/chatStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useAuthStore } from '../../stores/authStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { advanceStage, leaveProject, getStage } from '../../services/projectService'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import { ConnectionBanner } from '../../components/workspace/ConnectionBanner'
import { SeatBar } from '../../components/workspace/SeatBar'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { CanvasPanel } from '../../components/canvas/CanvasPanel'
import { ProjectPersonasPanel } from '../../components/persona/ProjectPersonasPanel'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import { MessageCircle, Users } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { WSMessage, WSChatMessagePayload, WSTypingPayload, WSStageChangedPayload, WSSeatChangedPayload, WSMicroPhaseChangedPayload } from '../../types/ws'
import type { Message, DTStage, MicroPhaseId } from '../../types/models'

const NEXT_STAGE: Partial<Record<DTStage, DTStage>> = {
  discover: 'define',
  define: 'develop',
  develop: 'deliver',
}

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { currentProject, fetchProject } = useProjectStore()
  const { addMessage, unreadCount, incrementUnread, resetUnread } = useChatStore()
  const { seats, setSeats, updateSeat } = useSeatStore()
  const { currentStage, currentMicroPhase, setCurrentStage, setCurrentMicroPhase } = useStageStore()
  const { user } = useAuthStore()

  const [showAdvanceModal, setShowAdvanceModal] = useState(false)
  const [showPersonasPanel, setShowPersonasPanel] = useState(false)
  const [isAdvancing, setIsAdvancing] = useState(false)
  const [wsError, setWsError] = useState(false)
  const [activeTab, setActiveTab] = useState<'canvas' | 'chat'>('canvas')
  const [chatOpen, setChatOpen] = useState(true)
  const chatOpenRef = useRef(chatOpen)
  chatOpenRef.current = chatOpen

  const [chatWidth, setChatWidth] = useState(380)
  const isResizing = useRef(false)

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isResizing.current = true
    const startX = e.clientX
    const startWidth = chatWidth

    const onMove = (ev: MouseEvent) => {
      if (!isResizing.current) return
      const delta = startX - ev.clientX
      const next = Math.min(Math.max(startWidth + delta, 280), window.innerWidth * 0.6)
      setChatWidth(next)
    }
    const onUp = () => {
      isResizing.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [chatWidth])

  useEffect(() => {
    if (id) fetchProject(id)
  }, [id, fetchProject])

  useEffect(() => {
    if (currentProject) {
      if (currentProject.seats) setSeats(currentProject.seats)
      setCurrentStage(currentProject.current_stage)
      if (currentProject.current_micro_phase) {
        setCurrentMicroPhase(currentProject.current_micro_phase as MicroPhaseId)
      }
    }
  }, [currentProject, setSeats, setCurrentStage, setCurrentMicroPhase])

  // Fetch micro phase from /stage API as fallback (project detail may not include it)
  useEffect(() => {
    if (id && !currentMicroPhase) {
      getStage(id).then((stageInfo) => {
        if (stageInfo.current_micro_phase) {
          setCurrentMicroPhase(stageInfo.current_micro_phase as MicroPhaseId)
        }
      }).catch(() => { /* ignore — old backend may not support this */ })
    }
  }, [id, currentMicroPhase, setCurrentMicroPhase])

  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case 'chat_message': {
          const p = msg.payload as WSChatMessagePayload
          const message: Message = {
            id: p.id ?? crypto.randomUUID(),
            project_id: id!,
            sender_type: p.sender_type,
            sender_id: p.sender_id,
            sender_name: p.sender_name,
            content: p.content,
            stage: (p.stage ?? currentStage) as DTStage,
            created_at: p.timestamp,
          }
          addMessage(message)
          if (!chatOpenRef.current) incrementUnread()
          break
        }
        case 'typing_indicator': {
          const p = msg.payload as WSTypingPayload
          useChatStore.getState().setTyping(p.user_name, p.is_typing)
          break
        }
        case 'stage_changed': {
          const p = msg.payload as WSStageChangedPayload
          setCurrentStage(p.to)
          useProjectStore.getState().updateCurrentProject({ current_stage: p.to })
          break
        }
        case 'seat_changed': {
          const p = msg.payload as WSSeatChangedPayload
          updateSeat(p.seat_role, {
            occupant_type: p.current.occupant_type,
            user_id: p.current.user_id ?? null,
            agent_id: p.current.agent_id ?? null,
            display_name: p.current.display_name,
          })
          break
        }
        case 'micro_phase_changed': {
          const p = msg.payload as WSMicroPhaseChangedPayload
          useStageStore.getState().setCurrentMicroPhase(p.to as MicroPhaseId)
          break
        }
      }
    },
    [id, currentStage, addMessage, incrementUnread, setCurrentStage, updateSeat],
  )

  // In dev mode, connect directly to the backend (Vite's WS proxy is unreliable)
  const wsUrl = id
    ? import.meta.env.DEV
      ? `ws://localhost:8000/ws/project/${id}`
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/project/${id}`
    : ''

  const { status: wsStatus, send: sendWS } = useWebSocket(wsUrl, {
    onMessage: handleWSMessage,
    onClose: () => setWsError(true),
    onOpen: () => setWsError(false),
    enabled: !!id,
  })

  const myCurrentSeat = seats.find(
    (s) => s.occupant_type === 'human' && s.user_id === user?.id,
  )
  const isObserver = !myCurrentSeat
  const isSupervisor = myCurrentSeat?.seat_role === 'supervisor'
  const nextStage = NEXT_STAGE[currentStage]

  const handleAdvanceStage = async () => {
    if (!id || !nextStage) return
    setIsAdvancing(true)
    try {
      await advanceStage(id, { from: currentStage, to: nextStage })
      setCurrentStage(nextStage)
      setShowAdvanceModal(false)
    } catch {
      // ignore — WS will broadcast the change if it happens
    } finally {
      setIsAdvancing(false)
    }
  }

  const handleLeave = async () => {
    if (!id) return
    try {
      await leaveProject(id)
    } finally {
      navigate(`/projects/${id}/lobby`)
    }
  }

  const hasAccess = currentProject && user && (
    currentProject.creator_id === user.id ||
    currentProject.seats?.some(s => s.user_id === user.id)
  )

  useEffect(() => {
    if (currentProject && user && !hasAccess) {
      navigate(`/projects/${id}/lobby`, { replace: true })
    }
  }, [currentProject, user, hasAccess, id, navigate])

  if (!currentProject) {
    return <Loading fullScreen text="載入工作區…" />
  }

  if (!hasAccess) {
    return <Loading fullScreen text="正在跳轉至大廳…" />
  }

  const showBanner = wsStatus === 'disconnected' || wsStatus === 'failed' || wsError

  return (
    <div className="flex h-screen flex-col bg-bg overflow-hidden">
      {/* WS disconnect banner */}
      {showBanner && (
        <ConnectionBanner status={wsStatus === 'failed' ? 'failed' : 'disconnected'} />
      )}

      {/* DT Progress bar */}
      <header className="flex-shrink-0 border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-4">
          <span className="text-sm text-text-muted whitespace-nowrap">{currentProject.name}</span>
          <div className="flex-1 min-w-0 flex justify-center">
            <DoubleDiamondProgress currentStage={currentStage} currentMicroPhase={currentMicroPhase ?? undefined} />
          </div>
        </div>
      </header>

      {/* Main content area */}
      <div className="relative flex-1 overflow-hidden">
        {/* Mobile: tabs */}
        <div className="flex md:hidden flex-col h-full overflow-hidden">
          <div className="flex border-b border-border bg-surface">
            <button
              className={cn(
                'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'canvas'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted',
              )}
              onClick={() => setActiveTab('canvas')}
            >
              白板
            </button>
            <button
              className={cn(
                'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'chat'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted',
              )}
              onClick={() => setActiveTab('chat')}
            >
              聊天室
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {activeTab === 'canvas' ? (
              <CanvasPanel projectId={id!} currentStage={currentStage} />
            ) : (
              <ChatPanel projectId={id!} sendWS={sendWS} />
            )}
          </div>
        </div>

        {/* Tablet/Desktop: fullwidth canvas + floating chat */}
        <div className="hidden md:block h-full relative overflow-hidden">
          <CanvasPanel projectId={id!} currentStage={currentStage} />

          {/* Floating chat panel */}
          <div
            className={cn(
              'absolute top-3 right-3 bottom-3 z-30',
              'overflow-hidden rounded-xl shadow-xl border border-border',
              'transition-transform duration-300 ease-out',
              'motion-reduce:transition-none',
              chatOpen ? 'translate-x-0' : 'translate-x-[calc(100%+12px)]',
            )}
            style={{ width: chatWidth }}
          >
            {/* Resize handle */}
            <div
              className="absolute left-0 top-0 bottom-0 z-10 w-1.5 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors"
              onMouseDown={handleResizeStart}
            />
            <ChatPanel projectId={id!} sendWS={sendWS} disabled={isObserver} onClose={() => setChatOpen(false)} />
          </div>

          {/* Toggle button: visible when chat is collapsed */}
          <button
            className={cn(
              'absolute bottom-6 right-4 z-40',
              'flex items-center gap-2 rounded-full px-4 py-2.5',
              'bg-accent text-white shadow-lg',
              'hover:bg-accent/90 cursor-pointer',
              'transition-all duration-300 ease-out',
              'motion-reduce:transition-none',
              chatOpen
                ? 'opacity-0 pointer-events-none scale-90'
                : 'opacity-100 scale-100',
            )}
            onClick={() => { setChatOpen(true); resetUnread() }}
            aria-label="開啟聊天室"
          >
            <MessageCircle size={18} />
            <span className="text-sm font-medium">聊天室</span>
            {unreadCount > 0 && (
              <span className="flex items-center justify-center min-w-[1.25rem] h-5 rounded-full bg-error px-1.5 text-xs font-bold text-white">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Seat status bar */}
      <footer className="flex-shrink-0 border-t border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-2 overflow-x-auto">
          <SeatBar seats={seats} currentUserId={user?.id} />

          <div className="ml-auto flex items-center gap-2">
            {currentProject?.creator_id === user?.id && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPersonasPanel(true)}
              >
                <Users size={14} />
                AI 隊友
              </Button>
            )}
            {isSupervisor && nextStage && (
              <Button
                size="sm"
                onClick={() => setShowAdvanceModal(true)}
              >
                推進到 {nextStage}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={handleLeave}>
              離開
            </Button>
          </div>
        </div>
      </footer>

      {/* Advance stage confirmation modal */}
      <Modal
        isOpen={showAdvanceModal}
        onClose={() => setShowAdvanceModal(false)}
        title="推進階段確認"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">
            確定要將專案推進到{' '}
            <span className="font-semibold text-primary">{nextStage}</span>{' '}
            階段嗎？前一階段的白板產出會自動儲存快照。
          </p>
          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => setShowAdvanceModal(false)}
            >
              取消
            </Button>
            <Button
              className="flex-1"
              isLoading={isAdvancing}
              onClick={handleAdvanceStage}
            >
              確認推進
            </Button>
          </div>
        </div>
      </Modal>

      {/* AI persona management (creator only) */}
      {showPersonasPanel && currentProject && (
        <ProjectPersonasPanel
          isOpen={showPersonasPanel}
          projectId={currentProject.id}
          seats={seats}
          onClose={() => setShowPersonasPanel(false)}
          onUpdated={(updatedSeat) => updateSeat(updatedSeat.seat_role, updatedSeat)}
        />
      )}
    </div>
  )
}
