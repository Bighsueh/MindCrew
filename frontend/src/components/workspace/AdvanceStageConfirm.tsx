import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { CheckCircle2, AlertCircle, ArrowRight, X } from 'lucide-react'
import { cn } from '../../lib/utils'

export type DTStage = 'discover' | 'define' | 'develop' | 'deliver'

export interface AdvanceCheck {
  id: string
  label: string
  status: 'done' | 'warn'
  hint?: string
}

export interface AdvanceStageConfirmProps {
  open: boolean
  currentStage: DTStage
  checks?: AdvanceCheck[]
  onConfirm: () => void
  onCancel: () => void
  isAdvancing?: boolean
}

const STAGE_LABEL: Record<DTStage, string> = {
  discover: 'Discover',
  define: 'Define',
  develop: 'Develop',
  deliver: 'Deliver',
}

const NEXT_STAGE: Record<DTStage, DTStage | null> = {
  discover: 'define',
  define: 'develop',
  develop: 'deliver',
  deliver: null,
}

const DEFAULT_CHECKS: Record<DTStage, AdvanceCheck[]> = {
  discover: [
    { id: 'interview', label: '已上傳訪談資料', status: 'done' },
    { id: 'consensus', label: '群組聊天有共識訊息', status: 'done' },
    {
      id: 'persona',
      label: '尚未產生 user persona',
      status: 'warn',
      hint: '建議補上再推進',
    },
    {
      id: 'assistant',
      label: '個人助理使用率偏低',
      status: 'warn',
      hint: '鼓勵學員善用 AI 諮詢',
    },
  ],
  define: [
    { id: 'hmw', label: '已撰寫 HMW 問題', status: 'done' },
    { id: 'cluster', label: '痛點分群完成', status: 'done' },
    {
      id: 'hmw-count',
      label: 'HMW 數量偏少',
      status: 'warn',
      hint: '建議至少 3 條再推進',
    },
  ],
  develop: [
    { id: 'crazy8', label: '已完成 Crazy 8s 發散', status: 'done' },
    { id: 'vote', label: '已點點投票收斂', status: 'done' },
    { id: 'pick', label: '尚未選定主構想', status: 'warn' },
  ],
  deliver: [],
}

function CheckIcon({ status }: { status: 'done' | 'warn' }) {
  const Icon = status === 'done' ? CheckCircle2 : AlertCircle
  const color = status === 'done' ? 'text-success' : 'text-warning'
  return (
    <Icon
      size={20}
      className={cn(color, 'animate-draw-on shrink-0 mt-0.5')}
      strokeWidth={2}
      aria-hidden="true"
    />
  )
}

export function AdvanceStageConfirm({
  open,
  currentStage,
  checks,
  onConfirm,
  onCancel,
  isAdvancing = false,
}: AdvanceStageConfirmProps) {
  const nextStage = NEXT_STAGE[currentStage]

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isAdvancing) onCancel()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, isAdvancing, onCancel])

  if (!open || !nextStage) return null

  const currentLabel = STAGE_LABEL[currentStage]
  const nextLabel = STAGE_LABEL[nextStage]
  const items =
    checks && checks.length > 0 ? checks : DEFAULT_CHECKS[currentStage]

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/30 animate-backdrop-fade"
        onClick={() => {
          if (!isAdvancing) onCancel()
        }}
        aria-hidden="true"
      />
      <div
        className="relative z-10 w-full max-w-md rounded-xl bg-surface shadow-xl p-6 animate-modal-enter"
        role="dialog"
        aria-modal="true"
        aria-labelledby="advance-stage-title"
      >
        <button
          onClick={() => {
            if (!isAdvancing) onCancel()
          }}
          disabled={isAdvancing}
          className="absolute top-4 right-4 rounded-sm p-1.5 text-text-muted hover:bg-surface-hover hover:text-text disabled:opacity-50"
          aria-label="關閉"
        >
          <X size={18} />
        </button>

        <div className="pr-8">
          <h2
            id="advance-stage-title"
            className="text-lg font-semibold text-text flex items-center gap-2 flex-wrap"
          >
            <span>將 {currentLabel}</span>
            <ArrowRight size={16} className="text-text-muted" aria-hidden="true" />
            <span>{nextLabel}？</span>
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            推進後將自動展開 {nextLabel} 階段的任務模板。
          </p>
        </div>

        {items.length > 0 && (
          <ul className="mt-5 space-y-3 stagger-children" aria-label="階段檢查清單">
            {items.map((check) => (
              <li key={check.id} className="flex items-start gap-3">
                <CheckIcon status={check.status} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-text">{check.label}</div>
                  {check.hint && (
                    <div className="mt-0.5 text-xs text-text-muted">
                      {check.hint}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isAdvancing}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            先補齊
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isAdvancing}
            className="rounded-md px-4 py-2 text-sm font-medium text-text-muted hover:bg-surface-hover hover:text-text disabled:opacity-50"
          >
            {isAdvancing ? '推進中…' : `仍要推進到 ${nextLabel}`}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
