import { Users } from 'lucide-react'
import type { Stakeholder } from '../../types/models'

/**
 * Phase 27：Lobby 的「設定的利害關係人」面板。
 *
 * - 空陣列（舊 project）→ 直接 return null，避免顯示空狀態
 * - 顯示建立 project 時使用者勾選的 stakeholders（read-only）
 */
interface Props {
  stakeholders: Stakeholder[]
}

export function StakeholderPanel({ stakeholders }: Props) {
  if (stakeholders.length === 0) return null

  return (
    <section className="mt-6 rounded-2xl border border-border-light bg-surface p-5 shadow-sm">
      <header className="mb-3 flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10 text-accent">
          <Users size={14} />
        </div>
        <h2 className="text-base font-semibold text-text">設定的利害關係人</h2>
        <span className="text-xs text-text-muted">
          建立設計專案時勾選 · 共 {stakeholders.length} 位
        </span>
      </header>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
        {stakeholders.map((s) => (
          <div
            key={s.id}
            className="flex flex-col gap-1 rounded-xl border border-border-light bg-bg-warm/30 p-3"
          >
            <div className="text-sm font-semibold text-text">{s.name}</div>
            <div className="text-xs text-text-muted">{s.role}</div>
            {s.relevance && (
              <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                {s.relevance}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
