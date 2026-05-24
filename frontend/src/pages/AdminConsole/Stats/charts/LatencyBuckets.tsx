import type { LatencyBucket } from '../../../../services/adminService'

interface Props {
  buckets: LatencyBucket[]
}

/**
 * Latency histogram across fixed bucket boundaries. The buckets are
 * defined server-side so the chart stays consistent across deployments.
 */
export function LatencyBuckets({ buckets }: Props) {
  const max = buckets.reduce((m, b) => Math.max(m, b.request_count), 0)

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-latency-buckets"
    >
      <h2 className="text-sm font-semibold text-text-muted">Latency 分佈</h2>
      <p className="mt-1 text-xs text-text-muted">
        端到端延遲（含 fallback 與重試）的請求數量分佈
      </p>
      {max === 0 ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 space-y-2">
          {buckets.map((b) => {
            const pct = max > 0 ? Math.max(2, Math.round((b.request_count / max) * 100)) : 0
            return (
              <div key={b.label} className="flex items-center gap-3 text-sm">
                <div className="w-20 font-mono text-xs text-text-muted">{b.label}</div>
                <div className="w-12 text-right font-mono text-xs text-text">
                  {b.request_count}
                </div>
                <div className="flex-1 overflow-hidden rounded-md bg-surface-hover">
                  <div
                    className="h-5 bg-info/80"
                    style={{ width: `${pct}%` }}
                    aria-label={`${b.label} ${b.request_count} requests`}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
