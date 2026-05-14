/**
 * TimerInline — specs/16-timer-system.md §6.5.3。
 *
 * 放在 Workspace footer 的大型 timer 顯示，跟原本 canvas 上的 `TimerBadge`
 * 共用 `useTimerStore`。視覺重點：
 *   - 文字尺寸 text-sm（時間）/ text-base（sub_phase）讓老師遠看也清楚
 *   - 五階壓力等級 chip + 進度條雙重表達壓力
 *   - tight / critical / overtime 加 pulse 動畫吸睛
 */

import { useEffect } from 'react'
import { cn } from '../../lib/utils'
import {
  formatBudget,
  formatRemaining,
  getPressureLabel,
  getPressureLevel,
  useTimerStore,
  type PressureLevel,
} from '../../stores/timerStore'

// 五階壓力對應 chip 顏色 + 進度條顏色（同 TimerBadge palette）。
const PRESSURE_CHIP_CLASS: Record<PressureLevel, string> = {
  calm: 'bg-success/15 text-success',
  halfway: 'bg-amber-100 text-amber-700',
  two_thirds: 'bg-orange-100 text-orange-700',
  tight: 'bg-red-100 text-red-700',
  critical: 'bg-red-200 text-red-800',
}

const PRESSURE_BAR_CLASS: Record<PressureLevel, string> = {
  calm: 'bg-success',
  halfway: 'bg-amber-500',
  two_thirds: 'bg-orange-500',
  tight: 'bg-red-500',
  critical: 'bg-red-600',
}

interface TimerInlineProps {
  /** 是否為專案建立者（老師）：true 時不可用狀態會顯示「啟用」按鈕。 */
  isCreator?: boolean
  /** 老師按下「啟用倒數計時器」時呼叫。 */
  onActivate?: () => void
}

export function TimerInline({ isCreator = false, onActivate }: TimerInlineProps = {}) {
  const snapshot = useTimerStore((s) => s.snapshot)
  const tick = useTimerStore((s) => s.tick)

  useEffect(() => {
    if (!snapshot.available || snapshot.paused) return
    const id = window.setInterval(() => tick(), 1000)
    return () => window.clearInterval(id)
  }, [snapshot.available, snapshot.paused, tick])

  // 舊專案（建立時未自動初始化 timer）會收到 available=false。
  // specs/16-timer-system.md：footer 不再整個消失，改顯示啟用入口或等待提示。
  if (!snapshot.available || !snapshot.current_sub_phase) {
    if (isCreator) {
      return (
        <button
          type="button"
          onClick={onActivate}
          data-tour-timer=""
          className={cn(
            'flex items-center gap-2 rounded-lg border border-dashed border-primary/50 bg-primary/5 px-3 py-2',
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
          'flex items-center gap-2 rounded-lg border border-border bg-bg-warm/40 px-3 py-2',
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
  const shouldPulse = isOvertime || pressure === 'critical' || pressure === 'tight'
  const pct = Math.min(snapshot.used_pct, 100)

  return (
    <div
      role="timer"
      aria-live="off"
      // specs/16-timer-system.md：driver.js phase-advance tour 用這個 attr 找錨點
      data-tour-timer=""
      className={cn(
        'flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2',
        'min-w-[300px]',
        shouldPulse && 'animate-pulse',
      )}
    >
      <span aria-hidden="true" className="text-lg leading-none">
        {snapshot.paused ? '⏸' : '⏱'}
      </span>
      <div className="flex flex-1 flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-text leading-none">
            {snapshot.current_sub_phase}
          </span>
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-xs font-medium',
              PRESSURE_CHIP_CLASS[pressure],
            )}
          >
            {getPressureLabel(pressure)}
          </span>
          <span className="ml-auto tabular-nums text-sm font-semibold text-text">
            {formatRemaining(snapshot.budget_seconds, snapshot.used_seconds)}
            <span className="mx-1 text-text-muted font-normal">/</span>
            <span className="text-text-muted font-normal">
              {formatBudget(snapshot.budget_seconds)}
            </span>
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-warm">
          <div
            className={cn(
              'h-full transition-all duration-500',
              PRESSURE_BAR_CLASS[pressure],
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  )
}
