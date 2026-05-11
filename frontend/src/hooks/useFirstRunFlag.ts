import { useCallback, useEffect, useState } from 'react'

const STORAGE_PREFIX = 'mindcrew.firstrun.'

/**
 * 一次性旗標：給「第一次進入某流程」的指引／呼吸動畫使用。
 * 旗標儲存在 localStorage，跨 session 不再觸發。
 *
 * @param key   邏輯名稱（例如 'workspace-tour'、'stage-bar-bounce'）
 * @returns     [shouldShow, dismiss] — shouldShow=true 代表還沒看過；dismiss() 永久關掉。
 */
export function useFirstRunFlag(key: string): [boolean, () => void] {
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

  return [!seen, dismiss]
}
