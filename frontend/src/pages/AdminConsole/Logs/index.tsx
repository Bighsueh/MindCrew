import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button } from '../../../components/common/Button'
import { Loading } from '../../../components/common/Loading'
import {
  fetchOverviewStats,
  listLogs,
  listProviders,
  type AdminLogList,
  type AdminProvider,
  type CallerStatRow,
  type TopUserStatRow,
} from '../../../services/adminService'
import { AdminNav } from '../AdminNav'
import { LogDetailModal } from './LogDetailModal'
import { EMPTY_FILTERS, LogFilters, type LogFilterValue } from './LogFilters'

const PAGE_SIZE = 50
const LIVE_INTERVAL_MS = 10_000

export function AdminLogsPage() {
  const [providers, setProviders] = useState<AdminProvider[]>([])
  const [callerOptions, setCallerOptions] = useState<string[]>([])
  const [userOptions, setUserOptions] = useState<TopUserStatRow[]>([])
  const [data, setData] = useState<AdminLogList | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const [filters, setFilters] = useState<LogFilterValue>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [live, setLive] = useState(false)
  const [openLogId, setOpenLogId] = useState<number | null>(null)

  const modelOptions = useMemo(() => {
    return Array.from(new Set(providers.map((p) => p.model))).sort()
  }, [providers])

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent === true
      if (silent) setRefreshing(true)
      else setLoading(true)
      if (!silent) setError('')
      try {
        const query: Parameters<typeof listLogs>[0] = { limit: PAGE_SIZE, offset }
        if (filters.providerId) query.provider_id = filters.providerId
        if (filters.model) query.model = filters.model
        if (filters.caller) query.caller = filters.caller
        if (filters.userId) query.user_id = filters.userId
        if (filters.success !== 'all') query.success = filters.success === 'true'
        if (filters.since) query.since = filters.since
        if (filters.until) query.until = filters.until
        const res = await listLogs(query)
        setData(res)
      } catch (e: unknown) {
        if (!silent) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (silent) setRefreshing(false)
        else setLoading(false)
      }
    },
    [offset, filters],
  )

  // Option lists for the filter dropdowns (providers + callers + users).
  useEffect(() => {
    listProviders()
      .then(setProviders)
      .catch(() => {/* nav still works without provider names */})
    fetchOverviewStats(30)
      .then((o) => {
        setCallerOptions(o.callers.map((c: CallerStatRow) => c.caller))
        setUserOptions(o.top_users)
      })
      .catch(() => {/* filter dropdowns degrade to free-text / empty */})
  }, [])

  useEffect(() => {
    load().catch(() => {/* load already records its own error */})
  }, [load])

  // Live mode: poll the newest page every LIVE_INTERVAL_MS while visible.
  useEffect(() => {
    if (!live) return
    const tick = () => {
      if (document.visibilityState !== 'visible') return
      load({ silent: true }).catch(() => {/* error captured in state */})
    }
    const id = window.setInterval(tick, LIVE_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [live, load])

  const onFiltersChange = (next: LogFilterValue) => {
    setOffset(0)
    setFilters(next)
  }

  const onToggleLive = (on: boolean) => {
    if (on) setOffset(0) // newest first when going live
    setLive(on)
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const page = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-text">LLM Request Logs</h1>
        <p className="text-sm text-text-muted">
          每次 provider 呼叫（成功或失敗）皆有一筆紀錄：來自哪個 provider／model、用途、誰、
          花多少 token、latency。可交叉篩選，開「即時更新」看最新呼叫進來。點任意 row 看完整
          messages 與 response。
        </p>
      </header>

      <AdminNav />

      <LogFilters
        value={filters}
        providers={providers}
        modelOptions={modelOptions}
        callerOptions={callerOptions}
        userOptions={userOptions}
        live={live}
        onChange={onFiltersChange}
        onToggleLive={onToggleLive}
        onRefresh={() => load({ silent: true })}
        onReset={() => {
          setOffset(0)
          setFilters(EMPTY_FILTERS)
        }}
      />

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">{error}</div>
      )}

      {loading || !data ? (
        <Loading text="載入紀錄…" />
      ) : (
        <>
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>
              共 {data.total} 筆{refreshing && ' · 更新中…'}
            </span>
            {live && <span className="text-success">● 即時更新中</span>}
          </div>
          <div className="overflow-x-auto rounded-lg border border-border" data-testid="logs-table">
            <table className="min-w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2">時間</th>
                  <th className="px-3 py-2">使用者</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Provider · Model · Tier</th>
                  <th className="px-3 py-2">用途</th>
                  <th className="px-3 py-2 text-right">Tokens</th>
                  <th className="px-3 py-2 text-right">Latency</th>
                  <th className="px-3 py-2">結果</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-6 text-center text-text-muted">
                      無紀錄
                    </td>
                  </tr>
                )}
                {data.items.map((row) => (
                  <tr
                    key={row.id}
                    className="cursor-pointer border-t border-border hover:bg-surface-hover"
                    onClick={() => setOpenLogId(row.id)}
                    data-testid={`log-row-${row.id}`}
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-text">{row.owning_user_display_name ?? '—'}</div>
                      {row.triggered_by_user_id &&
                        row.triggered_by_user_id !== row.owning_user_id && (
                          <div className="text-xs text-text-muted">
                            觸發：{row.triggered_by_display_name ?? '—'}
                          </div>
                        )}
                    </td>
                    <td className="px-3 py-2 text-text-muted">{row.project_name ?? '—'}</td>
                    <td className="px-3 py-2">
                      <div className="text-text">
                        {row.provider_name ?? row.provider_id.slice(0, 8)}
                        <span className="ml-1 text-xs text-text-muted">T{row.tier_used}</span>
                        {row.cascade_from_tier !== null && (
                          <span className="text-xs text-warning"> ← T{row.cascade_from_tier}</span>
                        )}
                      </div>
                      {row.model && (
                        <div className="font-mono text-xs text-text-muted">{row.model}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{row.caller}</td>
                    <td className="px-3 py-2 text-right font-medium">{row.total_tokens}</td>
                    <td className="px-3 py-2 text-right">{row.latency_ms}ms</td>
                    <td className="px-3 py-2">
                      {row.success ? (
                        <span className="text-success">success</span>
                      ) : (
                        <span className="text-error" title={row.error_message ?? ''}>
                          {row.error_class ?? 'failure'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm text-text-muted">
            <div>
              共 {data.total} 筆 · 第 {page} / {totalPages} 頁
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一頁
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一頁
              </Button>
            </div>
          </div>
        </>
      )}

      <LogDetailModal logId={openLogId} onClose={() => setOpenLogId(null)} />
    </div>
  )
}
