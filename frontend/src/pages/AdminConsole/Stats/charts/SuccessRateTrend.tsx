import { useMemo, useState } from 'react'
import type { SuccessRateTrend as Data } from '../../../../services/adminService'

interface Props {
  data: Data
}

/**
 * SVG polyline of success rate (0..100%) bucketed by `data.granularity`.
 *
 * Phase 26: x-axis is now actual timestamps from the response (default
 * window: last 24h × 30min); empty buckets render as gaps rather than 0%
 * to avoid implying a real failure.
 */
export function SuccessRateTrend({ data }: Props) {
  const { granularity, points } = data
  const [hover, setHover] = useState<number | null>(null)

  const width = 760
  const height = 200
  const padX = 40
  const padY = 20
  const innerW = width - padX * 2
  const innerH = height - padY * 2

  const xFor = (i: number): number => {
    if (points.length <= 1) return padX
    return padX + (innerW / (points.length - 1)) * i
  }
  const yFor = (rate: number): number => padY + innerH - rate * innerH

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

  // Break the polyline at null-rate buckets so empty windows render as gaps.
  const segments = useMemo(() => {
    const out: Array<Array<{ x: number; y: number; i: number }>> = []
    let cur: Array<{ x: number; y: number; i: number }> = []
    points.forEach((p, i) => {
      if (p.rate == null) {
        if (cur.length > 0) {
          out.push(cur)
          cur = []
        }
        return
      }
      cur.push({ x: xFor(i), y: yFor(p.rate), i })
    })
    if (cur.length > 0) out.push(cur)
    return out
  }, [points])

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-success-rate"
    >
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-text-muted">成功率走勢</h2>
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
      <p className="mt-1 text-xs text-text-muted">success / total，0–100%</p>
      {points.length === 0 ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <svg width={width} height={height} role="img" aria-label="success rate trend">
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
                    strokeDasharray={g === 0 || g === 1 ? '' : '2 2'}
                  />
                  <text x={4} y={y + 4} className="fill-text-muted text-[10px]">
                    {Math.round(g * 100)}%
                  </text>
                </g>
              )
            })}
            {segments.map((seg, sIdx) => (
              <polyline
                key={sIdx}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                points={seg.map((s) => `${s.x},${s.y}`).join(' ')}
                className="text-success"
              />
            ))}
            {points.map((p, i) => {
              if (p.rate == null) return null
              const x = xFor(i)
              const y = yFor(p.rate)
              const labelEvery = Math.max(1, Math.ceil(points.length / 12))
              const showLabel =
                i === 0 || i === points.length - 1 || i % labelEvery === 0
              return (
                <g
                  key={p.bucket_ts}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <circle
                    cx={x}
                    cy={y}
                    r={hover === i ? 4 : 2.5}
                    className="fill-success"
                  />
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
            {hover !== null && points[hover]?.rate != null && (
              <g>
                <rect
                  x={Math.min(xFor(hover) + 8, width - 150)}
                  y={Math.max(padY, yFor(points[hover].rate!) - 40)}
                  width={140}
                  height={40}
                  rx={4}
                  className="fill-surface stroke-border"
                  strokeWidth={1}
                />
                <text
                  x={Math.min(xFor(hover) + 16, width - 142)}
                  y={Math.max(padY + 14, yFor(points[hover].rate!) - 24)}
                  className="fill-text text-[11px]"
                >
                  {formatLabel(points[hover].bucket_ts)}
                </text>
                <text
                  x={Math.min(xFor(hover) + 16, width - 142)}
                  y={Math.max(padY + 28, yFor(points[hover].rate!) - 10)}
                  className="fill-text-muted text-[10px]"
                >
                  {(points[hover].rate! * 100).toFixed(1)}% ·{' '}
                  {points[hover].success_count}/{points[hover].request_count}
                </text>
              </g>
            )}
          </svg>
        </div>
      )}
    </section>
  )
}
