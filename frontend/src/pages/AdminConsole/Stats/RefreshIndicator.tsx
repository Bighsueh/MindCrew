interface Props {
  autoRefresh: boolean
  refreshing: boolean
  lastUpdatedAt: Date | null
  onToggle: (next: boolean) => void
  onManualRefresh: () => void
}

function formatClock(d: Date | null): string {
  if (!d) return '—'
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * Compact status bar shown in the Stats page header. Indicates whether the
 * background poll is active, when the last refresh succeeded, and lets the
 * admin pause auto-refresh or trigger one immediately.
 *
 * Phase 26.E: 60s setInterval lives in the parent (Stats/index.tsx); this
 * component is presentational.
 */
export function RefreshIndicator({
  autoRefresh,
  refreshing,
  lastUpdatedAt,
  onToggle,
  onManualRefresh,
}: Props) {
  return (
    <div
      className="flex items-center gap-3 text-xs text-text-muted"
      data-testid="stats-refresh-indicator"
    >
      <span
        title={lastUpdatedAt ? '時間以瀏覽器當地時區顯示；圖表 X 軸為 UTC' : undefined}
      >
        上次更新：
        <span className="ml-1 font-mono text-text">{formatClock(lastUpdatedAt)}</span>
      </span>

      <span
        className="inline-block h-3 w-3"
        aria-hidden="true"
        data-testid="stats-refresh-spinner"
        data-active={refreshing ? 'true' : 'false'}
      >
        {refreshing && (
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-text-muted border-t-transparent" />
        )}
      </span>

      <label className="flex items-center gap-1">
        <input
          type="checkbox"
          checked={autoRefresh}
          onChange={(e) => onToggle(e.target.checked)}
          data-testid="stats-refresh-toggle"
        />
        <span>自動刷新（60s）</span>
      </label>

      <button
        type="button"
        onClick={onManualRefresh}
        disabled={refreshing}
        className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-muted hover:text-text disabled:opacity-50"
        data-testid="stats-refresh-button"
      >
        重新整理
      </button>
    </div>
  )
}
