import { useState } from 'react'
import { AlertTriangle, AlertCircle, Info, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { AlertItem, ProjectMonitorItem } from '../../types/models'

interface AlertBannerProps {
  projects: ProjectMonitorItem[]
}

interface ProjectAlert {
  projectName: string
  projectId: string
  alert: AlertItem
}

const LEVEL_CONFIG = {
  error: {
    icon: AlertCircle,
    bg: 'bg-error/10 border-error/30',
    text: 'text-error',
    dot: 'bg-error',
  },
  warning: {
    icon: AlertTriangle,
    bg: 'bg-warning/10 border-warning/30',
    text: 'text-warning',
    dot: 'bg-warning',
  },
  info: {
    icon: Info,
    bg: 'bg-info/10 border-info/30',
    text: 'text-info',
    dot: 'bg-info',
  },
} as const

export function AlertBanner({ projects }: AlertBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const allAlerts: ProjectAlert[] = projects.flatMap((p) =>
    p.alerts.map((alert) => ({
      projectName: p.name,
      projectId: p.id,
      alert,
    }))
  )

  // Sort: error first, then warning, then info
  const levelOrder = { error: 0, warning: 1, info: 2 }
  allAlerts.sort((a, b) => levelOrder[a.alert.level] - levelOrder[b.alert.level])

  if (allAlerts.length === 0) return null

  const errorCount = allAlerts.filter((a) => a.alert.level === 'error').length
  const warningCount = allAlerts.filter((a) => a.alert.level === 'warning').length
  const displayed = isExpanded ? allAlerts : allAlerts.slice(0, 3)

  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <button
        className="flex w-full items-center justify-between text-left cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-warning" />
          <span className="text-sm font-semibold text-text">
            需要關注
          </span>
          {errorCount > 0 && (
            <span className="rounded-full bg-error/20 px-2 py-0.5 text-xs font-medium text-error">
              {errorCount} 緊急
            </span>
          )}
          {warningCount > 0 && (
            <span className="rounded-full bg-warning/20 px-2 py-0.5 text-xs font-medium text-warning">
              {warningCount} 警告
            </span>
          )}
        </div>
        {allAlerts.length > 3 && (
          isExpanded
            ? <ChevronUp size={16} className="text-text-muted" />
            : <ChevronDown size={16} className="text-text-muted" />
        )}
      </button>

      <div className="mt-3 space-y-2">
        {displayed.map((item, idx) => {
          const config = LEVEL_CONFIG[item.alert.level]
          const Icon = config.icon
          return (
            <div
              key={`${item.projectId}-${idx}`}
              className={cn(
                'flex items-start gap-2 rounded-lg border px-3 py-2',
                config.bg,
              )}
            >
              <Icon size={14} className={cn(config.text, 'mt-0.5 shrink-0')} />
              <div className="min-w-0 flex-1">
                <span className="text-xs font-medium text-text">{item.projectName}</span>
                <span className="text-xs text-text-muted"> — {item.alert.message}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
