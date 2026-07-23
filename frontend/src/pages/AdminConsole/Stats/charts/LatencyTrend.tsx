import { useMemo, useState } from 'react'
import type { LatencyStats } from '../../../../services/adminService'

interface Props {
  data: LatencyStats
}

interface Pt {
  x: number
  y: number
  i: number
}

/**
 * Dual SVG polyline of latency over time: avg (muted) + p95 (accent), bucketed
 * by `data.granularity`. Empty buckets render as gaps. Mirrors the SVG
 * approach used by `SuccessRateTrend` so the axes line up visually.
 */
export function LatencyTrend({ data }: Props) {
  const { granularity, trend } = data
  const [hover, setHover] = useState<number | null>(null)

  const width = 760
  const height = 200
  const padX = 48
  const padY = 20
  const innerW = width - padX * 2
  const innerH = height - padY * 2

  const maxMs = useMemo(() => {
    const vals = trend.flatMap((p) => [p.p95_ms ?? 0, p.avg_ms ?? 0])
    return Math.max(1, ...vals)
  }, [trend])

  const xFor = (i: number): number =>
    trend.length <= 1 ? padX : padX + (innerW / (trend.length - 1)) * i
  const yFor = (ms: number): number => padY + innerH - (ms / maxMs) * innerH

  const formatLabel = (iso: string): string => {
    const d = new Date(iso)
    if (granularity === '30min' || granularity === 'hour') {
      return `${d.getUTCHours().toString().padStart(2, '0')}:${d
        .getUTCMinutes()
        .toString()
        .padStart(2, '0')}`
    }
    return `${(d.getUTCMonth() + 1).toString().padStart(2, '0')}-${d
      .getUTCDate()
      .toString()
      .padStart(2, '0')}`
  }

  const buildSegments = (pick: (i: number) => number | null) => {
    const out: Pt[][] = []
    let cur: Pt[] = []
    trend.forEach((_p, i) => {
      const v = pick(i)
      if (v == null) {
        if (cur.length) out.push(cur)
        cur = []
        return
      }
      cur.push({ x: xFor(i), y: yFor(v), i })
    })
    if (cur.length) out.push(cur)
    return out
  }

  const p95Segs = useMemo(
    () => buildSegments((i) => trend[i].p95_ms),
    [trend, maxMs],
  )
  const avgSegs = useMemo(
    () => buildSegments((i) => trend[i].avg_ms),
    [trend, maxMs],
  )

  const fmtMs = (ms: number): string =>
    ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-latency-trend"
    >
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-text-muted">Latency 走勢（avg / p95）</h2>
        <span className="text-xs text-text-muted">
          粒度：
          {granularity === '30min' ? '每 30 分鐘' : granularity === 'hour' ? '每小時' : '每日'}{' '}
          (UTC)
        </span>
      </header>
      <div className="mt-1 flex gap-4 text-xs text-text-muted">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-primary" /> p95
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-text-muted" /> avg
        </span>
      </div>
      {trend.length === 0 ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <svg width={width} height={height} role="img" aria-label="latency trend">
            {[0, 0.5, 1].map((g) => {
              const y = padY + innerH - g * innerH
              return (
                <g key={g}>
                  <line
                    x1={padX}
                    x2={width - padX}
                    y1={y}
                    y2={y}
                    stroke="currentColor"
                    className="text-border"
                    strokeDasharray={g === 0 ? '' : '2 2'}
                  />
                  <text x={4} y={y + 4} className="fill-text-muted text-[10px]">
                    {fmtMs(g * maxMs)}
                  </text>
                </g>
              )
            })}
            {avgSegs.map((seg, sIdx) => (
              <polyline
                key={`a${sIdx}`}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                points={seg.map((s) => `${s.x},${s.y}`).join(' ')}
                className="text-text-muted"
              />
            ))}
            {p95Segs.map((seg, sIdx) => (
              <polyline
                key={`p${sIdx}`}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                points={seg.map((s) => `${s.x},${s.y}`).join(' ')}
                className="text-primary"
              />
            ))}
            {trend.map((p, i) => {
              if (p.p95_ms == null) return null
              const x = xFor(i)
              const y = yFor(p.p95_ms)
              const labelEvery = Math.max(1, Math.ceil(trend.length / 12))
              const showLabel = i === 0 || i === trend.length - 1 || i % labelEvery === 0
              return (
                <g
                  key={p.bucket_ts}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <circle cx={x} cy={y} r={hover === i ? 4 : 2.5} className="fill-primary" />
                  {showLabel && (
                    <text
                      x={x}
                      y={height - 4}
                      textAnchor="middle"
                      className="fill-text-muted text-[10px]"
                    >
                      {formatLabel(p.bucket_ts)}
                    </text>
                  )}
                </g>
              )
            })}
            {hover !== null && trend[hover]?.p95_ms != null && (
              <g>
                <rect
                  x={Math.min(xFor(hover) + 8, width - 160)}
                  y={Math.max(padY, yFor(trend[hover].p95_ms!) - 46)}
                  width={150}
                  height={46}
                  rx={4}
                  className="fill-surface stroke-border"
                  strokeWidth={1}
                />
                <text
                  x={Math.min(xFor(hover) + 16, width - 152)}
                  y={Math.max(padY + 14, yFor(trend[hover].p95_ms!) - 30)}
                  className="fill-text text-[11px]"
                >
                  {formatLabel(trend[hover].bucket_ts)} · {trend[hover].request_count} 次
                </text>
                <text
                  x={Math.min(xFor(hover) + 16, width - 152)}
                  y={Math.max(padY + 28, yFor(trend[hover].p95_ms!) - 16)}
                  className="fill-text-muted text-[10px]"
                >
                  p95 {fmtMs(trend[hover].p95_ms!)}
                  {trend[hover].avg_ms != null && ` · avg ${fmtMs(trend[hover].avg_ms!)}`}
                </text>
              </g>
            )}
          </svg>
        </div>
      )}
    </section>
  )
}
