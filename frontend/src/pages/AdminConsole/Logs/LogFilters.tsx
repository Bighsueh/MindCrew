import { Button } from '../../../components/common/Button'
import type {
  AdminProvider,
  TopUserStatRow,
} from '../../../services/adminService'

export interface LogFilterValue {
  providerId: string
  model: string
  caller: string
  userId: string
  success: 'all' | 'true' | 'false'
  /** ISO UTC string, or '' for no lower bound. */
  since: string
  /** ISO UTC string, or '' for no upper bound. */
  until: string
}

export const EMPTY_FILTERS: LogFilterValue = {
  providerId: '',
  model: '',
  caller: '',
  userId: '',
  success: 'all',
  since: '',
  until: '',
}

interface Props {
  value: LogFilterValue
  providers: AdminProvider[]
  modelOptions: string[]
  callerOptions: string[]
  userOptions: TopUserStatRow[]
  live: boolean
  onChange: (next: LogFilterValue) => void
  onToggleLive: (on: boolean) => void
  onRefresh: () => void
  onReset: () => void
}

// <input type="datetime-local"> ↔ canonical UTC ISO. Empty stays empty.
function isoToLocalInput(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const off = d.getTimezoneOffset() * 60_000
  return new Date(d.getTime() - off).toISOString().slice(0, 16)
}

function localInputToIso(local: string): string {
  return local ? new Date(local).toISOString() : ''
}

const FIELD_CLASS = 'rounded-md border border-border bg-surface px-3 py-2 text-sm'

/**
 * Filter + Live-mode bar for the log explorer. Cross-filter by provider,
 * model, caller (用途), user (誰), status, and time range. Presentational —
 * all state lives in the parent so it can drive a single fetch per change.
 */
export function LogFilters({
  value,
  providers,
  modelOptions,
  callerOptions,
  userOptions,
  live,
  onChange,
  onToggleLive,
  onRefresh,
  onReset,
}: Props) {
  const patch = (p: Partial<LogFilterValue>) => onChange({ ...value, ...p })

  return (
    <section className="space-y-2 rounded-lg border border-border bg-surface p-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="起點">
          <input
            type="datetime-local"
            value={isoToLocalInput(value.since)}
            onChange={(e) => patch({ since: localInputToIso(e.target.value) })}
            className={FIELD_CLASS}
            data-testid="log-since"
          />
        </Field>
        <Field label="終點">
          <input
            type="datetime-local"
            value={isoToLocalInput(value.until)}
            onChange={(e) => patch({ until: localInputToIso(e.target.value) })}
            className={FIELD_CLASS}
            data-testid="log-until"
          />
        </Field>
        <Field label="使用者（誰）">
          <select
            value={value.userId}
            onChange={(e) => patch({ userId: e.target.value })}
            className={FIELD_CLASS}
            data-testid="log-user"
          >
            <option value="">全部</option>
            {userOptions.map((u) => (
              <option key={u.owning_user_id} value={u.owning_user_id}>
                {u.display_name ?? u.owning_user_id.slice(0, 8)}
                {u.role ? ` (${u.role})` : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Provider">
          <select
            value={value.providerId}
            onChange={(e) => patch({ providerId: e.target.value })}
            className={FIELD_CLASS}
            data-testid="log-provider"
          >
            <option value="">全部</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model">
          <select
            value={value.model}
            onChange={(e) => patch({ model: e.target.value })}
            className={FIELD_CLASS}
            data-testid="log-model"
          >
            <option value="">全部</option>
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>
        <Field label="用途 (caller)">
          <input
            list="log-caller-options"
            value={value.caller}
            onChange={(e) => patch({ caller: e.target.value })}
            placeholder="全部"
            className={FIELD_CLASS}
            data-testid="log-caller"
          />
          <datalist id="log-caller-options">
            {callerOptions.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </Field>
        <Field label="狀態">
          <select
            value={value.success}
            onChange={(e) =>
              patch({ success: e.target.value as LogFilterValue['success'] })
            }
            className={FIELD_CLASS}
            data-testid="log-success"
          >
            <option value="all">全部</option>
            <option value="true">success</option>
            <option value="false">failure</option>
          </select>
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-text-muted">
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => onToggleLive(e.target.checked)}
            data-testid="log-live-toggle"
          />
          <span className={live ? 'font-medium text-success' : ''}>
            即時更新{live ? '（每 10 秒）' : ''}
          </span>
        </label>
        <Button variant="secondary" size="sm" onClick={onRefresh}>
          重新整理
        </Button>
        <button
          type="button"
          onClick={onReset}
          className="text-xs text-text-muted underline hover:text-text"
          data-testid="log-reset"
        >
          清除全部篩選
        </button>
      </div>
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-text-muted">{label}</label>
      {children}
    </div>
  )
}
