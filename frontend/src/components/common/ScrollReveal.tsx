import { type ReactNode, type CSSProperties } from 'react'
import { useScrollReveal } from '@/hooks/useScrollReveal'

type AnimationVariant =
  | 'fade-up'
  | 'fade-down'
  | 'fade-left'
  | 'fade-right'
  | 'scale-in'
  | 'fade'

interface ScrollRevealProps {
  readonly children: ReactNode
  /** Animation variant. Default: 'fade-up' */
  readonly variant?: AnimationVariant
  /** Delay in ms before animation starts. Default: 0 */
  readonly delay?: number
  /** Animation duration in ms. Default: 600 */
  readonly duration?: number
  /** Additional className */
  readonly className?: string
  /** HTML tag to render. Default: 'div' */
  readonly as?: keyof JSX.IntrinsicElements
  /** Intersection threshold. Default: 0.15 */
  readonly threshold?: number
}

const VARIANT_STYLES: Record<AnimationVariant, CSSProperties> = {
  'fade-up': { opacity: 0, transform: 'translateY(32px)' },
  'fade-down': { opacity: 0, transform: 'translateY(-32px)' },
  'fade-left': { opacity: 0, transform: 'translateX(-32px)' },
  'fade-right': { opacity: 0, transform: 'translateX(32px)' },
  'scale-in': { opacity: 0, transform: 'scale(0.92)' },
  'fade': { opacity: 0, transform: 'none' },
}

const REVEALED_STYLE: CSSProperties = {
  opacity: 1,
  transform: 'none',
}

export function ScrollReveal({
  children,
  variant = 'fade-up',
  delay = 0,
  duration = 600,
  className = '',
  as: Tag = 'div',
  threshold = 0.15,
}: ScrollRevealProps) {
  const { ref, isRevealed } = useScrollReveal({ threshold })

  const style: CSSProperties = {
    ...(isRevealed ? REVEALED_STYLE : VARIANT_STYLES[variant]),
    transitionProperty: 'opacity, transform',
    transitionDuration: `${duration}ms`,
    transitionTimingFunction: 'var(--ease-out)',
    transitionDelay: `${delay}ms`,
    willChange: isRevealed ? 'auto' : 'opacity, transform',
  }

  // Using a type assertion since `as` prop with dynamic tags is hard to type perfectly
  const Element = Tag as 'div'

  return (
    <Element ref={ref as React.Ref<HTMLDivElement>} className={className} style={style}>
      {children}
    </Element>
  )
}
