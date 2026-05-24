import { useMemo, useState } from 'react'
import type {
  ProviderRef,
  TimeseriesPoint,
  TokenTimeseries,
} from '../../../../services/adminService'

interface Props {
  data: TokenTimeseries
}

// Palette tuned to be distinguishable on both light and dark themes.
const PROVIDER_COLORS = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#14b8a6', // teal
  '#ec4899', // pink
  '#84cc16', // lime
]

function colorForProvider(idx: number): string {
  return PROVIDER_COLORS[idx % PROVIDER_COLORS.length]
}

interface PivotedBucket {
  bucket_ts: string
  total_tokens: number
  request_count: number
  byProvider: Map<string, TimeseriesPoint>
}

function pivot(
  points: TimeseriesPoint[],
  providers: ProviderRef[],
): PivotedBucket[] {
  const byBucket = new Map<string, PivotedBucket>()
  for (const p of points) {
    let row = byBucket.get(p.bucket_ts)
    if (!row) {
      row = {
        bucket_ts: p.bucket_ts,
        total_tokens: 0,
        request_count: 0,
        byProvider: new Map(),
      }
      byBucket.set(p.bucket_ts, row)
    }
    row.total_tokens += p.total_tokens
    row.request_count += p.request_count
    if (p.provider_id) {
      row.byProvider.set(p.provider_id, p)
    }
  }
  // Ensure every bucket has an entry for every provider (zeros for missing).
  for (const row of byBucket.values()) {
    for (const prov of providers) {
      if (!row.byProvider.has(prov.id)) {
        row.byProvider.set(prov.id, {
          bucket_ts: row.bucket_ts,
          provider_id: prov.id,
          request_count: 0,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
        })
      }
    }
  }
  return Array.from(byBucket.values()).sort((a, b) =>
    a.bucket_ts.localeCompare(b.bucket_ts),
  )
}

/**
 * Stacked-area chart of token usage over time, grouped by LLM provider.
 *
 * The X axis is the bucket timestamp (formatted by granularity); the Y axis
 * is the sum of total_tokens across providers in that bucket. Each provider
 * is a separate stacked layer with its own color; clicking a legend entry
 * hides that series. When the response has no tokens at all (a pre-25.L
 * regression where vLLM streams didn't emit usage), the chart falls back
 * to plotting request counts instead.
 */
export function TokenUsageTimeline({ data }: Props) {
  const { granularity, points, providers } = data
  const [hover, setHover] = useState<number | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const pivoted = useMemo(() => pivot(points, providers), [points, providers])

  // Decide whether to plot tokens or request_count.
  const totalTokens = useMemo(
    () => pivoted.reduce((m, r) => m + r.total_tokens, 0),
    [pivoted],
  )
  const totalRequests = useMemo(
    () => pivoted.reduce((m, r) => m + r.request_count, 0),
    [pivoted],
  )
  const fallbackToCount = totalTokens === 0 && totalRequests > 0
  const metricForCell = (cell: TimeseriesPoint) =>
    fallbackToCount ? cell.request_count : cell.total_tokens

  // Visible providers (legend toggle).
  const visibleProviders = providers.filter((p) => !hidden.has(p.id))

  // Per-bucket stacked totals (for Y scale).
  const stackedTotals = pivoted.map((row) =>
    visibleProviders.reduce((sum, prov) => {
      const cell = row.byProvider.get(prov.id)
      return sum + (cell ? metricForCell(cell) : 0)
    }, 0),
  )
  const max = Math.max(0, ...stackedTotals)
  const yMax = Math.max(1, Math.ceil(max * 1.1))

  const W = 760
  const H = 260
  const padX = 56
  const padY = 24
  const innerW = W - padX * 2
  const innerH = H - padY * 2

  const xFor = (i: number): number => {
    if (pivoted.length <= 1) return padX
    return padX + (innerW / (pivoted.length - 1)) * i
  }

  const formatLabel = (iso: string): string => {
    const d = new Date(iso)
    if (granularity === '30min' || granularity === 'hour') {
      return `${d.getUTCMonth() + 1}/${d
        .getUTCDate()
        .toString()
        .padStart(2, '0')} ${d.getUTCHours().toString().padStart(2, '0')}:${d
        .getUTCMinutes()
        .toString()
        .padStart(2, '0')}`
    }
    return `${(d.getUTCMonth() + 1).toString().padStart(2, '0')}-${d
      .getUTCDate()
      .toString()
      .padStart(2, '0')}`
  }

  // Build stacked polygons per provider.
  // Each provider's polygon = upper boundary line + previous lower boundary
  // line (reversed) so the area fills cleanly.
  const polygons = useMemo(() => {
    const out: Array<{ provider: ProviderRef; path: string; color: string }> = []
    const lowerY: number[] = pivoted.map(() => padY + innerH)
    visibleProviders.forEach((prov) => {
      const upper: number[] = []
      for (let i = 0; i < pivoted.length; i++) {
        const cell = pivoted[i].byProvider.get(prov.id)
        const v = cell ? metricForCell(cell) : 0
        const yLower = lowerY[i]
        // Convert "y at top of this layer" — layer rises from lowerY upward.
        const yUpper = yLower - (v / yMax) * innerH
        upper.push(yUpper)
      }
      const topPts = upper.map((y, i) => `${xFor(i)},${y}`).join(' ')
      const bottomPts = lowerY
        .map((y, i) => `${xFor(i)},${y}`)
        .reverse()
        .join(' ')
      out.push({
        provider: prov,
        path: `${topPts} ${bottomPts}`,
        color: colorForProvider(
          // Stable index across show/hide toggles.
          providers.findIndex((p) => p.id === prov.id),
        ),
      })
      // Promote upper to lower for the next layer.
      for (let i = 0; i < upper.length; i++) lowerY[i] = upper[i]
    })
    return out
  }, [pivoted, visibleProviders, providers, yMax, fallbackToCount, innerH])

  const toggleProvider = (id: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-token-timeline"
    >
      <header className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold text-text-muted">
            {fallbackToCount ? '請求數趨勢 (依 provider 堆疊)' : 'Token 用量趨勢 (依 provider 堆疊)'}
          </h2>
          {fallbackToCount && (
            <span
              className="rounded-sm bg-warning-bg px-1.5 py-0.5 text-[10px] text-warning"
              title="此範圍內所有 log 的 total_tokens 都是 0，改畫請求數"
            >
              fallback: request_count
            </span>
          )}
        </div>
        <span className="text-xs text-text-muted">
          粒度：
          {granularity === '30min'
            ? '每 30 分鐘'
            : granularity === 'hour'
              ? '每小時'
              : '每日'}{' '}
          (UTC)
        </span>
      </header>

      {providers.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="ts-legend">
          {providers.map((p, idx) => {
            const isHidden = hidden.has(p.id)
            return (
              <button
                key={p.id}
                type="button"
                className="flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-0.5 text-xs"
                onClick={() => toggleProvider(p.id)}
                data-testid={`ts-legend-${p.id}`}
                title={isHidden ? '已隱藏，點擊顯示' : '點擊隱藏'}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{
                    backgroundColor: colorForProvider(idx),
                    opacity: isHidden ? 0.25 : 1,
                  }}
                />
                <span
                  className={isHidden ? 'text-text-muted line-through' : 'text-text'}
                >
                  {p.name}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {pivoted.length === 0 ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <svg width={W} height={H} role="img" aria-label="token usage over time">
            {/* Y gridlines: 0, 50%, 100% */}
            {[0, 0.5, 1].map((g) => {
              const y = padY + innerH - g * innerH
              const value = Math.round(g * yMax)
              return (
                <g key={g}>
                  <line
                    x1={padX}
                    x2={W - padX}
                    y1={y}
                    y2={y}
                    className="text-border"
                    stroke="currentColor"
                    strokeDasharray={g === 0 || g === 1 ? '' : '2 2'}
                  />
                  <text
                    x={padX - 6}
                    y={y + 4}
                    textAnchor="end"
                    className="fill-text-muted text-[10px]"
                  >
                    {value.toLocaleString()}
                  </text>
                </g>
              )
            })}

            {polygons.map((poly) => (
              <polygon
                key={poly.provider.id}
                points={poly.path}
                fill={poly.color}
                fillOpacity={0.5}
                stroke={poly.color}
                strokeWidth={1.2}
              />
            ))}

            {/* Bucket markers + hover hotspots */}
            {pivoted.map((row, i) => {
              const x = xFor(i)
              const labelEvery = Math.max(1, Math.ceil(pivoted.length / 10))
              const showLabel =
                i === 0 || i === pivoted.length - 1 || i % labelEvery === 0
              return (
                <g
                  key={row.bucket_ts}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <rect
                    x={x - (innerW / Math.max(1, pivoted.length)) / 2}
                    y={padY}
                    width={innerW / Math.max(1, pivoted.length)}
                    height={innerH}
                    fill="transparent"
                  />
                  {showLabel && (
                    <text
                      x={x}
                      y={H - 4}
                      textAnchor="middle"
                      className="fill-text-muted text-[10px]"
                    >
                      {formatLabel(row.bucket_ts)}
                    </text>
                  )}
                </g>
              )
            })}

            {hover !== null && pivoted[hover] && (
              <g>
                <line
                  x1={xFor(hover)}
                  x2={xFor(hover)}
                  y1={padY}
                  y2={padY + innerH}
                  stroke="currentColor"
                  className="text-text-muted"
                  strokeDasharray="2 2"
                />
                {(() => {
                  const row = pivoted[hover]
                  const lines = visibleProviders
                    .map((prov) => {
                      const cell = row.byProvider.get(prov.id)
                      return cell ? { prov, value: metricForCell(cell), cell } : null
                    })
                    .filter(
                      (x): x is { prov: ProviderRef; value: number; cell: TimeseriesPoint } =>
                        !!x && x.value > 0,
                    )
                  const boxX = Math.min(xFor(hover) + 8, W - 220)
                  const boxY = Math.max(padY, 40)
                  const boxH = 24 + lines.length * 14
                  return (
                    <>
                      <rect
                        x={boxX}
                        y={boxY}
                        width={210}
                        height={boxH}
                        rx={4}
                        className="fill-surface stroke-border"
                        strokeWidth={1}
                      />
                      <text x={boxX + 8} y={boxY + 14} className="fill-text text-[11px]">
                        {formatLabel(row.bucket_ts)} · {row.request_count} reqs
                      </text>
                      {lines.map((ln, idx) => (
                        <g key={ln.prov.id}>
                          <rect
                            x={boxX + 8}
                            y={boxY + 22 + idx * 14}
                            width={8}
                            height={8}
                            fill={colorForProvider(
                              providers.findIndex((p) => p.id === ln.prov.id),
                            )}
                          />
                          <text
                            x={boxX + 20}
                            y={boxY + 30 + idx * 14}
                            className="fill-text-muted text-[10px]"
                          >
                            {ln.prov.name}: {ln.value.toLocaleString()}
                          </text>
                        </g>
                      ))}
                    </>
                  )
                })()}
              </g>
            )}
          </svg>
        </div>
      )}
    </section>
  )
}
