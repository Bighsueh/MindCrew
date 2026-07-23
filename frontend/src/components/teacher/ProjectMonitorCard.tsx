import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Eye, LogIn, MessageSquare, Bot, Users, Clock, TrendingUp,
  TrendingDown, Minus, Send, Settings2, AlertCircle, FastForward,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../common/Button'
import { Modal } from '../common/Modal'
import { PhaseIndicator } from '../common/PhaseIndicator'
import { TurnPolicySwitcher } from './TurnPolicySwitcher'
import { formatDuration } from '../../utils/formatters'
import { sendHint, updateAIContribution } from '../../services/teacherService'
import { advanceStage } from '../../services/projectService'
import type { ProjectMonitorItem, AIContribution, DTStage } from '../../types/models'

interface ProjectMonitorCardProps {
  project: ProjectMonitorItem
  onRefresh: () => void
}

const TREND_ICON = {
  improving: TrendingUp,
  stagnant: Minus,
  declining: TrendingDown,
} as const

const TREND_COLOR = {
  improving: 'text-success',
  stagnant: 'text-text-muted',
  declining: 'text-error',
} as const

const AI_LEVELS: AIContribution[] = ['low', 'medium', 'high']
const AI_LEVEL_LABELS: Record<AIContribution, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
// Phase 42 補正 R2（裁定②）：教師面一併去英文（spec 28 §6 單一真相來源口徑）。
const STAGE_LABELS: Record<DTStage, string> = {
  warmup: '暖場 · 破冰',
  discover: '發現',
  define: '定義',
  completed: '第一鑽石完成',
}

const NEXT_STAGE: Partial<Record<DTStage, DTStage>> = {
  warmup: 'discover',
  discover: 'define',
  define: 'completed',
}

export function ProjectMonitorCard({ project, onRefresh }: ProjectMonitorCardProps) {
  const navigate = useNavigate()
  const [showHintModal, setShowHintModal] = useState(false)
  const [showAIModal, setShowAIModal] = useState(false)
  const [showAdvanceModal, setShowAdvanceModal] = useState(false)
  const [hintContent, setHintContent] = useState('')
  const [isSendingHint, setIsSendingHint] = useState(false)
  const [isUpdatingAI, setIsUpdatingAI] = useState(false)
  const [isAdvancing, setIsAdvancing] = useState(false)
  const [advanceError, setAdvanceError] = useState<string | null>(null)

  const { evaluation_score, participation, ai_activity, alerts } = project
  const hasAlerts = alerts.length > 0
  const hasError = alerts.some((a) => a.level === 'error')

  const handleSendHint = async () => {
    if (!hintContent.trim()) return
    setIsSendingHint(true)
    try {
      await sendHint(project.id, { content: hintContent })
      setHintContent('')
      setShowHintModal(false)
    } finally {
      setIsSendingHint(false)
    }
  }

  const handleForceAdvance = async () => {
    const next = NEXT_STAGE[project.current_stage as DTStage]
    if (!next) return
    setIsAdvancing(true)
    setAdvanceError(null)
    try {
      await advanceStage(project.id, {
        from: project.current_stage,
        to: next,
      })
      setShowAdvanceModal(false)
      onRefresh()
    } catch (err) {
      const message = err instanceof Error ? err.message : '推進階段失敗'
      setAdvanceError(message)
    } finally {
      setIsAdvancing(false)
    }
  }

  const handleUpdateAI = async (level: AIContribution) => {
    setIsUpdatingAI(true)
    try {
      await updateAIContribution(project.id, level)
      setShowAIModal(false)
      onRefresh()
    } finally {
      setIsUpdatingAI(false)
    }
  }

  // Participation ratio bar
  const totalMsg = participation.human_messages + participation.ai_messages
  const humanPct = totalMsg > 0 ? (participation.human_messages / totalMsg) * 100 : 50

  const TrendIcon = TREND_ICON[evaluation_score.trend]

  return (
    <>
      <div
        className={cn(
          'card-hover-warm rounded-2xl border bg-surface p-5 shadow-md',
          hasError ? 'border-error/40' : hasAlerts ? 'border-warning/40' : 'border-border-light',
        )}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-text truncate">{project.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <PhaseIndicator phase={project.current_stage} />
              <span className="flex items-center gap-1 text-xs text-text-muted">
                <Users size={12} />{project.seat_summary.human}
                <Bot size={12} className="ml-1" />{project.seat_summary.ai}
              </span>
            </div>
          </div>
          {hasError && <AlertCircle size={16} className="text-error shrink-0 mt-1" />}
        </div>

        {/* Stage duration + evaluation */}
        <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
          <div className="rounded-lg bg-bg px-2.5 py-2">
            <div className="flex items-center gap-1 text-text-muted mb-0.5">
              <Clock size={11} />
              <span>停留時間</span>
            </div>
            <span className="font-medium text-text">
              {formatDuration(project.stage_duration_seconds)}
            </span>
          </div>
          <div className="rounded-lg bg-bg px-2.5 py-2">
            <div className="flex items-center gap-1 text-text-muted mb-0.5">
              <TrendIcon size={11} className={TREND_COLOR[evaluation_score.trend]} />
              <span>評估分數</span>
            </div>
            <span className="font-medium text-text">
              {evaluation_score.latest_total != null
                ? `${evaluation_score.latest_total.toFixed(1)} / ${evaluation_score.threshold?.toFixed(1) ?? '-'}`
                : '尚無'}
            </span>
          </div>
        </div>

        {/* Participation ratio */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs text-text-muted mb-1">
            <span className="flex items-center gap-1">
              <MessageSquare size={11} />
              發言比 (人:{participation.human_messages} / AI:{participation.ai_messages})
            </span>
          </div>
          <div className="flex h-2 w-full overflow-hidden rounded-full bg-bg">
            <div
              className="bg-primary transition-all"
              style={{ width: `${humanPct}%` }}
            />
            <div
              className="bg-accent/60 transition-all"
              style={{ width: `${100 - humanPct}%` }}
            />
          </div>
        </div>

        {/* AI activity */}
        <div className="flex items-center gap-2 text-xs text-text-muted mb-3">
          <Bot size={12} />
          <span>AI 介入：{ai_activity.recent_interventions} 次 (近10分鐘) / 共 {ai_activity.total_interventions} 次</span>
        </div>

        {/* Phase 28：對話模式切換器 */}
        <div className="mb-3">
          <TurnPolicySwitcher
            projectId={project.id}
            projectName={project.name}
            currentPolicy={project.turn_policy ?? 'cued'}
            onChange={() => onRefresh()}
            compact
          />
        </div>

        {/* Alert badges */}
        {alerts.length > 0 && (
          <div className="mb-3 space-y-1">
            {alerts.slice(0, 2).map((alert, idx) => (
              <div
                key={idx}
                className={cn(
                  'rounded-md px-2 py-1 text-xs',
                  alert.level === 'error' ? 'bg-error/10 text-error' :
                  alert.level === 'warning' ? 'bg-warning/10 text-warning' :
                  'bg-info/10 text-info',
                )}
              >
                {alert.message}
              </div>
            ))}
          </div>
        )}

        {/* Action buttons */}
        <div className="grid grid-cols-5 gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs px-1"
            onClick={() => navigate(`/projects/${project.id}/lobby`)}
            title="觀察"
          >
            <Eye size={13} />
            <span className="hidden sm:inline">觀察</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs px-1"
            onClick={() => navigate(`/projects/${project.id}/lobby`)}
            title="進入"
          >
            <LogIn size={13} />
            <span className="hidden sm:inline">進入</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs px-1"
            onClick={() => setShowHintModal(true)}
            title="發送提示"
          >
            <Send size={13} />
            <span className="hidden sm:inline">提示</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs px-1"
            onClick={() => setShowAIModal(true)}
            title="調整 AI"
          >
            <Settings2 size={13} />
            <span className="hidden sm:inline">AI</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs px-1"
            onClick={() => {
              setAdvanceError(null)
              setShowAdvanceModal(true)
            }}
            title="強制推進階段"
            disabled={!NEXT_STAGE[project.current_stage as DTStage]}
          >
            <FastForward size={13} />
            <span className="hidden sm:inline">推進</span>
          </Button>
        </div>
      </div>

      {/* Send hint modal */}
      <Modal isOpen={showHintModal} onClose={() => setShowHintModal(false)} title="發送提示給小組">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">
            提示將以系統訊息的形式出現在 <strong>{project.name}</strong> 的聊天室中。
          </p>
          <textarea
            value={hintContent}
            onChange={(e) => setHintContent(e.target.value)}
            placeholder="輸入提示內容..."
            rows={3}
            className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setShowHintModal(false)}>
              取消
            </Button>
            <Button
              className="flex-1"
              isLoading={isSendingHint}
              onClick={handleSendHint}
              disabled={!hintContent.trim()}
            >
              發送
            </Button>
          </div>
        </div>
      </Modal>

      {/* Force advance modal */}
      <Modal
        isOpen={showAdvanceModal}
        onClose={() => setShowAdvanceModal(false)}
        title="強制推進階段"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">
            這會立即推進 <strong className="text-text">{project.name}</strong> 的階段，覆蓋 AI 自動評估。組長席位永遠由 AI 擔任，因此只有你（教師）可以手動推進。
          </p>
          <div className="rounded-lg bg-bg p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">目前</span>
              <span className="font-medium text-text">
                {STAGE_LABELS[project.current_stage as DTStage]}
              </span>
            </div>
            <div className="my-2 h-px bg-border-light" />
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">推進至</span>
              <span className="font-semibold text-primary">
                {(() => {
                  const next = NEXT_STAGE[project.current_stage as DTStage]
                  return next ? STAGE_LABELS[next] : '— 已是最後階段 —'
                })()}
              </span>
            </div>
          </div>
          {advanceError && (
            <div className="rounded-md bg-error/10 px-3 py-2 text-xs text-error">
              {advanceError}
            </div>
          )}
          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => setShowAdvanceModal(false)}
            >
              取消
            </Button>
            <Button
              className="flex-1"
              isLoading={isAdvancing}
              onClick={handleForceAdvance}
              disabled={!NEXT_STAGE[project.current_stage as DTStage]}
            >
              確認推進
            </Button>
          </div>
        </div>
      </Modal>

      {/* AI contribution modal */}
      <Modal isOpen={showAIModal} onClose={() => setShowAIModal(false)} title="調整 AI 貢獻等級">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">
            調整 <strong>{project.name}</strong> 的 AI 介入頻率。目前等級：
            <strong className="text-text"> {AI_LEVEL_LABELS[project.ai_contribution]}</strong>
          </p>
          <div className="flex gap-2">
            {AI_LEVELS.map((level) => (
              <Button
                key={level}
                variant={project.ai_contribution === level ? 'primary' : 'secondary'}
                className="flex-1"
                isLoading={isUpdatingAI}
                onClick={() => handleUpdateAI(level)}
              >
                {AI_LEVEL_LABELS[level]}
              </Button>
            ))}
          </div>
        </div>
      </Modal>
    </>
  )
}
