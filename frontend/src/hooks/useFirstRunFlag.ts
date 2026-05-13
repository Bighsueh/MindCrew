import { useCallback, useEffect, useState } from 'react'

const STORAGE_PREFIX = 'mindcrew.firstrun.'

/**
 * 一次性旗標：給「第一次進入某流程」的指引／呼吸動畫使用。
 * 旗標儲存在 localStorage，跨 session 不再觸發。
 *
 * @param key   邏輯名稱（例如 'workspace-tour'、'stage-bar-bounce'）
 * @returns     [shouldShow, dismiss, reset]
 *              - shouldShow=true 代表還沒看過
 *              - dismiss() 永久關掉
 *              - reset()   清掉 flag，讓首次體驗重來（給「重新導引」按鈕用）
 */
export function useFirstRunFlag(key: string): [boolean, () => void, () => void] {
  const storageKey = STORAGE_PREFIX + key
  const [seen, setSeen] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true
    try {
      return window.localStorage.getItem(storageKey) === '1'
    } catch {
      return true
    }
  })

  const dismiss = useCallback(() => {
    setSeen(true)
    try {
      window.localStorage.setItem(storageKey, '1')
    } catch {
      /* localStorage 不可用時靜默 */
    }
  }, [storageKey])

  // 每次 key 改變時重新檢查（例如不同 user 切換）。
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      setSeen(window.localStorage.getItem(storageKey) === '1')
    } catch {
      setSeen(true)
    }
  }, [storageKey])

  const reset = useCallback(() => {
    setSeen(false)
    try {
      window.localStorage.removeItem(storageKey)
    } catch {
      /* localStorage 不可用時靜默 */
    }
  }, [storageKey])

  return [!seen, dismiss, reset]
}
