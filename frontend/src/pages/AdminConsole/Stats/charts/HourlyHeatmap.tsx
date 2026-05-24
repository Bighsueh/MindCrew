import { useMemo } from 'react'
import type { HourlyBucket } from '../../../../services/adminService'

interface Props {
  buckets: HourlyBucket[]
}

/**
 * 24-cell CSS grid heatmap: which hour of day (UTC) sees the most LLM
 * traffic. Color depth scales linearly with request_count.
 */
export function HourlyHeatmap({ buckets }: Props) {
  const maxCount = useMemo(
    () => buckets.reduce((m, b) => Math.max(m, b.request_count), 0),
    [buckets],
  )

  function cellClass(count: number): string {
    if (maxCount === 0 || count === 0) return 'bg-surface-hover'
    const ratio = count / maxCount
    // 5 shades. Use opacity so the same Tailwind primary token works across themes.
    if (ratio < 0.2) return 'bg-primary/20'
    if (ratio < 0.4) return 'bg-primary/40'
    if (ratio < 0.6) return 'bg-primary/60'
    if (ratio < 0.85) return 'bg-primary/80'
    return 'bg-primary'
  }

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-hourly-heatmap"
    >
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-text-muted">24 小時請求熱力圖</h2>
        <span className="text-xs text-text-muted">(UTC)</span>
      </header>
      <div className="mt-3 grid grid-cols-12 gap-1" role="img" aria-label="hourly heatmap">
        {buckets.map((b) => (
          <div
            key={b.hour}
            className={`aspect-square rounded-sm ${cellClass(b.request_count)} flex flex-col items-center justify-center`}
            title={`${b.hour.toString().padStart(2, '0')}:00 — ${b.request_count} requests, ${b.total_tokens.toLocaleString()} tokens`}
          >
            <span className="text-[10px] font-mono text-text-muted">
              {b.hour.toString().padStart(2, '0')}
            </span>
            {b.request_count > 0 && (
              <span className="text-[10px] font-medium text-text">
                {b.request_count}
              </span>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-text-muted">
        每格 hover 可看詳細數字；數字＝該小時的請求數
      </p>
    </section>
  )
}
