import { useEffect, useRef, useState } from 'react'

/** Module-level reduced-motion query — evaluated once, shared by all instances */
const reducedMotionQuery =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null

function prefersReducedMotion(): boolean {
  return reducedMotionQuery?.matches ?? false
}

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
 * Returns a ref to attach, a boolean `isRevealed`, and `isNear` (within 200px).
 *
 * Respects `prefers-reduced-motion` — instantly reveals if motion is reduced.
 */
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>(
  options: UseScrollRevealOptions = {},
) {
  const { threshold = 0.15, rootMargin = '0px 0px -60px 0px', once = true } = options
  const ref = useRef<T>(null)
  const [isRevealed, setIsRevealed] = useState(false)
  const [isNear, setIsNear] = useState(false)

  useEffect(() => {
    if (prefersReducedMotion()) {
      setIsRevealed(true)
      setIsNear(true)
      return
    }

    const el = ref.current
    if (!el) return

    // Proximity observer — fires when element is within 200px of viewport
    const nearObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsNear(true)
          nearObserver.unobserve(el)
        }
      },
      { rootMargin: '200px 0px 200px 0px' },
    )

    // Reveal observer — fires at configured threshold
    const revealObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsRevealed(true)
          if (once) {
            revealObserver.unobserve(el)
          }
        } else if (!once) {
          setIsRevealed(false)
        }
      },
      { threshold, rootMargin },
    )

    nearObserver.observe(el)
    revealObserver.observe(el)

    return () => {
      nearObserver.disconnect()
      revealObserver.disconnect()
    }
  }, [threshold, rootMargin, once])

  return { ref, isRevealed, isNear }
}
