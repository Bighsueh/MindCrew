// 教師儀表板 mount 後 per-session 自動啟動 driver.js 漫遊

import { useEffect } from 'react'
import {
  startTeacherDashboardTour,
  hasShownTeacherDashboardTour,
} from './teacherDashboardTour'

interface Options {
  /** 等資料載入完 + 進場動畫穩定再啟動。 */
  delayMs?: number
  /** 仍在 loading 時建議延後啟動。 */
  isLoading?: boolean
}

export function useTeacherDashboardTourAutoStart({
  delayMs = 400,
  isLoading = false,
}: Options = {}): void {
  useEffect(() => {
    if (isLoading) return
    if (hasShownTeacherDashboardTour()) return

    const timer = window.setTimeout(() => {
      startTeacherDashboardTour()
    }, delayMs)

    return () => window.clearTimeout(timer)
  }, [isLoading, delayMs])
}
