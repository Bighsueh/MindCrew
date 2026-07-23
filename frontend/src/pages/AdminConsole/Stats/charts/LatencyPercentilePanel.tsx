import type { LatencyPercentileRow } from '../../../../services/adminService'

interface Props {
  rows: LatencyPercentileRow[]
}

function fmt(ms: number | null): string {
  if (ms == null) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.round(ms)}ms`
}

/**
 * Per-provider latency percentiles (p50 / p95 / p99 / max / avg / count). The
 * first row is the overall aggregate; the rest are sorted slowest-p95 first so
 * a misbehaving provider surfaces at the top.
 */
export function LatencyPercentilePanel({ rows }: Props) {
  const hasData = rows.some((r) => r.request_count > 0)
  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-latency-percentiles"
    >
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-text-muted">Latency 百分位（分 provider）</h2>
        <span className="text-xs text-text-muted">越高的 p95 排越前面</span>
      </header>
      {!hasData ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-text-muted">
              <tr>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2 text-right">次數</th>
                <th className="px-3 py-2 text-right">p50</th>
                <th className="px-3 py-2 text-right">p95</th>
                <th className="px-3 py-2 text-right">p99</th>
                <th className="px-3 py-2 text-right">max</th>
                <th className="px-3 py-2 text-right">avg</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const overall = r.provider_id === null
                return (
                  <tr
                    key={r.provider_id ?? 'overall'}
                    className={
                      'border-t border-border ' +
                      (overall ? 'bg-surface-hover font-medium text-text' : '')
                    }
                  >
                    <td className="px-3 py-2">
                      {r.provider_name ?? (overall ? '全部' : r.provider_id?.slice(0, 8))}
                    </td>
                    <td className="px-3 py-2 text-right">{r.request_count}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.p50_ms)}</td>
                    <td className="px-3 py-2 text-right font-medium">{fmt(r.p95_ms)}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.p99_ms)}</td>
                    <td className="px-3 py-2 text-right text-text-muted">{fmt(r.max_ms)}</td>
                    <td className="px-3 py-2 text-right text-text-muted">{fmt(r.avg_ms)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
