import { useEffect, useRef, useState, useCallback } from 'react'

interface UseScrollRevealOptions {
  /** Intersection threshold (0-1). Default: 0.15 */
  readonly threshold?: number
  /** Root margin for earlier/later triggering. Default: '0px 0px -60px 0px' */
  readonly rootMargin?: string
  /** Only trigger once. Default: true */
  readonly once?: boolean
}

/**
 * Hook that tracks whether an element has entered the viewport.
 * Returns a ref to attach and a boolean `isRevealed`.
 *
 * Respects `prefers-reduced-motion` — instantly reveals if motion is reduced.
 */
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>(
  options: UseScrollRevealOptions = {},
) {
  const { threshold = 0.15, rootMargin = '0px 0px -60px 0px', once = true } = options
  const ref = useRef<T>(null)
  const [isRevealed, setIsRevealed] = useState(false)

  // Check reduced motion preference
  const prefersReducedMotion = useCallback(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  useEffect(() => {
    // If reduced motion, reveal immediately
    if (prefersReducedMotion()) {
      setIsRevealed(true)
      return
    }

    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsRevealed(true)
          if (once) {
            observer.unobserve(el)
          }
        } else if (!once) {
          setIsRevealed(false)
        }
      },
      { threshold, rootMargin },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [threshold, rootMargin, once, prefersReducedMotion])

  return { ref, isRevealed }
}
