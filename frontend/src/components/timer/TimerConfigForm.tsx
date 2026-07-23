/**
 * TimerConfigForm — 抽自 CreateProjectDialog（）。
 *
 * 用於：建立專案 step 1 / 舊專案啟用 timer dialog。
 * 對應後端 backend/app/timer/calculator.py DEFAULT_2HR_PRESET / PRESET_4HR
 * 與 backend/app/timer/schemas.py::TimerConfig（total_session_minutes ge=30, le=720）。
 */

import { useEffect, useMemo } from 'react'
import { Lock } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { TimerConfigInput } from '../../types/api'

// Phase 29 (spec/16-timer-system §2.1): develop / deliver removed; budgets
// reallocated entirely to the first diamond.
// Phase 39 (spec/16 §2.1 v1.1): 新增 40/60/90 分短場 preset；都跑完整第一鑽石，
// intensity 把便條張數/深度等比變輕（後端 timer/scaling.py 套用）。
type PresetKey =
  | 'timer_preset_40min'
  | 'timer_preset_60min'
  | 'timer_preset_90min'

// Phase 42 B1 (spec/16 §2.1 v2.0)：暖場固定「軟 3／硬 5 分」、所有 preset（含 custom）
// 相同——macro_budgets.warmup 一律 5（硬上限）；後端 initialize_project 亦會強制覆寫。
// 剩餘 total−5 依 discover:define ≈ 60:40 分配（與後端 calculator.py 鏡像同步）。
const TIMER_PRESETS: Record<PresetKey, TimerConfigInput> = {
  timer_preset_40min: {
    total_session_minutes: 40,
    intensity: 0.4,
    macro_budgets: { warmup: 5, discover: 21, define: 14 },
    preset_id: 'timer_preset_40min',
  },
  timer_preset_60min: {
    total_session_minutes: 60,
    intensity: 0.55,
    macro_budgets: { warmup: 5, discover: 33, define: 22 },
    preset_id: 'timer_preset_60min',
  },
  timer_preset_90min: {
    total_session_minutes: 90,
    intensity: 0.8,
    macro_budgets: { warmup: 5, discover: 51, define: 34 },
    preset_id: 'timer_preset_90min',
  },
}

export type TimerMode =
  | 'preset_40min'
  | 'preset_60min'
  | 'preset_90min'
  | 'custom'
type MacroPhaseKey = 'discover' | 'define'

// Phase 42 補正 R2（裁定②）：教師面一併去英文階段代號（spec 28 §6 口徑）。
const MACRO_PHASE_LABELS: { key: MacroPhaseKey; label: string; hint: string }[] = [
  { key: 'discover', label: '發現', hint: '發散' },
  { key: 'define', label: '定義', hint: '收斂' },
]

interface TimerConfigFormProps {
  mode: TimerMode
  customMacroBudgets: { discover: number; define: number }
  onModeChange: (mode: TimerMode) => void
  onCustomChange: (next: TimerConfigFormProps['customMacroBudgets']) => void
  onValidityChange?: (valid: boolean) => void
  /** Phase 43（spec/29）：study 模式下停用 preset 切換 */
  disabled?: boolean
  /** Phase 43：鎖定後於標籤旁顯示 🔒 */
  locked?: boolean
}

export function TimerConfigForm({
  mode,
  customMacroBudgets,
  onModeChange,
  onCustomChange,
  onValidityChange,
  disabled = false,
  locked = false,
}: TimerConfigFormProps) {
  // Phase 42 B1：暖場固定 5 分（硬上限），custom 也不可調——合計含這固定 5 分。
  const customTotalMinutes =
    customMacroBudgets.discover +
    customMacroBudgets.define +
    5

  const isValid = mode !== 'custom' || customTotalMinutes >= 30

  useEffect(() => {
    onValidityChange?.(isValid)
  }, [isValid, onValidityChange])

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-text">
        ⏱ 時間配置
        {locked && (
          <Lock
            size={12}
            className="ml-1 inline-block align-middle text-text-muted"
            aria-label="實驗設定已鎖定"
          />
        )}
      </label>
      <p className="text-xs text-text-muted">
        設定整場工作坊及每個階段的時間預算。AI 會依時間壓力調整發散/收斂策略。
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          { value: 'preset_40min' as const, label: '40 分', desc: '快速體驗 · 完整流程' },
          { value: 'preset_60min' as const, label: '60 分', desc: '一節課 · 完整流程' },
          { value: 'preset_90min' as const, label: '90 分', desc: '標準課堂 · 完整流程' },
          { value: 'custom' as const, label: '自訂', desc: '個別設定階段預算' },
        ].map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onModeChange(opt.value)}
            className={cn(
              'flex-1 rounded-lg border p-3 text-left text-sm transition-all cursor-pointer disabled:cursor-not-allowed',
              mode === opt.value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-surface text-text-muted hover:border-primary/40 hover:bg-primary/5',
              disabled && mode !== opt.value && 'opacity-40',
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
            <span className="ml-1 opacity-80">（含固定暖場 5 分）</span>
            <span className="ml-2 opacity-80">（限制：30–720 分鐘）</span>
            {customTotalMinutes < 30 && (
              <span className="ml-2 font-medium">⚠ 總時間需 ≥ 30 分鐘</span>
            )}
          </div>
        </div>
      )}

      {mode !== 'custom' && (
        <div className="rounded-md bg-bg-warm/60 px-3 py-2 text-xs text-text-muted">
          暖場 軟 3／硬 5 分（固定） · 發現{' '}
          {TIMER_PRESETS[`timer_${mode}`].macro_budgets.discover} 分 · 定義{' '}
          {TIMER_PRESETS[`timer_${mode}`].macro_budgets.define} 分
          {(TIMER_PRESETS[`timer_${mode}`].intensity ?? 1) < 1 && (
            <span className="ml-2 opacity-80">
              （短場：完整流程，便條張數依時長等比變輕）
            </span>
          )}
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
  if (mode === 'preset_40min') return TIMER_PRESETS.timer_preset_40min
  if (mode === 'preset_60min') return TIMER_PRESETS.timer_preset_60min
  if (mode === 'preset_90min') return TIMER_PRESETS.timer_preset_90min
  // Phase 42 B1：custom 也帶固定暖場 5 分（後端 initialize_project 仍會強制覆寫，雙保險）。
  const total = customMacroBudgets.discover + customMacroBudgets.define + 5
  return {
    total_session_minutes: total,
    macro_budgets: { warmup: 5, ...customMacroBudgets },
    preset_id: 'custom',
  }
}

/** 預設 custom budget（與 2hr preset 一致；Phase 29 第一鑽石）。 */
export const DEFAULT_CUSTOM_BUDGETS = {
  discover: 70,
  define: 50,
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
    const total = customMacroBudgets.discover + customMacroBudgets.define
    return total >= 30
  }, [mode, customMacroBudgets])
}
