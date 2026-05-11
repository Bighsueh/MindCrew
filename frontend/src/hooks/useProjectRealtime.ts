/**
 * useProjectRealtime — Spec 14 + 15.
 *
 * 統一 hook：訂閱 timer state + advance vote session，5 秒 polling fallback。
 * 真實系統會用 WS，本版先用 REST polling 確保功能可用。
 */

import { useEffect, useState } from 'react'
import api from '@/services/api'
import { useTimerStore, type TimerStateSnapshot, type TimerConfig } from '@/stores/timerStore'
import type { AdvanceVoteSession } from '@/components/vote/AdvanceVoteBanner'

interface UseProjectRealtimeResult {
  voteSession: AdvanceVoteSession | null
}

export function useProjectRealtime(projectId: string): UseProjectRealtimeResult {
  const [voteSession, setVoteSession] = useState<AdvanceVoteSession | null>(null)
  const setSnapshot = useTimerStore((s) => s.setSnapshot)
  const setConfig = useTimerStore((s) => s.setConfig)

  useEffect(() => {
    let cancelled = false
    let timerHandle: number | null = null

    const fetchOnce = async () => {
      try {
        const [timerResp, voteResp] = await Promise.all([
          api.get<TimerStateSnapshot & { config?: TimerConfig }>(
            `/projects/${projectId}/timer`,
          ),
          api.get<{ session: AdvanceVoteSession | null }>(
            `/projects/${projectId}/advance-vote`,
          ),
        ])

        if (cancelled) return

        const t = timerResp.data
        setSnapshot({
          available: Boolean(t.available),
          current_sub_phase: t.current_sub_phase ?? null,
          budget_seconds: t.budget_seconds ?? 0,
          used_seconds: t.used_seconds ?? 0,
          paused: Boolean(t.paused),
          used_pct: t.used_pct ?? 0,
        })
        if (t.config) setConfig(t.config)

        setVoteSession(voteResp.data.session)
      } catch {
        // silent — keep current state
      }
    }

    void fetchOnce()
    timerHandle = window.setInterval(fetchOnce, 5000)

    return () => {
      cancelled = true
      if (timerHandle !== null) window.clearInterval(timerHandle)
    }
  }, [projectId, setSnapshot, setConfig])

  return { voteSession }
}
