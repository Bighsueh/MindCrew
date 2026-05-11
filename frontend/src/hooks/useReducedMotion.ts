import { useEffect, useState } from 'react'

/**
 * 偵測使用者是否啟用「減少動態效果」設定。
 * 重要動畫應呼叫此 hook，確保無障礙性。
 *
 * 用法：
 *   const reduced = useReducedMotion()
 *   if (reduced) return <SimpleVersion />
 */
export function useReducedMotion(): boolean {
  const getInitial = (): boolean => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  const [reduced, setReduced] = useState<boolean>(getInitial)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return reduced
}
