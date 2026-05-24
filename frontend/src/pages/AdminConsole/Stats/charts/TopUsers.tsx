import type { TopUserStatRow } from '../../../../services/adminService'

interface Props {
  rows: TopUserStatRow[]
}

/**
 * Top-N users by total tokens consumed. Owner = the user attributed to pay
 * for the call (project teacher for agent ticks, request user for coach).
 */
export function TopUsers({ rows }: Props) {
  return (
    <section
      className="rounded-lg border border-border bg-surface p-4"
      data-testid="chart-top-users"
    >
      <h2 className="text-sm font-semibold text-text-muted">Top 使用者（依 token 用量）</h2>
      <p className="mt-1 text-xs text-text-muted">
        Owning user — 對 agent tick 來說是 project 的主辦 teacher，對 coach/personas 則是發起人。
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-text-muted">
            <tr>
              <th className="px-3 py-2">使用者</th>
              <th className="px-3 py-2">角色</th>
              <th className="px-3 py-2 text-right">Requests</th>
              <th className="px-3 py-2 text-right">Total Tokens</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-text-muted">
                  無資料
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.owning_user_id} className="border-t border-border">
                <td className="px-3 py-2">
                  <div className="font-medium text-text">
                    {r.display_name ?? r.owning_user_id.slice(0, 8)}
                  </div>
                  <div className="font-mono text-xs text-text-muted">
                    {r.owning_user_id.slice(0, 12)}…
                  </div>
                </td>
                <td className="px-3 py-2 text-text-muted">{r.role ?? '—'}</td>
                <td className="px-3 py-2 text-right">{r.request_count}</td>
                <td className="px-3 py-2 text-right font-medium">
                  {r.total_tokens.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
