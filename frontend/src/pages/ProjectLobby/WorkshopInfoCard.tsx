import { cn } from '../../lib/utils'
import type { Project } from '../../types/models'

const AI_LABELS: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

// Phase 28：輪流規則 → 友善文案。
const TURN_LABELS: Record<string, string> = {
  cued: '點名發言',
  round_robin: '輪流發言',
  open_floor: '自由發言',
}

const GRID_COLS: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-2',
  3: 'grid-cols-3',
}

interface Stat {
  label: string
  value: string
}

interface WorkshopInfoCardProps {
  project: Project
}

/**
 * 大廳「工作坊資訊」卡（UI/UX v4.24 重設計）。
 *
 * 設計取捨：
 * - 主題與 H1 標題相同時不重複顯示（避免冗餘）；不同時才列出。
 * - 設計限制為主要脈絡，置於上方。
 * - 設定項（AI 貢獻度 / 團隊組成 / 發言方式）改為乾淨的 stat 三欄帶，
 *   取代原本低對比、字多的 pill chips。
 */
export function WorkshopInfoCard({ project }: WorkshopInfoCardProps) {
  const aiLabel = AI_LABELS[project.ai_contribution] ?? project.ai_contribution

  // AI 組員數 = 既非 supervisor 也非真人專屬席的常駐 crew。
  const crewCount = (project.seats ?? []).filter(
    (s) => s.seat_role !== 'supervisor' && s.seat_role !== 'human_creator',
  ).length

  const turnLabel = project.turn_policy
    ? (TURN_LABELS[project.turn_policy] ?? null)
    : null

  const topic =
    project.description && project.description.trim() !== project.name.trim()
      ? project.description.trim()
      : null

  const stats: Stat[] = [
    { label: 'AI 貢獻度', value: aiLabel },
    ...(crewCount > 0
      ? [{ label: '團隊組成', value: `1 組長＋${crewCount} AI` }]
      : []),
    ...(turnLabel ? [{ label: '發言方式', value: turnLabel }] : []),
  ]

  return (
    <section className="rounded-2xl bg-surface p-5 shadow-md">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        工作坊資訊
      </h2>

      {topic && (
        <p className="mt-2 text-lg font-semibold leading-snug text-text">
          {topic}
        </p>
      )}

      {project.constraints && (
        <div className={cn(topic ? 'mt-4' : 'mt-3')}>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
            設計限制
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">
            {project.constraints}
          </p>
        </div>
      )}

      <dl
        className={cn(
          'mt-4 grid divide-x divide-border-light overflow-hidden rounded-xl border border-border-light',
          GRID_COLS[stats.length] ?? 'grid-cols-3',
        )}
      >
        {stats.map((s) => (
          <div key={s.label} className="px-3 py-3 text-center">
            <dt className="text-[11px] text-text-muted">{s.label}</dt>
            <dd className="mt-0.5 text-sm font-semibold text-text">{s.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
