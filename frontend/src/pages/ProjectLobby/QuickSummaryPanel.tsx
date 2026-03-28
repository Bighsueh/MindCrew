import { Sparkles, AlertTriangle, RefreshCw, Tag, Crosshair } from 'lucide-react'
import { Button } from '../../components/common/Button'
import { useLobbyStore } from '../../stores/lobbyStore'
import { formatRelativeTime } from '../../utils/formatters'

interface QuickSummaryPanelProps {
  projectId: string
  embedded?: boolean
}

export function QuickSummaryPanel({ projectId, embedded = false }: QuickSummaryPanelProps) {
  const { summary, isSummaryLoading, summaryError, fetchSummary } = useLobbyStore()

  const handleGenerate = () => {
    fetchSummary(projectId)
  }

  return (
    <div className={embedded ? '' : 'rounded-xl border border-border bg-surface p-5 shadow-sm'}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-accent" />
          <h3 className="text-sm font-semibold text-text">快速摘要</h3>
        </div>
      </div>

      {/* Generate button or loading */}
      {!summary && !isSummaryLoading && !summaryError && (
        <div className="text-center py-2">
          <p className="text-xs text-text-muted mb-3">
            讓 AI 幫你統整目前的討論狀態
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleGenerate}
            className="w-full"
          >
            <span className="flex items-center justify-center gap-1.5">
              <Sparkles size={14} />
              產生摘要
            </span>
          </Button>
        </div>
      )}

      {/* Loading skeleton */}
      {isSummaryLoading && (
        <div className="space-y-3 animate-pulse">
          <div className="h-3 w-full rounded bg-border/50" />
          <div className="h-3 w-4/5 rounded bg-border/50" />
          <div className="h-3 w-3/5 rounded bg-border/50" />
          <div className="flex gap-2 mt-4">
            <div className="h-5 w-16 rounded-full bg-border/50" />
            <div className="h-5 w-20 rounded-full bg-border/50" />
            <div className="h-5 w-14 rounded-full bg-border/50" />
          </div>
        </div>
      )}

      {/* Error */}
      {summaryError && (
        <div className="text-center py-2">
          <p className="text-xs text-error mb-3">{summaryError}</p>
          <Button size="sm" variant="ghost" onClick={handleGenerate}>
            <span className="flex items-center justify-center gap-1.5">
              <RefreshCw size={14} />
              重試
            </span>
          </Button>
        </div>
      )}

      {/* Summary result */}
      {summary && !isSummaryLoading && (
        <div className="space-y-4">
          {/* Summary text */}
          <p className="text-sm text-text leading-relaxed">{summary.summary}</p>

          {/* Topics */}
          {summary.topics.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Tag size={12} className="text-text-muted" />
                <span className="text-xs font-medium text-text-muted">討論主題</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {summary.topics.map((topic) => (
                  <span
                    key={topic}
                    className="rounded-full bg-accent/10 px-2.5 py-0.5 text-xs text-accent"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Current focus */}
          {summary.current_focus && (
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <Crosshair size={12} className="text-text-muted" />
                <span className="text-xs font-medium text-text-muted">當前焦點</span>
              </div>
              <p className="rounded-lg bg-primary/5 px-3 py-2 text-xs text-text">
                {summary.current_focus}
              </p>
            </div>
          )}

          {/* Blind spots */}
          {summary.blind_spots.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <AlertTriangle size={12} className="text-warning" />
                <span className="text-xs font-medium text-text-muted">可能盲點</span>
              </div>
              <ul className="space-y-1">
                {summary.blind_spots.map((spot) => (
                  <li key={spot} className="text-xs text-text-muted flex items-start gap-1.5">
                    <span className="mt-1 h-1 w-1 flex-shrink-0 rounded-full bg-warning" />
                    {spot}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Timestamp + refresh */}
          <div className="flex items-center justify-between pt-2 border-t border-border/50">
            <span className="text-[10px] text-text-muted">
              產生於 {formatRelativeTime(summary.generated_at)}
            </span>
            <button
              onClick={handleGenerate}
              className="flex items-center gap-1 text-[10px] text-accent hover:text-text transition-colors"
            >
              <RefreshCw size={10} />
              重新產生
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
