import { useCallback, useEffect, useState } from 'react'
import { Button } from '../../../components/common/Button'
import { Loading } from '../../../components/common/Loading'
import {
  listLogs,
  listProviders,
  type AdminLogList,
  type AdminProvider,
} from '../../../services/adminService'
import { AdminNav } from '../AdminNav'
import { LogDetailModal } from './LogDetailModal'

const PAGE_SIZE = 50

export function AdminLogsPage() {
  const [providers, setProviders] = useState<AdminProvider[]>([])
  const [data, setData] = useState<AdminLogList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [providerId, setProviderId] = useState<string>('')
  const [success, setSuccess] = useState<'all' | 'true' | 'false'>('all')
  const [offset, setOffset] = useState(0)
  const [openLogId, setOpenLogId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const query: Parameters<typeof listLogs>[0] = { limit: PAGE_SIZE, offset }
      if (providerId) query.provider_id = providerId
      if (success !== 'all') query.success = success === 'true'
      const res = await listLogs(query)
      setData(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [offset, providerId, success])

  useEffect(() => {
    listProviders().then(setProviders).catch(() => {/* nav still works without provider names */})
  }, [])

  useEffect(() => {
    load().catch(() => {/* load already records its own error */})
  }, [load])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const page = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-text">LLM Request Logs</h1>
        <p className="text-sm text-text-muted">
          每次 provider 呼叫（成功或失敗）皆有一筆紀錄。點任意 row 可以看完整 messages 與 response。
        </p>
      </header>

      <AdminNav />

      <section className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted">Provider</label>
          <select
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value)
              setOffset(0)
            }}
            data-testid="filter-provider"
          >
            <option value="">全部</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted">狀態</label>
          <select
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={success}
            onChange={(e) => {
              setSuccess(e.target.value as 'all' | 'true' | 'false')
              setOffset(0)
            }}
            data-testid="filter-success"
          >
            <option value="all">全部</option>
            <option value="true">success</option>
            <option value="false">failure</option>
          </select>
        </div>
        <Button variant="secondary" onClick={() => load()}>
          重新整理
        </Button>
      </section>

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">{error}</div>
      )}

      {loading || !data ? (
        <Loading text="載入紀錄…" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border" data-testid="logs-table">
            <table className="min-w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2">時間</th>
                  <th className="px-3 py-2">使用者</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Provider · Tier</th>
                  <th className="px-3 py-2">Caller</th>
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
                      <div className="text-text">
                        {row.owning_user_display_name ?? '—'}
                      </div>
                      {row.triggered_by_user_id &&
                        row.triggered_by_user_id !== row.owning_user_id && (
                          <div className="text-xs text-text-muted">
                            觸發：{row.triggered_by_display_name ?? '—'}
                          </div>
                        )}
                    </td>
                    <td className="px-3 py-2 text-text-muted">
                      {row.project_name ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      {row.provider_name ?? row.provider_id.slice(0, 8)}
                      <span className="ml-1 text-xs text-text-muted">T{row.tier_used}</span>
                      {row.cascade_from_tier !== null && (
                        <span className="text-xs text-warning"> ← T{row.cascade_from_tier}</span>
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
