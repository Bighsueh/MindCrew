import { useChatStore } from '../stores/chatStore'
import { useHumanGateStore } from '../stores/humanGateStore'
import { useSeatStore } from '../stores/seatStore'
import { useStageStore } from '../stores/stageStore'
import { getHumanGate, getSeats, getStage } from '../services/projectService'
import type { MicroPhaseId } from '../types/models'
import type { UserTaskActionKind, WSWaitingForHumanPayload } from '../types/ws'

interface ResyncArgs {
  projectId: string
  /** 有值才一併重抓個人助理(personal)歷史。 */
  currentUserId?: string
}

/**
 * 重連自癒：把客戶端關鍵狀態全量對齊 server truth。每次 WS (重)連線都呼叫。
 *
 * 為什麼需要：`event_bus` 是 Redis pub/sub、無 replay——WS 一斷，斷線空窗內發布的
 * `stage_changed` / AI 聊天 / `seat_changed` 就永久遺失。前端若只靠 WS 推送，會卡在舊狀態
 * 直到使用者整頁重整（盲測 2026-06-09 R5：後端已 define、學生卻看不到、被迫重整）。
 * 重連後以權威 REST 快照重抓即可**冪等收斂**，且涵蓋「重試耗盡無 socket」的終局
 * （快照重抓嚴格優於事件重播）。
 *
 * 鐵律：此路徑**只設 store、絕不呼叫 `triggerPhaseAdvanceTour`**——spotlight 只由 live WS
 * handler 觸發，否則每次重連都會洗版 spotlight。set 前先比較，避免無謂 re-render。
 *
 * `Promise.allSettled`：任一面向失敗不阻斷其餘（部分收斂優於全無）。
 */
export async function resyncCriticalSurface({
  projectId,
  currentUserId,
}: ResyncArgs): Promise<void> {
  const chat = useChatStore.getState()
  await Promise.allSettled([
    getStage(projectId).then((info) => {
      const s = useStageStore.getState()
      if (info.current_stage !== s.currentStage) {
        s.setCurrentStage(info.current_stage)
      }
      if (
        info.current_micro_phase &&
        info.current_micro_phase !== s.currentMicroPhase
      ) {
        s.setCurrentMicroPhase(info.current_micro_phase as MicroPhaseId)
      }
    }),
    // loadHistory 已有 in-flight guard + merge-preserve（保住 pending/較新本地訊息），冪等。
    chat.loadHistory(projectId, 'group'),
    currentUserId
      ? chat.loadHistory(projectId, 'personal', currentUserId)
      : Promise.resolve(),
    getSeats(projectId).then((seats) => {
      // 全量快照 → 用 setSeats（非 per-field updateSeat）；快照本就完整、不會洗掉名字。
      if (seats.length) useSeatStore.getState().setSeats(seats)
    }),
    // Phase 42 補正 R4（A-P1，spec 05 Flow 12／06 v4.28）：TaskBanner／WaitingIndicator
    // 水合——原本只靠 live WS 事件存在，刷新／重連／休眠喚醒後全部消失，且
    // waiting_for_human 同回合 NX 去重永不重發。快照重建，冪等收斂。
    getHumanGate(projectId).then((snap) => {
      const gate = useHumanGateStore.getState()
      if (snap.user_task && snap.user_task.task_text) {
        gate.setTask({
          project_id: projectId,
          task_text: snap.user_task.task_text,
          sub_phase: snap.user_task.sub_phase,
          action_kind: snap.user_task.action_kind as UserTaskActionKind,
          anchor_note_ids: null,
          timestamp: '',
        })
      }
      if (snap.waiting) {
        gate.setWaiting({
          project_id: projectId,
          sub_phase: snap.waiting.sub_phase,
          round: snap.waiting.round,
          required: snap.waiting.required as WSWaitingForHumanPayload['required'],
          target_user_id: '',
          timestamp: '',
        } as WSWaitingForHumanPayload)
      } else if (useHumanGateStore.getState().waiting) {
        // 快照說沒在等 → 清殘留（如斷線空窗中已解鎖、turn_state 漏接）。
        gate.clearWaiting()
      }
    }),
  ])
}
