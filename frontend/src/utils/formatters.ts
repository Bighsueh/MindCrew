import type { DTStage } from '../types/models'

export const STAGE_LABELS: Record<DTStage, string> = {
  discover: '🔍 發現',
  define: '📌 定義',
  develop: '💡 發展',
  deliver: '🚀 交付',
  completed: '✅ 完成',
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
