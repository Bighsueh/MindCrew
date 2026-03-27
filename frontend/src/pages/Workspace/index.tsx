import { useEffect, useCallback, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useChatStore } from '../../stores/chatStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useAuthStore } from '../../stores/authStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { advanceStage, leaveProject } from '../../services/projectService'
import { DTProgressBar } from '../../components/dt-progress/DTProgressBar'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { CanvasPanel } from '../../components/canvas/CanvasPanel'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Loading } from '../../components/common/Loading'
import type { WSMessage, WSChatMessagePayload, WSTypingPayload, WSStageChangedPayload, WSSeatChangedPayload } from '../../types/ws'
import type { Message, DTStage, SeatRole } from '../../types/models'

const SEAT_ROLE_LABELS: Record<SeatRole, string> = {
  supervisor: '指導者',
  crew_1: '成員 1',
  crew_2: '成員 2',
  crew_3: '成員 3',
  crew_4: '成員 4',
}

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

  const wsUrl = id ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/project/${id}` : ''

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

  // Redirect to lobby if user is not creator and has no seat
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

  return (
    <div className="flex h-screen flex-col bg-gray-100 overflow-hidden">
      {/* WS disconnect banner */}
      {(wsStatus === 'disconnected' || wsStatus === 'failed' || wsError) && (
        <div
          className={[
            'z-50 px-4 py-2 text-center text-sm font-medium text-white',
            wsStatus === 'failed' ? 'bg-red-600' : 'bg-yellow-500',
          ].join(' ')}
        >
          {wsStatus === 'failed'
            ? '⚠️ 無法連線，請檢查網路後重新整理頁面。'
            : '🔄 連線中斷，嘗試重新連線…'}
        </div>
      )}

      {/* DT Progress bar */}
      <header className="flex-shrink-0 border-b border-gray-200 bg-white px-4 py-2">
        <div className="flex items-center gap-4">
          <Link to="/projects" className="text-sm text-gray-500 hover:text-gray-700 whitespace-nowrap">
            ← 離開
          </Link>
          <div className="flex-1 min-w-0">
            <DTProgressBar currentStage={currentStage} />
          </div>
          <span className="hidden lg:block text-sm font-medium text-gray-700 whitespace-nowrap truncate max-w-40">
            {currentProject.name}
          </span>
        </div>
      </header>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas + Chat layout */}

        {/* Mobile: tabs */}
        <div className="flex lg:hidden flex-col flex-1 overflow-hidden">
          {/* Tab bar */}
          <div className="flex border-b border-gray-200 bg-white">
            <button
              className={[
                'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'canvas'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500',
              ].join(' ')}
              onClick={() => setActiveTab('canvas')}
            >
              📋 白板
            </button>
            <button
              className={[
                'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'chat'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500',
              ].join(' ')}
              onClick={() => setActiveTab('chat')}
            >
              💬 聊天室
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
          {/* Canvas: 60% */}
          <div className="w-3/5 p-3">
            <CanvasPanel projectId={id!} />
          </div>
          {/* Chat: 40% */}
          <div className="w-2/5 border-l border-gray-200 bg-white overflow-hidden">
            <ChatPanel projectId={id!} sendWS={sendWS} />
          </div>
        </div>
      </div>

      {/* Seat status bar */}
      <footer className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2 overflow-x-auto">
          {seats.map((seat) => (
            <div
              key={seat.id}
              className={[
                'flex flex-shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
                seat.occupant_type === 'human'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-500',
                seat.user_id === user?.id ? 'ring-2 ring-blue-500' : '',
              ].join(' ')}
            >
              <span>{seat.occupant_type === 'human' ? '👤' : '🤖'}</span>
              <span>{seat.display_name ?? (seat.occupant_type === 'human' ? '人類' : `AI ${SEAT_ROLE_LABELS[seat.seat_role]}`)}</span>
            </div>
          ))}

          <div className="ml-auto flex items-center gap-2">
            {isSupervisor && nextStage && (
              <Button
                size="sm"
                onClick={() => setShowAdvanceModal(true)}
              >
                推進到 {nextStage} ▶
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
          <p className="text-sm text-gray-600">
            確定要將專案推進到{' '}
            <span className="font-semibold text-blue-600">{nextStage}</span>{' '}
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
