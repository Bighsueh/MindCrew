import type { DTStage } from '../types/models'

// Phase 29 (spec/04-06 §4.10): develop / deliver removed.
export const STAGE_LABELS: Record<DTStage, string> = {
  warmup: '🔥 暖場',
  discover: '🔍 發現',
  define: '📌 定義',
  completed: '✅ 完成',
}

/**
 * 無 emoji 的階段中文標籤——給「已有自身 icon 的元件 / aria-label / 緊湊 tag」用。
 * 與 STAGE_LABELS 同為階段標籤的**單一真相來源**；元件不得自帶英文 map（spec 28 §6）。
 */
export const STAGE_LABELS_PLAIN: Record<DTStage, string> = {
  warmup: '暖場',
  discover: '發現',
  define: '定義',
  completed: '完成',
}

/** Parse an ISO string as UTC if it has no timezone suffix. */
function parseUTCDate(iso: string): Date {
  if (!iso.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(iso)) {
    return new Date(iso + 'Z')
  }
  return new Date(iso)
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - parseUTCDate(iso).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return '剛剛'
  if (minutes < 60) return `${minutes} 分鐘前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小時前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  const months = Math.floor(days / 30)
  return `${months} 個月前`
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`
  const mins = Math.floor(seconds / 60)
  if (mins < 60) return `${mins} 分鐘`
  const hrs = Math.floor(mins / 60)
  const remMins = mins % 60
  return remMins > 0 ? `${hrs} 小時 ${remMins} 分鐘` : `${hrs} 小時`
}
