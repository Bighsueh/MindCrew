import { Clock, MessageCircle, StickyNote, Gauge } from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatDuration, STAGE_LABELS } from '../../utils/formatters'
import type { StageInfo, StageHistoryEntry, AIContribution, DTStage } from '../../types/models'

interface ProjectDashboardStatsProps {
  stageInfo: StageInfo | null
  stageHistory: StageHistoryEntry[]
  messageCount: number
  noteCount: number
  aiContribution: AIContribution
  embedded?: boolean
}

const AI_LEVEL_CONFIG: Record<AIContribution, { label: string; width: string; color: string }> = {
  low: { label: '低', width: 'w-1/3', color: 'bg-success' },
  medium: { label: '中', width: 'w-2/3', color: 'bg-warning' },
  high: { label: '高', width: 'w-full', color: 'bg-accent' },
}

const STAGE_ORDER: DTStage[] = ['discover', 'define', 'develop', 'deliver']

const STAGE_COLORS: Record<string, string> = {
  discover: 'bg-info',
  define: 'bg-accent',
  develop: 'bg-warning',
  deliver: 'bg-success',
  completed: 'bg-success',
}

export function ProjectDashboardStats({
  stageInfo,
  stageHistory,
  messageCount,
  noteCount,
  aiContribution,
  embedded = false,
}: ProjectDashboardStatsProps) {
  const aiConfig = AI_LEVEL_CONFIG[aiContribution]

  return (
    <div className={embedded ? '' : 'rounded-xl border border-border bg-surface p-5 shadow-sm'}>
      <h3 className="mb-4 text-sm font-semibold text-text">活動概況</h3>

      {/* Stat cards grid */}
      <div className="grid grid-cols-2 gap-3 mb-5">
        {/* Current stage */}
        <StatCard
          icon={<Clock size={16} />}
          label="目前階段"
          value={stageInfo ? STAGE_LABELS[stageInfo.current_stage] : '—'}
          detail={stageInfo?.duration_seconds != null ? formatDuration(stageInfo.duration_seconds) : undefined}
        />

        {/* Messages */}
        <StatCard
          icon={<MessageCircle size={16} />}
          label="對話訊息"
          value={`${messageCount}`}
          detail="則"
        />

        {/* Notes */}
        <StatCard
          icon={<StickyNote size={16} />}
          label="便條紙"
          value={`${noteCount}`}
          detail="張"
        />

        {/* AI level */}
        <div className="rounded-lg bg-bg p-3">
          <div className="flex items-center gap-1.5 text-text-muted mb-2">
            <Gauge size={16} />
            <span className="text-xs">AI 貢獻度</span>
          </div>
          <p className="text-sm font-semibold text-text mb-1.5">{aiConfig.label}</p>
          <div className="h-1.5 w-full rounded-full bg-border/50">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                aiConfig.width,
                aiConfig.color,
              )}
            />
          </div>
        </div>
      </div>

      {/* Stage timeline */}
      {stageHistory.length > 0 && (
        <div>
          <p className="mb-3 text-xs font-medium text-text-muted uppercase tracking-wide">
            階段時間線
          </p>
          <div className="flex items-center gap-1">
            {STAGE_ORDER.map((stage) => {
              const entry = stageHistory.find((h) => h.to_stage === stage)
              const isCurrent = stageInfo?.current_stage === stage
              const isCompleted = !!entry

              return (
                <div key={stage} className="flex-1">
                  <div
                    className={cn(
                      'h-2 rounded-full transition-all',
                      isCompleted
                        ? STAGE_COLORS[stage]
                        : isCurrent
                          ? cn(STAGE_COLORS[stage], 'animate-pulse')
                          : 'bg-border/30',
                    )}
                  />
                  <p className="mt-1 text-center text-[10px] text-text-muted truncate">
                    {STAGE_LABELS[stage].replace(/^.+\s/, '')}
                  </p>
                  {entry?.duration_seconds != null && (
                    <p className="text-center text-[10px] text-text-muted">
                      {formatDuration(entry.duration_seconds)}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

interface StatCardProps {
  icon: React.ReactNode
  label: string
  value: string
  detail?: string
}

function StatCard({ icon, label, value, detail }: StatCardProps) {
  return (
    <div className="rounded-lg bg-bg p-3">
      <div className="flex items-center gap-1.5 text-text-muted mb-2">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-sm font-semibold text-text">{value}</span>
        {detail && <span className="text-xs text-text-muted">{detail}</span>}
      </div>
    </div>
  )
}
