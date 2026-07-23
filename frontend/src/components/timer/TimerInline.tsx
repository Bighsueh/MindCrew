/**
 * TimerInline — Workspace footer 的大型 timer 顯示（「沉穩 pill」設計）。
 *
 * 跟 canvas 上的 `TimerBadge` 共用 `useTimerStore`。視覺重點：
 *   - pill 外框；tight / critical / overtime 時外框轉為壓力色
 *   - 大字剩餘時間（22px）讓老師遠看也清楚，旁附「本關剩餘 · sub_phase」
 *   - 右側壓力小圓點 + 一句鼓勵語（從容 → 最後衝刺）
 *   - 16 格「跑道」進度條，隨時間從右側逐格熄滅
 */

import { cn } from '../../lib/utils'
import {
  formatRemaining,
  getPressureLevel,
  useTimerStore,
  type PressureLevel,
} from '../../stores/timerStore'
import { useCanvasStatsStore } from '../../stores/canvasStatsStore'

// 五階壓力對應的跑道格／圓點底色（同 TimerBadge palette）。
const PRESSURE_BAR_CLASS: Record<PressureLevel, string> = {
  calm: 'bg-green-600',
  halfway: 'bg-amber-500',
  two_thirds: 'bg-orange-500',
  tight: 'bg-red-500',
  critical: 'bg-red-600',
}

// 鼓勵語 / 圓點文字色。
const PRESSURE_TEXT_CLASS: Record<PressureLevel, string> = {
  calm: 'text-green-700',
  halfway: 'text-amber-700',
  two_thirds: 'text-orange-700',
  tight: 'text-red-700',
  critical: 'text-red-800',
}

// tight / critical / overtime 時的外框色。
const PRESSURE_BORDER_CLASS: Record<PressureLevel, string> = {
  calm: 'border-border',
  halfway: 'border-border',
  two_thirds: 'border-border',
  tight: 'border-red-500',
  critical: 'border-red-600',
}

// 依壓力等級給一句口語化提示。
const PRESSURE_PHRASE: Record<PressureLevel, string> = {
  calm: '時間很從容',
  halfway: '進度過半，保持節奏',
  two_thirds: '剩三分之一，開始收尾',
  tight: '快結束囉，先存下重點',
  critical: '最後衝刺！',
}

const RUNWAY_SEGMENTS = 16

interface TimerInlineProps {
  /** 是否為專案建立者（老師）：true 時不可用狀態會顯示「啟用」按鈕。 */
  isCreator?: boolean
  /** 老師按下「啟用倒數計時器」時呼叫。 */
  onActivate?: () => void
}

export function TimerInline({ isCreator = false, onActivate }: TimerInlineProps = {}) {
  const snapshot = useTimerStore((s) => s.snapshot)
  // Phase 42 B1（spec 28 §3.2）：暖場期間（後端帶 warmup_goal）顯示「便條 N／目標 G」。
  const contentNoteCount = useCanvasStatsStore((s) => s.contentNoteCount)

  // 每秒遞減由 workspace 層的 useTimerTick 單一計時源負責（本元件被響應式雙掛，
  // 不可自行計時，否則 tick 每秒被呼叫兩次造成倒數抖動）。本元件純展示。

  // 舊專案（建立時未自動初始化 timer）會收到 available=false。
  // footer 不再整個消失，改顯示啟用入口或等待提示。
  if (!snapshot.available || !snapshot.current_sub_phase) {
    if (isCreator) {
      return (
        <button
          type="button"
          onClick={onActivate}
          data-tour-timer=""
          className={cn(
            'flex items-center gap-2 rounded-full border border-dashed border-primary/50 bg-primary/5 px-4 py-2.5',
            'min-w-[300px] text-sm text-primary hover:bg-primary/10 transition-colors cursor-pointer',
          )}
        >
          <span aria-hidden="true" className="text-lg leading-none">
            ⏱
          </span>
          <span className="flex-1 text-left font-medium">啟用倒數計時器</span>
          <span className="text-xs text-text-muted">點此選擇預設</span>
        </button>
      )
    }
    return (
      <div
        data-tour-timer=""
        className={cn(
          'flex items-center gap-2 rounded-full border border-border bg-bg-warm/40 px-4 py-2.5',
          'min-w-[300px] text-sm text-text-muted',
        )}
      >
        <span aria-hidden="true" className="text-lg leading-none opacity-60">
          ⏱
        </span>
        <span>等待建立者啟用計時器</span>
      </div>
    )
  }

  const pressure = getPressureLevel(snapshot.used_pct)
  const isOvertime = snapshot.used_pct >= 100
  // overtime 比照 critical 呈現（壓力色外框 + 圓點脈動）。
  const level: PressureLevel = isOvertime ? 'critical' : pressure
  const isCritical = level === 'critical' || level === 'tight'
  const subPhaseLabel = snapshot.current_sub_phase_label ?? snapshot.current_sub_phase
  // 剩餘比例（0..1）驅動跑道格：從右側逐格熄滅。
  const remainingRatio =
    snapshot.budget_seconds > 0
      ? Math.max(0, 1 - snapshot.used_seconds / snapshot.budget_seconds)
      : 0

  // 暖場軟目標（spec 28 §3.1）：在跑道上標示「3 分軟目標」、過軟目標後切換副標，
  // 讓組長「延長到五分鐘」話術有可視指涉（spec 05 §5、spec 16 §4.5）。
  const warmupSoft =
    snapshot.warmup_soft_seconds != null && snapshot.warmup_soft_seconds > 0
      ? snapshot.warmup_soft_seconds
      : null
  const showSoftMarker = warmupSoft != null && snapshot.budget_seconds > 0
  // 軟目標在跑道上的位置＝剩餘比例 1 − soft/budget（跑道由左至右代表剩餘 0..1）。
  const softRemainingRatio =
    warmupSoft != null && snapshot.budget_seconds > 0
      ? Math.max(0, Math.min(1, 1 - warmupSoft / snapshot.budget_seconds))
      : 0
  const pastSoft = warmupSoft != null && snapshot.used_seconds >= warmupSoft
  const softMin = warmupSoft != null ? Math.round(warmupSoft / 60) : 0
  const hardMin = Math.round(snapshot.budget_seconds / 60)

  return (
    <div
      role="timer"
      aria-live="off"
      // driver.js phase-advance tour 用這個 attr 找錨點
      data-tour-timer=""
      className={cn(
        'flex items-center gap-3.5 rounded-full border bg-surface py-[7px] pl-4 pr-3 shadow-sm',
        'min-w-[320px]',
        PRESSURE_BORDER_CLASS[level],
      )}
    >
      <span aria-hidden="true" className="shrink-0 text-base leading-none text-text-muted">
        {snapshot.paused ? '⏸' : '⏱'}
      </span>
      <div className="flex flex-1 flex-col gap-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              'tabular-nums text-[22px] font-extrabold leading-none tracking-tight',
              isCritical ? PRESSURE_TEXT_CLASS[level] : 'text-text',
            )}
          >
            {formatRemaining(snapshot.budget_seconds, snapshot.used_seconds)}
          </span>
          {/* spec 16 v2.0 §4.5：明確標示這是「本關」的剩餘時間，不是整場。 */}
          <span className="text-xs font-medium text-text-muted whitespace-nowrap">
            本關剩餘 · {subPhaseLabel}
          </span>
          {/* Phase 42 B1（spec 28 §3.2）：暖場團隊目標即時計數「N／目標」。 */}
          {snapshot.warmup_goal != null && snapshot.warmup_goal > 0 && (
            <span
              className={cn(
                'text-xs font-bold whitespace-nowrap',
                contentNoteCount >= snapshot.warmup_goal
                  ? 'text-green-700'
                  : 'text-text-muted',
              )}
            >
              便條 {contentNoteCount}／目標 {snapshot.warmup_goal}
            </span>
          )}
          <span
            className={cn(
              'ml-auto flex items-center gap-1.5 text-xs font-bold whitespace-nowrap',
              PRESSURE_TEXT_CLASS[level],
            )}
          >
            <span
              className={cn(
                'h-[7px] w-[7px] rounded-full',
                PRESSURE_BAR_CLASS[level],
                isCritical && 'animate-pulse',
              )}
            />
            {PRESSURE_PHRASE[level]}
          </span>
        </div>
        {/* 暖場軟/硬目標副標：過 3 分軟目標前後切換措辭，對齊組長「延長到五分鐘」話術。 */}
        {showSoftMarker && (
          <span className="text-[11px] font-medium text-text-muted whitespace-nowrap">
            {pastSoft
              ? `已過 ${softMin} 分軟目標 · 衝到 ${hardMin} 分`
              : `軟目標 ${softMin} 分 · 上限 ${hardMin} 分`}
          </span>
        )}
        {/* 16 格跑道：每格代表 1/16 預算，剩餘比例不足即熄滅。 */}
        <div className="relative">
          <div className="flex h-[7px] gap-[3px]">
            {Array.from({ length: RUNWAY_SEGMENTS }).map((_, i) => {
              const filled = (i + 1) / RUNWAY_SEGMENTS <= remainingRatio
              return (
                <span
                  key={i}
                  className={cn(
                    'flex-1 rounded-sm transition-colors duration-500',
                    filled ? PRESSURE_BAR_CLASS[level] : 'bg-bg-warm',
                    filled && !isCritical && 'opacity-[0.85]',
                  )}
                />
              )
            })}
          </div>
          {/* 暖場軟目標刻痕：標出 3 分軟目標在跑道上的位置。 */}
          {showSoftMarker && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 h-[12px] w-[2px] -translate-y-1/2 rounded-full bg-text/40"
              style={{ left: `${softRemainingRatio * 100}%` }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
