/**
 * useProjectRealtime — Spec 15。
 *
 * 訂閱 timer state，5 秒 polling fallback（真實系統用 WS，本版先用 REST polling）。
 *
 * v4.15：移除 advance-vote 輪詢（crew 推進投票廢除，改為後端 progression_watcher
 * 決定性推進，前端不再有投票 UI）。
 */

import { useEffect } from 'react'
import api from '@/services/api'
import { getStage } from '@/services/projectService'
import { useProjectStore } from '@/stores/projectStore'
import { useStageStore } from '@/stores/stageStore'
import { useTimerStore, type TimerStateSnapshot, type TimerConfig } from '@/stores/timerStore'
import type { RoomPauseReason } from '@/types/ws'

// Phase 42 補正 R4（D5 縫 b）：room_paused banner 只由 WS 事件驅動——outage／休眠中
// 刷新頁面看不到異常說明。由 timer 快照的 pause_reason 水合；只認 WS 同源的兩種
// 全房暫停理由（teacher 暫停不發 room_paused，不由此路徑豎 banner）。
const HYDRATABLE_PAUSE_REASONS: readonly RoomPauseReason[] = ['llm_down', 'awaiting_human']

export function useProjectRealtime(projectId: string): void {
  const setSnapshot = useTimerStore((s) => s.setSnapshot)
  const setConfig = useTimerStore((s) => s.setConfig)

  useEffect(() => {
    let cancelled = false
    let timerHandle: number | null = null

    const fetchOnce = async () => {
      try {
        const timerResp = await api.get<
          TimerStateSnapshot & {
            config?: TimerConfig
            state?: { pause_reason?: string | null }
          }
        >(`/projects/${projectId}/timer`)

        if (cancelled) return

        const t = timerResp.data

        // Phase 42 補正 R4（D5 縫 b）：全房暫停 banner 水合／收斂。
        const pauseReason = t.state?.pause_reason ?? null
        const store = useProjectStore.getState()
        if (
          t.paused &&
          pauseReason &&
          HYDRATABLE_PAUSE_REASONS.includes(pauseReason as RoomPauseReason)
        ) {
          if (store.roomPauseReason !== pauseReason) {
            store.setRoomPaused(pauseReason as RoomPauseReason)
          }
        } else if (
          store.roomPauseReason &&
          HYDRATABLE_PAUSE_REASONS.includes(store.roomPauseReason) &&
          !t.paused
        ) {
          // 快照說已恢復 → 清殘留 banner（漏接 room_resumed 的自癒）。
          store.setRoomResumed()
        }
        setSnapshot({
          available: Boolean(t.available),
          current_sub_phase: t.current_sub_phase ?? null,
          // 帶上友善 label，否則 TimerBadge 退回顯示 raw 代號（盲測 2026-06-09「剩餘·1.1a」）。
          current_sub_phase_label: t.current_sub_phase_label ?? t.current_sub_phase ?? null,
          budget_seconds: t.budget_seconds ?? 0,
          used_seconds: t.used_seconds ?? 0,
          paused: Boolean(t.paused),
          used_pct: t.used_pct ?? 0,
          // spec 16 v2.0 §4.5：本關上限/已用（舊後端缺欄位時退回既有同義值）＋暖場目標。
          sub_phase_budget_seconds: t.sub_phase_budget_seconds ?? t.budget_seconds ?? 0,
          sub_phase_used_seconds: t.sub_phase_used_seconds ?? t.used_seconds ?? 0,
          warmup_goal: t.warmup_goal ?? null,
          warmup_soft_seconds: t.warmup_soft_seconds ?? null,
        })
        if (t.config) setConfig(t.config)
      } catch {
        // silent — keep current state
      }
    }

    // stage 兜底校正：即使漏接重連事件，UI 也在 5s 內收斂到後端真實 stage（盲測 2026-06-09：
    // 後端已 define、學生卻看不到）。set 前先比較，避免無謂 re-render；不觸發 spotlight tour。
    const reconcileStage = async () => {
      try {
        const info = await getStage(projectId)
        if (cancelled) return
        const s = useStageStore.getState()
        if (info.current_stage !== s.currentStage) s.setCurrentStage(info.current_stage)
        if (
          info.current_micro_phase &&
          info.current_micro_phase !== s.currentMicroPhase
        ) {
          s.setCurrentMicroPhase(info.current_micro_phase)
        }
      } catch {
        // silent — keep current state
      }
    }

    const poll = () => {
      void fetchOnce()
      void reconcileStage()
    }
    poll()
    timerHandle = window.setInterval(poll, 5000)

    return () => {
      cancelled = true
      if (timerHandle !== null) window.clearInterval(timerHandle)
    }
  }, [projectId, setSnapshot, setConfig])
}
