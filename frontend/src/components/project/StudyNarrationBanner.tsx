import { Lock } from 'lucide-react'

/**
 * Phase 43（spec/29 §3.2）：幽靈代填的精靈層級敘事橫幅。
 * 動畫中顯示進行中的動作（pulse 圓點），播畢轉為鎖定完成態（🔒）。
 */
interface StudyNarrationBannerProps {
  narration: string
  isAnimating: boolean
}

export function StudyNarrationBanner({ narration, isAnimating }: StudyNarrationBannerProps) {
  return (
    <div
      className={
        isAnimating
          ? 'flex items-center gap-2 rounded-md bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary'
          : 'flex items-center gap-2 rounded-md bg-success/10 px-4 py-2.5 text-sm font-medium text-success'
      }
      role="status"
      aria-live="polite"
    >
      {isAnimating ? (
        <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-primary" aria-hidden="true" />
      ) : (
        <Lock size={14} className="shrink-0" aria-hidden="true" />
      )}
      {narration}
    </div>
  )
}
