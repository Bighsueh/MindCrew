import { useEffect } from 'react'
import type { SeatRole } from '../types/models'

/**
 * Phase 28 /  — 被 cue 時的視覺通知。
 *
 * 收到 WS `cue` event 且 `target_seat_id === mySeatRole` 時：
 *   - 派發 CustomEvent('mindcrew:cue') 讓 ChatPanel banner + ChatInput
 *     邊框閃爍可監聽 (跨元件低耦合溝通)
 *   - 若 Notification.permission === 'granted'，跳桌面通知
 *
 * 訂閱端用 ``window.addEventListener('mindcrew:cue', handler)`` 聽事件，
 * 不必直接依賴此 hook。
 */
export const CUE_EVENT_NAME = 'mindcrew:cue'

export interface CueEventDetail {
  target_seat_role: SeatRole
  from_seat_role: SeatRole
  timestamp: string
}

export function dispatchCueNotification(detail: CueEventDetail): void {
  window.dispatchEvent(new CustomEvent<CueEventDetail>(CUE_EVENT_NAME, { detail }))

  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    try {
      new Notification('MindCrew', {
        body: '輪到你發言了',
        tag: 'mindcrew-cue', // 同類通知互相覆蓋,不堆疊
      })
    } catch {
      // ignore — best-effort
    }
  }
}

/**
 * 訂閱 cue 事件。回 callback ref 給呼叫端用來判斷現在是否處於 cue 高亮狀態。
 */
export function useCueNotification(
  mySeatRole: SeatRole | null | undefined,
  onCued: (detail: CueEventDetail) => void,
): void {
  useEffect(() => {
    if (!mySeatRole) return
    const handler = (event: Event) => {
      const custom = event as CustomEvent<CueEventDetail>
      if (custom.detail?.target_seat_role === mySeatRole) {
        onCued(custom.detail)
      }
    }
    window.addEventListener(CUE_EVENT_NAME, handler)
    return () => window.removeEventListener(CUE_EVENT_NAME, handler)
  }, [mySeatRole, onCued])
}

/** 對外暴露一個 helper：請求桌面通知權限（在使用者點按下時呼叫一次）。 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (typeof Notification === 'undefined') return 'denied'
  if (Notification.permission === 'granted' || Notification.permission === 'denied') {
    return Notification.permission
  }
  try {
    return await Notification.requestPermission()
  } catch {
    return 'denied'
  }
}
