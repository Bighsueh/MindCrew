// Phase 34 (spec/26-first-diamond-closing.md): 第一鑽石終局橫幅。
//
// 訂閱 first_diamond_completed WS event；在 workspace 顯示「第一鑽石完成」+
// 當選 HMW + 「回到 Lobby」CTA。當 project.current_stage === 'completed' 時 mount。

import { CheckCircle2, ArrowLeft } from 'lucide-react'
import { cn } from '../../lib/utils'

export interface FirstDiamondOutput {
  personas?: Array<{
    name: string
    fields?: Record<string, string>
    completeness?: number
  }>
  chosen_problem_statement?: string | null
  chosen_hmw?: string | null
  completed_at?: string
  summary?: string
}

interface FirstDiamondCompletedBannerProps {
  output: FirstDiamondOutput | null | undefined
  onBackToLobby?: () => void
  className?: string
}

export function FirstDiamondCompletedBanner({
  output,
  onBackToLobby,
  className,
}: FirstDiamondCompletedBannerProps) {
  if (!output) return null

  const chosenHmw = output.chosen_hmw?.trim()
  const personaCount = output.personas?.length ?? 0

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'w-full rounded-xl border border-success/40 bg-success/5 p-5 shadow-sm',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <CheckCircle2
          size={24}
          className="mt-0.5 shrink-0 text-success"
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-text">
            🎉 第一鑽石完成！
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            團隊已走完同理 + 定義階段
            {personaCount > 0 && `，建構了 ${personaCount} 位 Persona`}
            ，並聚焦出一個明確的設計挑戰。
          </p>

          {chosenHmw && (
            <div className="mt-3 rounded-md bg-surface px-4 py-3 border border-border-light">
              <div className="text-xs font-medium text-text-muted uppercase tracking-wide">
                你們聚焦的設計挑戰
              </div>
              <div className="mt-1 whitespace-pre-line text-base font-semibold text-text">
                {chosenHmw}
              </div>
            </div>
          )}

          {output.summary && (
            <p className="mt-3 whitespace-pre-line text-sm text-text">
              {output.summary}
            </p>
          )}

          {onBackToLobby && (
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onBackToLobby}
                className="inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                <ArrowLeft size={14} aria-hidden="true" />
                回到 Lobby
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
