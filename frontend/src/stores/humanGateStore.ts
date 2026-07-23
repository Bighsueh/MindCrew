import { create } from 'zustand'
import type {
  UserTaskActionKind,
  WSUserTaskPayload,
  WSWaitingForHumanPayload,
} from '../types/ws'

/**
 * Phase 42 A3（WP5/WP7）：回合鎖等待狀態＋「你的任務」釘住 banner＋輸入退回提示。
 *
 * 三組同源 UI 狀態收在一個 store（都由回合鎖／組長任務事件驅動）：
 * - `waiting`：`waiting_for_human` 事件 → 「等待真人輸入中…」狀態列；
 *   `turn_state` 事件（解鎖／推進後端必發）→ 清除。
 * - `task`：`user_task` 事件 → 釘住 banner；後到覆蓋、task_text=null 清除、
 *   換關（sub_phase 變更）清除（spec 05 Flow 12 生命週期）。
 * - `bounce`：`input_bounced` 事件 → 退回 toast（顯示後由元件自動清除）。
 */

export interface WaitingState {
  subPhase: string
  round: number
  required: WSWaitingForHumanPayload['required']
  targetUserId: string
}

export interface TaskState {
  taskText: string
  subPhase: string
  actionKind: UserTaskActionKind
  anchorNoteIds: string[]
}

export interface BounceState {
  reasonZh: string
  hintZh: string
  /** 單調遞增 key——同文案連續退回也要重新觸發 toast。 */
  seq: number
}

interface HumanGateState {
  waiting: WaitingState | null
  task: TaskState | null
  bounce: BounceState | null
  setWaiting: (p: WSWaitingForHumanPayload) => void
  clearWaiting: () => void
  setTask: (p: WSUserTaskPayload) => void
  /** 換關時呼叫：清掉舊關殘留的 banner 與等待列。 */
  onSubPhaseChange: (subPhase: string | null) => void
  showBounce: (reasonZh: string, hintZh: string) => void
  clearBounce: () => void
}

export const useHumanGateStore = create<HumanGateState>((set, get) => ({
  waiting: null,
  task: null,
  bounce: null,

  setWaiting: (p) =>
    set({
      waiting: {
        subPhase: p.sub_phase,
        round: p.round,
        required: p.required,
        targetUserId: p.target_user_id,
      },
    }),
  clearWaiting: () => set({ waiting: null }),

  setTask: (p) => {
    if (p.task_text === null || p.task_text === '') {
      set({ task: null })
      return
    }
    set({
      task: {
        taskText: p.task_text,
        subPhase: p.sub_phase,
        actionKind: p.action_kind,
        anchorNoteIds: p.anchor_note_ids ?? [],
      },
    })
  },

  onSubPhaseChange: (subPhase) => {
    const { task, waiting } = get()
    const next: Partial<Pick<HumanGateState, 'task' | 'waiting'>> = {}
    if (task && subPhase && task.subPhase && task.subPhase !== subPhase) {
      next.task = null
    }
    if (waiting && subPhase && waiting.subPhase && waiting.subPhase !== subPhase) {
      next.waiting = null
    }
    if (Object.keys(next).length > 0) set(next)
  },

  showBounce: (reasonZh, hintZh) =>
    set((s) => ({
      bounce: { reasonZh, hintZh, seq: (s.bounce?.seq ?? 0) + 1 },
    })),
  clearBounce: () => set({ bounce: null }),
}))
