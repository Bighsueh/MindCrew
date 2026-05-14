/**
 * TimerConfigForm — 抽自 CreateProjectDialog（specs/16-timer-system.md）。
 *
 * 用於：建立專案 step 1 / 舊專案啟用 timer dialog。
 * 對應後端 backend/app/timer/calculator.py DEFAULT_2HR_PRESET / PRESET_4HR
 * 與 backend/app/timer/schemas.py::TimerConfig（total_session_minutes ge=30, le=720）。
 */

import { useEffect, useMemo } from 'react'
import { cn } from '../../lib/utils'
import type { TimerConfigInput } from '../../types/api'

const TIMER_PRESETS: Record<'timer_preset_2hr' | 'timer_preset_4hr', TimerConfigInput> = {
  timer_preset_2hr: {
    total_session_minutes: 120,
    macro_budgets: { discover: 45, define: 30, develop: 25, deliver: 20 },
    preset_id: 'timer_preset_2hr',
  },
  timer_preset_4hr: {
    total_session_minutes: 240,
    macro_budgets: { discover: 90, define: 60, develop: 50, deliver: 40 },
    preset_id: 'timer_preset_4hr',
  },
}

export type TimerMode = 'preset_2hr' | 'preset_4hr' | 'custom'
type MacroPhaseKey = 'discover' | 'define' | 'develop' | 'deliver'

const MACRO_PHASE_LABELS: { key: MacroPhaseKey; label: string; hint: string }[] = [
  { key: 'discover', label: 'Discover', hint: '發現（發散）' },
  { key: 'define', label: 'Define', hint: '定義（收斂）' },
  { key: 'develop', label: 'Develop', hint: '發展（發散）' },
  { key: 'deliver', label: 'Deliver', hint: '交付（收斂）' },
]

interface TimerConfigFormProps {
  mode: TimerMode
  customMacroBudgets: { discover: number; define: number; develop: number; deliver: number }
  onModeChange: (mode: TimerMode) => void
  onCustomChange: (next: TimerConfigFormProps['customMacroBudgets']) => void
  onValidityChange?: (valid: boolean) => void
}

export function TimerConfigForm({
  mode,
  customMacroBudgets,
  onModeChange,
  onCustomChange,
  onValidityChange,
}: TimerConfigFormProps) {
  const customTotalMinutes =
    customMacroBudgets.discover +
    customMacroBudgets.define +
    customMacroBudgets.develop +
    customMacroBudgets.deliver

  const isValid = mode !== 'custom' || customTotalMinutes >= 30

  useEffect(() => {
    onValidityChange?.(isValid)
  }, [isValid, onValidityChange])

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-text">⏱ 時間配置</label>
      <p className="text-xs text-text-muted">
        設定整場工作坊及每個階段的時間預算。AI 會依時間壓力調整發散/收斂策略。
      </p>
      <div className="flex gap-2">
        {[
          { value: 'preset_2hr' as const, label: '2 小時', desc: '120 分鐘 · 標準工作坊' },
          { value: 'preset_4hr' as const, label: '4 小時', desc: '240 分鐘 · 深度工作坊' },
          { value: 'custom' as const, label: '自訂', desc: '個別設定四個階段' },
        ].map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onModeChange(opt.value)}
            className={cn(
              'flex-1 rounded-lg border p-3 text-left text-sm transition-all cursor-pointer',
              mode === opt.value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
            )}
          >
            <div className="font-semibold">{opt.label}</div>
            <div className="mt-0.5 text-xs opacity-70">{opt.desc}</div>
          </button>
        ))}
      </div>

      {mode === 'custom' && (
        <div className="mt-1 flex flex-col gap-2 rounded-lg border border-border-light bg-bg-warm/30 p-3">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {MACRO_PHASE_LABELS.map((phase) => (
              <div key={phase.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-text">
                  {phase.label}
                  <span className="ml-1 text-[10px] text-text-muted">{phase.hint}</span>
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min={5}
                    max={300}
                    step={5}
                    value={customMacroBudgets[phase.key]}
                    onChange={(e) =>
                      onCustomChange({
                        ...customMacroBudgets,
                        [phase.key]: Math.max(5, Math.min(300, Number(e.target.value) || 0)),
                      })
                    }
                    className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-text focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                  />
                  <span className="text-xs text-text-muted">分</span>
                </div>
              </div>
            ))}
          </div>
          <div
            className={cn(
              'rounded-md px-2 py-1.5 text-xs',
              customTotalMinutes < 30 ? 'bg-error-bg text-error' : 'bg-bg/60 text-text-muted',
            )}
          >
            合計：
            <span className="font-semibold text-text">{customTotalMinutes} 分鐘</span>
            <span className="ml-2 opacity-80">（限制：30–720 分鐘）</span>
            {customTotalMinutes < 30 && (
              <span className="ml-2 font-medium">⚠ 總時間需 ≥ 30 分鐘</span>
            )}
          </div>
        </div>
      )}

      {mode !== 'custom' && (
        <div className="rounded-md bg-bg-warm/60 px-3 py-2 text-xs text-text-muted">
          Discover {TIMER_PRESETS[`timer_${mode}`].macro_budgets.discover} 分 · Define{' '}
          {TIMER_PRESETS[`timer_${mode}`].macro_budgets.define} 分 · Develop{' '}
          {TIMER_PRESETS[`timer_${mode}`].macro_budgets.develop} 分 · Deliver{' '}
          {TIMER_PRESETS[`timer_${mode}`].macro_budgets.deliver} 分
        </div>
      )}
    </div>
  )
}

/** 把 form state 組成送往後端的 timer_config（preset / custom 二選一）。 */
export function buildTimerConfig(
  mode: TimerMode,
  customMacroBudgets: TimerConfigFormProps['customMacroBudgets'],
): TimerConfigInput {
  if (mode === 'preset_2hr') return TIMER_PRESETS.timer_preset_2hr
  if (mode === 'preset_4hr') return TIMER_PRESETS.timer_preset_4hr
  const total =
    customMacroBudgets.discover +
    customMacroBudgets.define +
    customMacroBudgets.develop +
    customMacroBudgets.deliver
  return {
    total_session_minutes: total,
    macro_budgets: customMacroBudgets,
    preset_id: 'custom',
  }
}

/** 預設 custom budget（與 2hr preset 一致）。 */
export const DEFAULT_CUSTOM_BUDGETS = {
  discover: 45,
  define: 30,
  develop: 25,
  deliver: 20,
} as const

// also re-export internal so callers that previously imported from CreateProjectDialog can switch.
export { TIMER_PRESETS }

// satisfies linter: useMemo imported but unused above; export a helper if a caller wants memoized validity.
export function useTimerValidity(
  mode: TimerMode,
  customMacroBudgets: TimerConfigFormProps['customMacroBudgets'],
): boolean {
  return useMemo(() => {
    if (mode !== 'custom') return true
    const total =
      customMacroBudgets.discover +
      customMacroBudgets.define +
      customMacroBudgets.develop +
      customMacroBudgets.deliver
    return total >= 30
  }, [mode, customMacroBudgets])
}
