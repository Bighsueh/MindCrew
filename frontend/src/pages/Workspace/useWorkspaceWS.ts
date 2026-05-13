import { useCallback, useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useProjectStore } from '../../stores/projectStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useTimerStore } from '../../stores/timerStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { isPersonalChatId } from '../../lib/chatId'
import { triggerPhaseAdvanceTour } from '../../components/onboarding/phaseAdvanceTour'
import type {
  WSMessage,
  WSChatMessagePayload,
  WSTypingPayload,
  WSStageChangedPayload,
  WSSeatChangedPayload,
  WSMicroPhaseChangedPayload,
  WSTimerStatePayload,
  WSTimerWarningPayload,
  WSTimerTimeoutPayload,
} from '../../types/ws'
import type { Message, DTStage, MicroPhaseId } from '../../types/models'
import type { ChatKind } from '../../stores/chatStore'

interface UseWorkspaceWSOptions {
  projectId: string | undefined
  currentStage: DTStage
  /** 當前哪個 chat channel 在前景；用來判斷是否要遞增 unread。 */
  activeChannel: ChatKind | null
  /** chat_message 抵達時觸發；父層用來更新 recentSpeaker 與 seatPreviews。 */
  onChatMessage?: (kind: ChatKind, message: Message) => void
}

/**
 * 將 Workspace 內所有 WebSocket handler 收斂到單一 hook。
 *
 * 核心改動：chat_message / typing_indicator 依 payload.chat_id 路由到對應 channel
 * （group / personal），確保個人助理訊息不會混進群組頻道。
 */
export function useWorkspaceWS({
  projectId,
  currentStage,
  activeChannel,
  onChatMessage,
}: UseWorkspaceWSOptions) {
  const [wsError, setWsError] = useState(false)

  // ── chat_id → kind 路由 ──
  const routeKind = useCallback((chatId: string | undefined): ChatKind => {
    return isPersonalChatId(chatId) ? 'personal' : 'group'
  }, [])

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case 'chat_message': {
          const p = msg.payload as WSChatMessagePayload
          const kind = routeKind(p.chat_id)
          const message: Message = {
            id: p.id ?? crypto.randomUUID(),
            project_id: projectId ?? '',
            sender_type: p.sender_type,
            sender_id: p.sender_id,
            sender_name: p.sender_name,
            content: p.content,
            stage: (p.stage ?? currentStage) as DTStage,
            created_at: p.timestamp,
          }
          const chat = useChatStore.getState()
          chat.addMessage(kind, message)
          // 訊息來自非當前 active channel → 累計 unread
          if (activeChannel !== kind) {
            chat.incrementUnread(kind)
          }
          onChatMessage?.(kind, message)
          break
        }
        case 'typing_indicator': {
          const p = msg.payload as WSTypingPayload
          // backend 目前未在 typing payload 帶 chat_id → 預設視為 group。
          // 若未來補上 chat_id 欄位，可在此擴充判斷。
          useChatStore.getState().setTyping('group', p.user_name, p.user_name, p.is_typing)
          break
        }
        case 'stage_changed': {
          const p = msg.payload as WSStageChangedPayload
          useStageStore.getState().setCurrentStage(p.to)
          useProjectStore.getState().updateCurrentProject({ current_stage: p.to })
          // specs/16-timer-system.md：macro stage 切換時跑 driver.js spotlight 介紹新階段 + timer 重設
          triggerPhaseAdvanceTour({ toStage: p.to })
          break
        }
        case 'seat_changed': {
          const p = msg.payload as WSSeatChangedPayload
          useSeatStore.getState().updateSeat(p.seat_role, {
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
          // specs/16-timer-system.md：micro_phase 切換時跑 driver.js spotlight 介紹新 sub-step + timer 重設。
          // 從 stageStore 取目前 stage（macro 不變的情況下沿用既有 store value）。
          const currentStage = useStageStore.getState().currentStage
          triggerPhaseAdvanceTour({
            toStage: currentStage,
            toMicroPhase: p.to as MicroPhaseId,
          })
          break
        }
        // specs/16-timer-system.md §6.5.3：timer 三類事件全員可見。
        case 'timer_state': {
          const p = msg.payload as WSTimerStatePayload
          useTimerStore.getState().setSnapshot({
            current_sub_phase: p.current_sub_phase,
            budget_seconds: p.budget_seconds,
            used_seconds: p.used_seconds,
            paused: p.paused,
            used_pct: p.used_pct,
            available: true,
          })
          break
        }
        case 'timer_warning': {
          const p = msg.payload as WSTimerWarningPayload
          // 警告事件不變更 store snapshot（state 事件會帶最新值）；
          // 留 console hint 給開發者觀察，未來可串 toast。
          if (import.meta.env.DEV) {
            console.info('[timer_warning]', p.threshold_pct, '%', p.current_sub_phase)
          }
          break
        }
        case 'timer_timeout': {
          const p = msg.payload as WSTimerTimeoutPayload
          if (import.meta.env.DEV) {
            console.info('[timer_timeout]', p.current_sub_phase)
          }
          break
        }
      }
    },
    [projectId, currentStage, activeChannel, routeKind, onChatMessage],
  )

  // dev 直連 backend（預設 :8000，可由 VITE_WS_URL 環境變數覆寫）；prod 走同 host 反向代理。
  const wsUrl = projectId
    ? import.meta.env.DEV
      ? `${import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'}/ws/project/${projectId}`
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/project/${projectId}`
    : ''

  const { status, send } = useWebSocket(wsUrl, {
    onMessage: handleMessage,
    onClose: () => setWsError(true),
    onOpen: () => setWsError(false),
    enabled: !!projectId,
  })

  return { wsStatus: status, sendWS: send, wsError }
}
