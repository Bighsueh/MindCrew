import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { Loading } from '../../../components/common/Loading'
import {
  fetchLLMHealth,
  type LLMHealth,
  type LLMOverallStatus,
} from '../../../services/adminService'
import { AdminNav } from '../AdminNav'

/**
 * Phase 42 D5（G14 / #35，spec 20 §13.6）：LLM fail-stop 健康總覽。
 *
 * 整體判定 up/degraded/down＋reactive/proactive 門檻狀態、各 provider 健康
 * （連續失敗／最近失敗時間+原因／cooldown）、受 fail-stop 暫停的房間清單。
 * 手動 useEffect + 30s silent 輪詢（比照 Logs/Stats）。
 */

const STATUS_STYLE: Record<LLMOverallStatus, string> = {
  up: 'bg-success-bg text-success',
  degraded: 'bg-amber-100 text-amber-800',
  down: 'bg-error-bg text-error',
}

const STATUS_LABEL: Record<LLMOverallStatus, string> = {
  up: '正常',
  degraded: '部分異常',
  down: '中斷（fail-stop）',
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export function AdminLLMHealthPage() {
  const [data, setData] = useState<LLMHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) {
      setLoading(true)
      setError('')
    }
    try {
      const res = await fetchLLMHealth()
      setData(res)
      setError('')
    } catch (e: unknown) {
      if (!opts?.silent) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    load().catch(() => {/* load records its own error */})
    const id = window.setInterval(() => {
      load({ silent: true }).catch(() => {})
    }, 30000)
    return () => window.clearInterval(id)
  }, [load])

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text">LLM Health</h1>
          <p className="text-sm text-text-muted">
            備援耗盡連續失敗或健康檢查連續不健康 → fail-stop 全房暫停；恢復後自動續跑
          </p>
        </div>
        <Button variant="ghost" onClick={() => load()} data-testid="refresh-llm-health">
          <RefreshCw className="mr-1 h-4 w-4" /> 重新整理
        </Button>
      </header>

      <AdminNav />

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">{error}</div>
      )}

      {loading || !data ? (
        <Loading text="載入 LLM 健康狀態…" />
      ) : (
        <div className="space-y-6">
          {/* 整體判定 */}
          <section className="rounded-lg border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center gap-4">
              <span
                className={`rounded-full px-3 py-1 text-sm font-semibold ${STATUS_STYLE[data.overall_status]}`}
                data-testid="llm-overall-status"
              >
                {STATUS_LABEL[data.overall_status]}
              </span>
              <span className="text-sm text-text-muted">
                reactive 連續失敗 {data.reactive_consecutive_failures}/{data.reactive_threshold}
                ；健檢連續不健康 {data.proactive_unhealthy_streak}/{data.proactive_threshold}
              </span>
              <span className="text-sm text-text-muted">
                最近狀態變更：{fmtTime(data.last_status_change)}
              </span>
            </div>
          </section>

          {/* per-provider 健康 */}
          <section className="rounded-lg border border-border bg-surface p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Providers
            </h2>
            {data.providers.length === 0 ? (
              <p className="mt-3 text-sm text-text-muted">（尚無健康檢查資料）</p>
            ) : (
              <table className="mt-3 w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="py-2">名稱</th>
                    <th>健康</th>
                    <th>連續失敗</th>
                    <th>最近失敗</th>
                    <th>原因</th>
                    <th>Cooldown</th>
                    <th>最近檢查</th>
                  </tr>
                </thead>
                <tbody>
                  {data.providers.map((p) => (
                    <tr key={p.provider_id} className="border-t border-border">
                      <td className="py-2 pr-3 font-medium text-text">{p.provider_name}</td>
                      <td className="pr-3">
                        <span
                          className={
                            p.healthy
                              ? 'rounded-full bg-success-bg px-2 py-0.5 text-xs text-success'
                              : 'rounded-full bg-error-bg px-2 py-0.5 text-xs text-error'
                          }
                        >
                          {p.healthy ? 'healthy' : 'unhealthy'}
                        </span>
                      </td>
                      <td className="pr-3">{p.consecutive_failures}</td>
                      <td className="pr-3 text-xs">{fmtTime(p.last_failure_at)}</td>
                      <td className="pr-3 text-xs text-text-muted">
                        {p.last_failure_reason ?? '—'}
                      </td>
                      <td className="pr-3 text-xs">
                        {p.cooldown_remaining_seconds != null
                          ? `${p.cooldown_remaining_seconds}s`
                          : '—'}
                      </td>
                      <td className="pr-3 text-xs">{fmtTime(p.last_check_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* 受影響房 */}
          <section className="rounded-lg border border-border bg-surface p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              受影響房間（fail-stop 暫停中）
            </h2>
            {data.affected_rooms.length === 0 ? (
              <p className="mt-3 text-sm text-text-muted">（目前沒有被 fail-stop 暫停的房間）</p>
            ) : (
              <table className="mt-3 w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="py-2">專案</th>
                    <th>暫停原因</th>
                    <th>暫停時間</th>
                  </tr>
                </thead>
                <tbody>
                  {data.affected_rooms.map((r) => (
                    <tr key={r.project_id} className="border-t border-border">
                      <td className="py-2 pr-3 font-medium text-text">
                        {r.project_name ?? r.project_id}
                      </td>
                      <td className="pr-3 text-xs">{r.pause_reason ?? '—'}</td>
                      <td className="pr-3 text-xs">{fmtTime(r.paused_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
