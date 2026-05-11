import { useEffect, useState } from 'react'

const QUERY = '(orientation: portrait) and (max-width: 1023px)'

export function useDrawerLayout(): boolean {
  const getInitial = (): boolean => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(QUERY).matches
  }

  const [isDrawer, setIsDrawer] = useState<boolean>(getInitial)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia(QUERY)
    const onChange = (e: MediaQueryListEvent) => setIsDrawer(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return isDrawer
}
