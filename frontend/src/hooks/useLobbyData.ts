import { useEffect, useState, useCallback, useRef } from 'react'
import { useProjectStore } from '../stores/projectStore'
import { useSeatStore } from '../stores/seatStore'
import { useStageStore } from '../stores/stageStore'
import { useAuthStore } from '../stores/authStore'
import { useWebSocket } from './useWebSocket'
import {
  getMessages,
  getStage,
  getStageHistory,
  getCanvasState,
} from '../services/projectService'
import type { Message, StageInfo, StageHistoryEntry, CanvasStateResponse } from '../types/models'
import type {
  WSMessage,
  WSChatMessagePayload,
  WSTypingPayload,
  WSSeatChangedPayload,
  WSStageChangedPayload,
} from '../types/ws'

const MAX_PREVIEW_MESSAGES = 5

interface TypingUser {
  name: string
  isTyping: boolean
}

interface LobbyData {
  recentMessages: Message[]
  typingUsers: Map<string, TypingUser>
  stageInfo: StageInfo | null
  stageHistory: StageHistoryEntry[]
  canvasState: CanvasStateResponse | null
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'failed'
  isLoading: boolean
  messageCount: number
}

export function useLobbyData(projectId: string | undefined): LobbyData {
  const { currentProject, fetchProject, isLoading: projectLoading } = useProjectStore()
  const { seats, setSeats, updateSeat } = useSeatStore()
  const { setCurrentStage } = useStageStore()
  const { user } = useAuthStore()

  const [recentMessages, setRecentMessages] = useState<Message[]>([])
  const [typingUsers, setTypingUsers] = useState<Map<string, TypingUser>>(new Map())
  const [stageInfo, setStageInfo] = useState<StageInfo | null>(null)
  const [stageHistory, setStageHistory] = useState<StageHistoryEntry[]>([])
  const [canvasState, setCanvasState] = useState<CanvasStateResponse | null>(null)
  const [isDataLoading, setIsDataLoading] = useState(true)
  const [messageCount, setMessageCount] = useState(0)
  const mountedRef = useRef(true)

  // Fetch project data on mount
  useEffect(() => {
    if (!projectId) return
    fetchProject(projectId)
  }, [projectId, fetchProject])

  // Sync seats from project
  useEffect(() => {
    if (currentProject?.seats) {
      setSeats(currentProject.seats)
    }
  }, [currentProject?.seats, setSeats])

  // Fetch additional data (messages, stage, canvas)
  useEffect(() => {
    if (!projectId) return
    mountedRef.current = true

    const loadData = async () => {
      setIsDataLoading(true)
      try {
        const [messagesRes, stageRes, historyRes, canvasRes] = await Promise.allSettled([
          getMessages(projectId, { limit: MAX_PREVIEW_MESSAGES }),
          getStage(projectId),
          getStageHistory(projectId),
          getCanvasState(projectId),
        ])

        if (!mountedRef.current) return

        if (messagesRes.status === 'fulfilled') {
          setRecentMessages(messagesRes.value.messages)
          setMessageCount(messagesRes.value.messages.length)
        }
        if (stageRes.status === 'fulfilled') {
          setStageInfo(stageRes.value)
        }
        if (historyRes.status === 'fulfilled') {
          setStageHistory(historyRes.value)
        }
        if (canvasRes.status === 'fulfilled') {
          setCanvasState(canvasRes.value)
        }
      } finally {
        if (mountedRef.current) setIsDataLoading(false)
      }
    }

    loadData()
    return () => { mountedRef.current = false }
  }, [projectId])

  // WS message handler
  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case 'chat_message': {
          const payload = msg.payload as WSChatMessagePayload
          const newMsg: Message = {
            id: payload.id ?? crypto.randomUUID(),
            project_id: projectId ?? '',
            sender_type: payload.sender_type,
            sender_id: payload.sender_id,
            sender_name: payload.sender_name,
            content: payload.content,
            stage: payload.stage ?? stageInfo?.current_stage ?? 'discover',
            created_at: payload.timestamp,
          }
          setRecentMessages((prev) => [...prev, newMsg].slice(-MAX_PREVIEW_MESSAGES))
          setMessageCount((prev) => prev + 1)
          break
        }
        case 'typing_indicator': {
          const payload = msg.payload as WSTypingPayload
          setTypingUsers((prev) => {
            const next = new Map(prev)
            if (payload.is_typing) {
              next.set(payload.user_name, { name: payload.user_name, isTyping: true })
            } else {
              next.delete(payload.user_name)
            }
            return next
          })
          break
        }
        case 'seat_changed': {
          const payload = msg.payload as WSSeatChangedPayload
          updateSeat(payload.seat_role, {
            occupant_type: payload.current.occupant_type,
            display_name: payload.current.display_name,
            user_id: payload.current.user_id ?? null,
            agent_id: payload.current.agent_id ?? null,
          })
          break
        }
        case 'stage_changed': {
          const payload = msg.payload as WSStageChangedPayload
          setCurrentStage(payload.to)
          setStageInfo((prev) =>
            prev ? { ...prev, current_stage: payload.to, started_at: payload.timestamp, duration_seconds: 0 } : prev,
          )
          break
        }
      }
    },
    [projectId, stageInfo?.current_stage, updateSeat, setCurrentStage],
  )

  // Determine if user can connect to WS (creator or has a seat)
  const canConnectWS =
    !!projectId &&
    !!user &&
    (currentProject?.creator_id === user.id ||
      seats.some((s) => s.occupant_type === 'human' && s.user_id === user.id))

  const wsUrl = projectId
    ? import.meta.env.DEV
      ? `${import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'}/ws/project/${projectId}`
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/project/${projectId}`
    : ''

  const { status: wsStatus } = useWebSocket(wsUrl, {
    onMessage: handleWSMessage,
    enabled: canConnectWS,
  })

  return {
    recentMessages,
    typingUsers,
    stageInfo,
    stageHistory,
    canvasState,
    wsStatus,
    isLoading: projectLoading || isDataLoading,
    messageCount,
  }
}
