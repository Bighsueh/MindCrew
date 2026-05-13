// ProjectsPage 首次進入時自動觸發 driver.js 漫遊
// session 範圍：每個瀏覽器分頁只跑一次

import { useEffect } from 'react'
import {
  startProjectsTour,
  hasShownProjectsTour,
  type ProjectsTourRole,
} from './projectsTour'

interface Options {
  role: ProjectsTourRole | undefined | null
  /** 等 DOM mount 完成 + 任何進場動畫穩定後再啟動。預設 400ms。 */
  delayMs?: number
}

export function useProjectsTourAutoStart({ role, delayMs = 400 }: Options): void {
  useEffect(() => {
    if (!role) return
    if (hasShownProjectsTour()) return

    const timer = window.setTimeout(() => {
      startProjectsTour(role)
    }, delayMs)

    return () => window.clearTimeout(timer)
  }, [role, delayMs])
}
