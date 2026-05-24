import type { CallerStatRow } from '../../../../services/adminService'

interface Props {
  rows: CallerStatRow[]
}

/**
 * Horizontal bar chart: which caller consumed how many tokens.
 * Useful for spotting whether stats are dominated by a noisy subsystem.
 */
export function CallerBreakdown({ rows }: Props) {
  const maxTokens = rows.reduce((m, r) => Math.max(m, r.total_tokens), 0)

  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-caller-breakdown"
    >
      <h2 className="text-sm font-semibold text-text-muted">Caller 用量分佈</h2>
      <p className="mt-1 text-xs text-text-muted">
        每個程式呼叫點（agent_think、project_summary…）的請求數與 token 總量
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-text-muted">所選範圍內沒有紀錄</p>
      ) : (
        <div className="mt-3 space-y-2">
          {rows.map((r) => {
            const pct = maxTokens > 0 ? Math.max(2, Math.round((r.total_tokens / maxTokens) * 100)) : 0
            return (
              <div key={r.caller} className="flex items-center gap-3 text-sm">
                <div className="w-44 truncate font-mono text-xs text-text" title={r.caller}>
                  {r.caller}
                </div>
                <div className="w-16 text-right font-mono text-xs text-text-muted">
                  {r.request_count}
                </div>
                <div className="flex-1 overflow-hidden rounded-md bg-surface-hover">
                  <div
                    className="h-6 bg-accent/80 px-2 text-xs font-medium leading-6 text-text-inverse"
                    style={{ width: `${pct}%` }}
                  >
                    {r.total_tokens.toLocaleString()} tokens
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
