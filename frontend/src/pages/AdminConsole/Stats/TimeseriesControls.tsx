import type {
  AdminProvider,
  Granularity,
  TopUserStatRow,
} from '../../../services/adminService'

interface Props {
  /** ISO string (UTC) for the start of the range. */
  since: string
  /** ISO string (UTC) for the end (exclusive). */
  until: string
  /** Filter the timeline to a single attributable user, or '' for everyone. */
  userId: string
  /** Selected provider IDs; empty list = "全部 provider". */
  providerIds: string[]
  /** Granularity requested by the user (`auto` = let backend decide). */
  granularity: 'auto' | Granularity
  /** Granularity the backend actually used (shown as a hint). */
  effectiveGranularity: Granularity | null
  topUsers: TopUserStatRow[]
  allProviders: AdminProvider[]
  onChange: (next: {
    since: string
    until: string
    userId: string
    providerIds: string[]
    granularity: 'auto' | Granularity
  }) => void
}

// Browser <input type="datetime-local"> only accepts/emits "YYYY-MM-DDTHH:mm"
// (no seconds, no zone). Convert between that local form and the canonical
// UTC ISO string we ship to the backend.
function isoToLocalInput(iso: string): string {
  const d = new Date(iso)
  const off = d.getTimezoneOffset() * 60_000
  return new Date(d.getTime() - off).toISOString().slice(0, 16)
}

function localInputToIso(local: string): string {
  return new Date(local).toISOString()
}

function shiftFromNow(hours: number): { since: string; until: string } {
  const now = new Date()
  const since = new Date(now.getTime() - hours * 3_600_000)
  return { since: since.toISOString(), until: now.toISOString() }
}

const PRESETS: Array<{ label: string; hours: number }> = [
  { label: '過去 24h', hours: 24 },
  { label: '過去 7 天', hours: 24 * 7 },
  { label: '過去 14 天', hours: 24 * 14 },
  { label: '過去 30 天', hours: 24 * 30 },
]

const GRANULARITY_OPTIONS: Array<{ value: 'auto' | Granularity; label: string }> = [
  { value: 'auto', label: '自動' },
  { value: '30min', label: '30 分鐘' },
  { value: 'hour', label: '每小時' },
  { value: 'day', label: '每日' },
]

/**
 * Inline controls for the timeseries line chart: start/end datetime, user
 * filter, provider multi-select, granularity selector. Emits a single
 * onChange so the parent can debounce-fetch once per real change.
 */
export function TimeseriesControls({
  since,
  until,
  userId,
  providerIds,
  granularity,
  effectiveGranularity,
  topUsers,
  allProviders,
  onChange,
}: Props) {
  const emit = (patch: Partial<{
    since: string
    until: string
    userId: string
    providerIds: string[]
    granularity: 'auto' | Granularity
  }>) =>
    onChange({
      since,
      until,
      userId,
      providerIds,
      granularity,
      ...patch,
    })

  const toggleProvider = (id: string) => {
    if (providerIds.includes(id)) {
      emit({ providerIds: providerIds.filter((p) => p !== id) })
    } else {
      emit({ providerIds: [...providerIds, id] })
    }
  }

  return (
    <section
      className="rounded-lg border border-border bg-surface p-3"
      data-testid="timeseries-controls"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted" htmlFor="ts-since">
            起點
          </label>
          <input
            id="ts-since"
            type="datetime-local"
            value={isoToLocalInput(since)}
            onChange={(e) => emit({ since: localInputToIso(e.target.value) })}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            data-testid="ts-since"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted" htmlFor="ts-until">
            終點
          </label>
          <input
            id="ts-until"
            type="datetime-local"
            value={isoToLocalInput(until)}
            onChange={(e) => emit({ until: localInputToIso(e.target.value) })}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            data-testid="ts-until"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted" htmlFor="ts-user">
            使用者
          </label>
          <select
            id="ts-user"
            value={userId}
            onChange={(e) => emit({ userId: e.target.value })}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            data-testid="ts-user"
          >
            <option value="">全部使用者</option>
            {topUsers.map((u) => (
              <option key={u.owning_user_id} value={u.owning_user_id}>
                {u.display_name ?? u.owning_user_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-text-muted" htmlFor="ts-granularity">
            粒度
          </label>
          <select
            id="ts-granularity"
            value={granularity}
            onChange={(e) =>
              emit({ granularity: e.target.value as 'auto' | Granularity })
            }
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            data-testid="ts-granularity-select"
          >
            {GRANULARITY_OPTIONS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-baseline gap-2 text-xs text-text-muted">
          <span>實際採用：</span>
          <span data-testid="ts-granularity" className="font-medium text-text">
            {effectiveGranularity === '30min'
              ? '每 30 分鐘 (UTC)'
              : effectiveGranularity === 'hour'
                ? '每小時 (UTC)'
                : effectiveGranularity === 'day'
                  ? '每日 (UTC)'
                  : '—'}
          </span>
        </div>
      </div>
      {allProviders.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-text-muted">Provider：</span>
          {allProviders.map((p) => {
            const checked = providerIds.length === 0 || providerIds.includes(p.id)
            return (
              <label
                key={p.id}
                className="flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-muted hover:text-text"
                data-testid={`ts-provider-${p.id}`}
              >
                <input
                  type="checkbox"
                  checked={providerIds.includes(p.id)}
                  onChange={() => toggleProvider(p.id)}
                />
                <span className={checked ? 'text-text' : ''}>{p.name}</span>
                <span className="text-text-muted">·T{p.tier}</span>
              </label>
            )
          })}
          {providerIds.length > 0 && (
            <button
              type="button"
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-muted hover:text-text"
              onClick={() => emit({ providerIds: [] })}
              data-testid="ts-provider-clear"
            >
              清除選擇（顯示全部）
            </button>
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => emit({ ...shiftFromNow(p.hours) })}
            className="rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-text-muted hover:text-text"
            data-testid={`ts-preset-${p.hours}`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </section>
  )
}
