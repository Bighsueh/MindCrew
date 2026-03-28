import type { AnchorHTMLAttributes, MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { usePageTransition } from '@/hooks/usePageTransition'

interface TransitionLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  readonly to: string
  readonly children: React.ReactNode
}

/**
 * Drop-in replacement for <Link> that plays the Landing → Auth
 * exit animation before navigating.
 *
 * Preserves native behaviour for cmd+click / ctrl+click / right-click.
 */
export function TransitionLink({ to, children, onClick, ...rest }: TransitionLinkProps) {
  const { navigateWithTransition } = usePageTransition()

  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    // Let the browser handle modifier-key clicks (new tab, etc.)
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) {
      return
    }

    // Call external handler first — it can cancel via e.preventDefault()
    onClick?.(e)
    if (e.defaultPrevented) return

    e.preventDefault()
    void navigateWithTransition(to)
  }

  return (
    <Link to={to} onClick={handleClick} {...rest}>
      {children}
    </Link>
  )
}
