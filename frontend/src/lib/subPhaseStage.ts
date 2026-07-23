import type { DTStage } from '../types/models'

/**
 * 由 sub_phase 代號推導 macro stage（鏡像後端 `SubPhase.macro_stage` 慣例）。
 * `0.x`→warmup、`1.x`→discover、`2.x`→define；未知/空回 `null`（呼叫端視為 no-op）。
 *
 * 用途：timer_state tick 對 macro stage 做兜底校正。Redis pub/sub 無 replay，單一
 * 一次性的 `stage_changed` 一旦在重連空窗漏接，macro stage 會永久卡住（盲測 2026-06-09：
 * DB=discover 但 UI 停在暖場 40 分）。timer_state 每 ~10s 必達且帶 current_sub_phase，
 * 由它推導 macro stage 即可在一個 tick 內自我校正。
 */
export function macroStageFromSubPhase(
  subId: string | null | undefined,
): DTStage | null {
  if (!subId) return null
  if (subId.startsWith('0.')) return 'warmup'
  if (subId.startsWith('1.')) return 'discover'
  if (subId.startsWith('2.')) return 'define'
  return null
}
