/**
 * Phase advance tour —  + UX 改動 2026-05-11。
 *
 * 當 stage / micro_phase 切換時，自動跑兩步 driver.js spotlight：
 *   1. 把 navbar 上「新 current stage 的 chip」打亮，說明這個階段要做什麼（白話）
 *   2. 把 footer 上的 timer 打亮，說明時間預算已重設、現在剩多久
 *
 * 觸發點：`useWorkspaceWS.ts` 收到 `stage_changed` 或 `micro_phase_changed` 時。
 * 設計考量：
 *   - 不在初次 mount 時 fire（避免每次進工作區都被 tour 打斷）
 *   - allowClose + esc 關閉，避免擋使用者操作
 *   - overlayOpacity 比 onboarding tour 低，更輕量
 */

import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import type { DTStage, MicroPhaseId } from '../../types/models'
import { MACRO_BY_STAGE } from '../progress/microPhaseInfo'

interface PhaseAdvanceTourOptions {
  toStage: DTStage
  toMicroPhase?: MicroPhaseId | null
  /** 若知道新 phase 的 budget（分鐘）就帶進來，會出現在 timer popover；省略則只說「已重設」。 */
  budgetMinutes?: number | null
}

let activeDriver: ReturnType<typeof driver> | null = null

export function triggerPhaseAdvanceTour({
  toStage,
  toMicroPhase,
  budgetMinutes,
}: PhaseAdvanceTourOptions): void {
  // completed 階段不做 tour
  if (toStage === 'completed') return

  // 找 macro meta 抓白話描述
  const macroKey = toStage as Exclude<DTStage, 'completed'>
  const macro = MACRO_BY_STAGE[macroKey]
  if (!macro) return

  const microMeta = toMicroPhase
    ? macro.micro.find((m) => m.id === toMicroPhase)
    : null

  const stageChipSelector = `[data-tour-stage-chip="${toStage}"]`
  const timerSelector = '[data-tour-timer]'

  // 預先取消舊的 tour，避免重疊
  if (activeDriver) {
    try {
      activeDriver.destroy()
    } catch {
      /* ignore */
    }
  }

  const stageDesc = microMeta
    ? `<strong>${macro.label}</strong><br/>` +
      `現在這一步：<strong>${microMeta.label}</strong><br/>` +
      `<span style="color:#666">${microMeta.description}</span>`
    : `<strong>${macro.label}</strong><br/>` +
      `<span style="color:#666">${macro.summary}</span>`

  const timerDesc =
    `時間預算已重設為新階段的額度。` +
    (budgetMinutes ? `這一步預算 <strong>${budgetMinutes} 分鐘</strong>。` : '') +
    `<br/><span style="color:#666">時間越緊，AI 組長越會推大家加快收斂——聚焦重點、挑出關鍵、把結論收尾。</span>`

  activeDriver = driver({
    showProgress: true,
    allowClose: true,
    doneBtnText: '我懂了',
    nextBtnText: '下一步 →',
    prevBtnText: '← 上一步',
    progressText: '{{current}} / {{total}}',
    showButtons: ['next', 'previous', 'close'],
    overlayOpacity: 0.4,
    stagePadding: 6,
    stageRadius: 12,
    smoothScroll: true,
    onDestroyed: () => {
      activeDriver = null
    },
    steps: [
      {
        element: stageChipSelector,
        popover: {
          title: '階段切換',
          description: stageDesc,
          side: 'bottom',
          align: 'center',
        },
      },
      {
        element: timerSelector,
        popover: {
          title: '時間重設了',
          description: timerDesc,
          side: 'top',
          align: 'center',
        },
      },
    ],
  })

  // 等 DOM 更新完再 drive（micro_phase_changed 同 tick 內 store update + re-render）
  setTimeout(() => {
    try {
      activeDriver?.drive()
    } catch {
      /* ignore — element 可能還沒掛上 */
    }
  }, 100)
}
