import { useCallback, useEffect, useState } from 'react'
import { Loading } from '../../../components/common/Loading'
import {
  fetchOverviewStats,
  fetchSuccessRateTrend,
  fetchTokenTimeseries,
  listProviders,
  type AdminProvider,
  type Granularity,
  type OverviewStats,
  type SuccessRateTrend as SuccessRateTrendData,
  type TokenTimeseries,
} from '../../../services/adminService'
import { AdminNav } from '../AdminNav'
import { RefreshIndicator } from './RefreshIndicator'
import { TimeseriesControls } from './TimeseriesControls'
import { TokenUsageTimeline } from './charts/TokenUsageTimeline'
import { CallerBreakdown } from './charts/CallerBreakdown'
import { TopUsers } from './charts/TopUsers'
import { HourlyHeatmap } from './charts/HourlyHeatmap'
import { LatencyBuckets } from './charts/LatencyBuckets'
import { SuccessRateTrend } from './charts/SuccessRateTrend'

const REFRESH_INTERVAL_MS = 60_000

function initialRange(): { since: string; until: string } {
  const until = new Date()
  const since = new Date(until.getTime() - 24 * 3_600_000)
  return { since: since.toISOString(), until: until.toISOString() }
}

function rangeHours(since: string, until: string): number {
  return (new Date(until).getTime() - new Date(since).getTime()) / 3_600_000
}

// Map a since/until range back onto the overview-stats `days` window so the
// bottom charts move roughly in sync with the line chart. Always at least 1.
function approxDaysWindow(since: string, until: string): number {
  return Math.max(1, Math.ceil(rangeHours(since, until) / 24))
}

export function AdminStatsPage() {
  const [range, setRange] = useState(initialRange)
  const [userId, setUserId] = useState<string>('')
  const [providerIds, setProviderIds] = useState<string[]>([])
  const [granularity, setGranularity] = useState<'auto' | Granularity>('auto')
  const [overview, setOverview] = useState<OverviewStats | null>(null)
  const [timeseries, setTimeseries] = useState<TokenTimeseries | null>(null)
  const [successRate, setSuccessRate] = useState<SuccessRateTrendData | null>(null)
  const [allProviders, setAllProviders] = useState<AdminProvider[]>([])
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)
  const [error, setError] = useState('')

  // Providers don't change often; load once.
  useEffect(() => {
    listProviders()
      .then(setAllProviders)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
      })
  }, [])

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent === true
      if (silent) {
        setRefreshing(true)
      } else {
        setInitialLoading(true)
      }
      // Don't clear `error` on silent refresh — a transient network blip
      // shouldn't make the banner flicker every minute. Non-silent loads
      // (mount, controls change, manual refresh) clear it explicitly.
      if (!silent) setError('')
      try {
        const days = approxDaysWindow(range.since, range.until)
        const [o, ts, sr] = await Promise.all([
          fetchOverviewStats(days),
          fetchTokenTimeseries({
            since: range.since,
            until: range.until,
            user_id: userId || undefined,
            provider_ids: providerIds.length > 0 ? providerIds : undefined,
            granularity,
          }),
          fetchSuccessRateTrend({
            since: range.since,
            until: range.until,
            granularity,
          }),
        ])
        setOverview(o)
        setTimeseries(ts)
        setSuccessRate(sr)
        setLastUpdatedAt(new Date())
        if (silent) setError('')
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (silent) {
          setRefreshing(false)
        } else {
          setInitialLoading(false)
        }
      }
    },
    [range, userId, providerIds, granularity],
  )

  // Initial + controls-driven load.
  useEffect(() => {
    load().catch(() => {/* load already records its own error */})
  }, [load])

  // Phase 26.E: silent auto-refresh every REFRESH_INTERVAL_MS.
  useEffect(() => {
    if (!autoRefresh) return
    const tick = () => {
      if (document.visibilityState !== 'visible') return
      // `refreshing` is captured by closure here, but we want the *current*
      // value at tick time — read from a probe instead. Since React 18 batches
      // state and we re-create this effect when `load` changes (controls
      // edited), stale-closure risk is bounded to one tick max; we accept it.
      load({ silent: true }).catch(() => {/* error captured in state */})
    }
    const id = window.setInterval(tick, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [autoRefresh, load])

  const handleManualRefresh = useCallback(() => {
    load({ silent: true }).catch(() => {/* error captured in state */})
  }, [load])

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">Stats</h1>
          <p className="text-sm text-text-muted">
            Token 用量趨勢（依 provider 拆分、可篩選使用者）+ 成功率走勢 (30 分鐘粒度) + caller / latency / 24h 尖峰
          </p>
        </div>
        <RefreshIndicator
          autoRefresh={autoRefresh}
          refreshing={refreshing}
          lastUpdatedAt={lastUpdatedAt}
          onToggle={setAutoRefresh}
          onManualRefresh={handleManualRefresh}
        />
      </header>

      <AdminNav />

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">{error}</div>
      )}

      <TimeseriesControls
        since={range.since}
        until={range.until}
        userId={userId}
        providerIds={providerIds}
        granularity={granularity}
        effectiveGranularity={timeseries?.granularity ?? null}
        topUsers={overview?.top_users ?? []}
        allProviders={allProviders}
        onChange={(next) => {
          setRange({ since: next.since, until: next.until })
          setUserId(next.userId)
          setProviderIds(next.providerIds)
          setGranularity(next.granularity)
        }}
      />

      {(initialLoading && !overview) || !overview || !timeseries || !successRate ? (
        <Loading text="計算統計中…" />
      ) : (
        <div className="space-y-6">
          <TokenUsageTimeline data={timeseries} />
          <SuccessRateTrend data={successRate} />
          <CallerBreakdown rows={overview.callers} />
          <TopUsers rows={overview.top_users} />
          <HourlyHeatmap buckets={overview.hourly} />
          <LatencyBuckets buckets={overview.latency_buckets} />
        </div>
      )}
    </div>
  )
}
