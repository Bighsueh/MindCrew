import { useEffect, useCallback, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useChatStore } from '../../stores/chatStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useAuthStore } from '../../stores/authStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { advanceStage, leaveProject } from '../../services/projectService'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import { ConnectionBanner } from '../../components/workspace/ConnectionBanner'
import { SeatBar } from '../../components/workspace/SeatBar'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { CanvasPanel } from '../../components/canvas/CanvasPanel'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import { cn } from '../../lib/utils'
import type { WSMessage, WSChatMessagePayload, WSTypingPayload, WSStageChangedPayload, WSSeatChangedPayload } from '../../types/ws'
import type { Message, DTStage } from '../../types/models'

const NEXT_STAGE: Partial<Record<DTStage, DTStage>> = {
  discover: 'define',
  define: 'develop',
  develop: 'deliver',
}

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { currentProject, fetchProject } = useProjectStore()
  const { addMessage } = useChatStore()
  const { seats, setSeats, updateSeat } = useSeatStore()
  const { currentStage, setCurrentStage } = useStageStore()
  const { user } = useAuthStore()

  const [showAdvanceModal, setShowAdvanceModal] = useState(false)
  const [isAdvancing, setIsAdvancing] = useState(false)
  const [wsError, setWsError] = useState(false)
  const [activeTab, setActiveTab] = useState<'canvas' | 'chat'>('canvas')

  useEffect(() => {
    if (id) fetchProject(id)
  }, [id, fetchProject])

  useEffect(() => {
    if (currentProject) {
      if (currentProject.seats) setSeats(currentProject.seats)
      setCurrentStage(currentProject.current_stage)
    }
  }, [currentProject, setSeats, setCurrentStage])

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
      }
    },
    [id, currentStage, addMessage, setCurrentStage, updateSeat],
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
            <DoubleDiamondProgress currentStage={currentStage} />
          </div>
        </div>
      </header>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Mobile: tabs */}
        <div className="flex lg:hidden flex-col flex-1 overflow-hidden">
          <div className="flex border-b border-border bg-surface">
            <button
              className={cn(
                'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'canvas'
                  ? 'border-primary text-primary'
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
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-muted',
              )}
              onClick={() => setActiveTab('chat')}
            >
              聊天室
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {activeTab === 'canvas' ? (
              <CanvasPanel projectId={id!} />
            ) : (
              <ChatPanel projectId={id!} sendWS={sendWS} />
            )}
          </div>
        </div>

        {/* Desktop: side-by-side */}
        <div className="hidden lg:flex flex-1 overflow-hidden gap-0">
          <div className="w-3/5 p-3">
            <CanvasPanel projectId={id!} />
          </div>
          <div className="w-2/5 border-l border-border bg-surface overflow-hidden">
            <ChatPanel projectId={id!} sendWS={sendWS} />
          </div>
        </div>
      </div>

      {/* Seat status bar */}
      <footer className="flex-shrink-0 border-t border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-2 overflow-x-auto">
          <SeatBar seats={seats} currentUserId={user?.id} />

          <div className="ml-auto flex items-center gap-2">
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
    </div>
  )
}
