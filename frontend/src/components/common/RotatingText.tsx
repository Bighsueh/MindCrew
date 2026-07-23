import { useEffect, useState } from 'react'
import { cn } from '../../lib/utils'
import { useReducedMotion } from '../../hooks/useReducedMotion'

interface RotatingTextProps {
  phrases: string[]
  /** 每個 phrase 停留的毫秒數，預設 1500 */
  interval?: number
  /** 固定前綴，不參與輪替 */
  prefix?: string
  className?: string
}

export function RotatingText({
  phrases,
  interval = 1500,
  prefix,
  className,
}: RotatingTextProps) {
  const [index, setIndex] = useState(0)
  const reduced = useReducedMotion()

  useEffect(() => {
    if (reduced || phrases.length <= 1) return
    const id = setInterval(() => {
      setIndex((prev) => (prev + 1) % phrases.length)
    }, interval)
    return () => clearInterval(id)
  }, [phrases.length, interval, reduced])

  const current = reduced ? phrases[phrases.length - 1] : phrases[index]

  return (
    <span className={cn('inline-flex items-baseline gap-1 overflow-hidden', className)}>
      {prefix && <span className="shrink-0">{prefix}</span>}
      {/* key 變化時 React 重新 mount，觸發 animate-text-rotate-in */}
      <span
        key={reduced ? 'static' : index}
        className={cn(
          'inline-block',
          !reduced && 'animate-text-rotate-in',
        )}
      >
        {current}
      </span>
    </span>
  )
}
