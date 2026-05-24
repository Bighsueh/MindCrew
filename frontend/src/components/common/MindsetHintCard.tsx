import type { ReactNode } from 'react'
import { Lightbulb } from 'lucide-react'

/**
 * Phase 27 練功坊：心法卡。
 *
 * 用於 wizard 各步驟頂部 / Lobby 等需要「一句話提示」的位置。
 * 視覺刻意輕量：圖示 + 粗體標題 + 一行 hint，呼應「練功坊心法」的氛圍。
 */
interface MindsetHintCardProps {
  icon?: ReactNode
  title: string
  hint: string
}

export function MindsetHintCard({ icon, title, hint }: MindsetHintCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
        {icon ?? <Lightbulb size={16} />}
      </div>
      <div className="flex flex-col gap-0.5">
        <div className="text-sm font-semibold text-text">{title}</div>
        <p className="text-xs leading-relaxed text-text-muted">{hint}</p>
      </div>
    </div>
  )
}
