import { useCallback, useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useProjectStore } from '../../stores/projectStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useTimerStore } from '../../stores/timerStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useAuthStore } from '../../stores/authStore'
import { isPersonalChatId } from '../../lib/chatId'
import { macroStageFromSubPhase } from '../../lib/subPhaseStage'
import { resyncCriticalSurface } from '../../hooks/useReconnectResync'
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
  WSCuePayload,
  WSTurnPolicyChangedPayload,
  WSTurnStatePayload,
  WSCueTimeoutPayload,
  WSCueAbandonedPayload,
  WSWaitingForHumanPayload,
  WSInputBouncedPayload,
  WSUserTaskPayload,
  WSNoteHighlightPayload,
  WSAgentTypingPayload,
  WSRoomPausedPayload,
} from '../../types/ws'
import type { Message, DTStage, MicroPhaseId } from '../../types/models'
import type { ChatKind } from '../../stores/chatStore'
import { dispatchCueNotification } from '../../hooks/useCueNotification'
import { useCueStore } from '../../stores/cueStore'
import { useHumanGateStore } from '../../stores/humanGateStore'
import { useNoteHighlightStore } from '../../stores/noteHighlightStore'

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
          // F1/F3：人類在群組發話 → 若該席位是 active cue → clear cue store
          // (對齊 backend chat_ws.notify_human_speak_in_group：人類發話視為回應)
          if (
            p.sender_type === 'human' &&
            kind === 'group'
          ) {
            const cur = useCueStore.getState().status
            if (cur.kind !== 'idle') {
              // 透過 seat lookup 比對；簡化：human 任何人發話都清掉 active cue
              // （單一人類規則 — 一個專案只會有一個 human seat）
              useCueStore.getState().clear()
            }
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
        case 'agent_typing': {
          // D2/WP9 #9：AI 發話/白板動作前置指示。後端只在群組 channel 發
          // （payload 無 chat_id）→ 一律 'group'；個人 channel 不顯示。
          const p = msg.payload as WSAgentTypingPayload
          useChatStore
            .getState()
            .setAgentTyping('group', p.seat_id, p.display_name, p.kind, p.state === 'start')
          break
        }
        case 'stage_changed': {
          const p = msg.payload as WSStageChangedPayload
          useStageStore.getState().setCurrentStage(p.to)
          useProjectStore.getState().updateCurrentProject({ current_stage: p.to })
          // ：macro stage 切換時跑 driver.js spotlight 介紹新階段 + timer 重設
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
          // 後端 MicroPhaseChangedEvent 送的是 to_phase（非 to）；過去 FE 讀 p.to 永遠 undefined
          // → micro 徽章不會 live 更新。對齊欄位名後修復。
          useStageStore.getState().setCurrentMicroPhase(p.to_phase as MicroPhaseId)
          // ：micro_phase 切換時跑 driver.js spotlight 介紹新 sub-step + timer 重設。
          // 從 stageStore 取目前 stage（macro 不變的情況下沿用既有 store value）。
          const currentStage = useStageStore.getState().currentStage
          triggerPhaseAdvanceTour({
            toStage: currentStage,
            toMicroPhase: p.to_phase as MicroPhaseId,
          })
          break
        }
        // ：timer 三類事件全員可見。
        case 'timer_state': {
          const p = msg.payload as WSTimerStatePayload
          useTimerStore.getState().setSnapshot({
            current_sub_phase: p.current_sub_phase,
            current_sub_phase_label: p.current_sub_phase_label ?? p.current_sub_phase,
            budget_seconds: p.budget_seconds,
            used_seconds: p.used_seconds,
            paused: p.paused,
            used_pct: p.used_pct,
            available: true,
            // spec 16 v2.0 §4.5：本關上限/已用（舊後端缺欄位時退回既有同義值）＋暖場目標。
            sub_phase_budget_seconds: p.sub_phase_budget_seconds ?? p.budget_seconds,
            sub_phase_used_seconds: p.sub_phase_used_seconds ?? p.used_seconds,
            warmup_goal: p.warmup_goal ?? null,
            warmup_soft_seconds: p.warmup_soft_seconds ?? null,
          })
          // 兜底校正 macro stage：stage_changed 為一次性事件、Redis 無 replay，漏接會卡死；
          // timer_state 每 ~10s 必達，由 current_sub_phase 推導 macro stage 校正（不觸發 tour）。
          const derivedStage = macroStageFromSubPhase(p.current_sub_phase)
          if (derivedStage && derivedStage !== useStageStore.getState().currentStage) {
            useStageStore.getState().setCurrentStage(derivedStage)
          }
          // Phase 42 A3：換關 → 清掉舊關的任務 banner 與等待列（Flow 12 生命週期）。
          useHumanGateStore.getState().onSubPhaseChange(p.current_sub_phase)
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
        // Phase 28 — Turn-Taking Controller events
        case 'turn_policy_changed': {
          const p = msg.payload as WSTurnPolicyChangedPayload
          useProjectStore.getState().updateCurrentProject({ turn_policy: p.policy })
          // 政策切換通常伴隨 turn_state 重置 (避免前端 isMyTurn 殘留)
          useProjectStore.getState().setTurnState(null)
          break
        }
        case 'cue': {
          const p = msg.payload as WSCuePayload
          // 透過 CustomEvent 廣播給 ChatPanel banner / ChatInput 邊框閃爍訂閱端
          dispatchCueNotification({
            target_seat_role: p.target_seat_id,
            from_seat_role: p.from_seat_id,
            timestamp: p.timestamp,
          })
          // F1/F3：標記 active cue（給 SeatChip 觀察者邊框 + 持久 banner 用）
          useCueStore.getState().setPending(p.target_seat_id)
          break
        }
        case 'turn_state': {
          const p = msg.payload as WSTurnStatePayload
          useProjectStore.getState().setTurnState({
            policy: p.policy,
            next_speaker: p.next_speaker,
            allowed_actions: p.allowed_actions,
          })
          // Phase 42 補正 R4（A-P2，spec 06 v4.28）：只認回合鎖來源清「等待真人」列。
          // 修復前任何 turn_state（政策層也發）都清——凍結期間政策層事件會提前清列，
          // 且 waiting_for_human 同回合 NX 去重不重發 → 等待列整回合失蹤。
          if (p.source === 'round_lock') {
            useHumanGateStore.getState().clearWaiting()
          }
          break
        }
        case 'cue_timeout': {
          const p = msg.payload as WSCueTimeoutPayload
          useCueStore.getState().setTimedOut(
            p.target_seat_role,
            p.retry_count,
            p.max_retries,
            p.will_retry,
          )
          break
        }
        case 'cue_abandoned': {
          const p = msg.payload as WSCueAbandonedPayload
          useCueStore.getState().setAbandoned(p.target_seat_role, p.total_attempts)
          // 30 秒後自動 fade 回 idle
          window.setTimeout(() => {
            const cur = useCueStore.getState().status
            if (cur.kind === 'abandoned' && cur.seat === p.target_seat_role) {
              useCueStore.getState().clear()
            }
          }, 30000)
          break
        }
        // Phase 42 A2/A3 — 回合鎖 + 真人不迷失 UX（spec 06 §3.1 / 05 Flow 4・Flow 12）
        case 'waiting_for_human': {
          const p = msg.payload as WSWaitingForHumanPayload
          useHumanGateStore.getState().setWaiting(p)
          break
        }
        case 'input_bounced': {
          const p = msg.payload as WSInputBouncedPayload
          // 退回提示只給被退回的本人（旁觀者／老師不彈 toast）。
          const myId = useAuthStore.getState().user?.id
          if (myId && p.user_id === myId) {
            useHumanGateStore.getState().showBounce(p.reason_zh, p.hint_zh)
          }
          break
        }
        case 'user_task': {
          const p = msg.payload as WSUserTaskPayload
          useHumanGateStore.getState().setTask(p)
          // 任務相關便條 → 連動高亮（同 note_highlight 機制，預設 12s）。
          if (p.task_text && p.anchor_note_ids && p.anchor_note_ids.length > 0) {
            useNoteHighlightStore.getState().highlight(p.anchor_note_ids, 12)
          }
          break
        }
        case 'note_highlight': {
          const p = msg.payload as WSNoteHighlightPayload
          useNoteHighlightStore.getState().highlight(p.note_ids, p.ttl)
          break
        }
        // Phase 42 D5 — LLM fail-stop 全房暫停／恢復（spec 20 §13.3/§13.4）
        case 'room_paused': {
          const p = msg.payload as WSRoomPausedPayload
          useProjectStore.getState().setRoomPaused(p.reason)
          break
        }
        case 'room_resumed': {
          useProjectStore.getState().setRoomResumed()
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
    onOpen: () => {
      setWsError(false)
      // 自癒：Redis pub/sub 無 replay，重連空窗漏接的一次性 stage_changed / AI 聊天 / seat_changed
      // 會讓 UI 永久卡舊狀態（盲測 2026-06-09 R5：後端已 define、學生卻看不到、被迫整頁重整）。
      // 每次 (重)連線全量對齊 server truth（stage+micro / group+personal 聊天 / 席位）；
      // 只設 store、不觸發 spotlight tour（避免重連洗版）。
      if (projectId) {
        void resyncCriticalSurface({
          projectId,
          currentUserId: useAuthStore.getState().user?.id,
        })
      }
    },
    enabled: !!projectId,
  })

  return { wsStatus: status, sendWS: send, wsError }
}
