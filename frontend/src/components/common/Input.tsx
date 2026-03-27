import type { InputHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

export function Input({ label, error, helperText, id, className = '', ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium text-text">
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={cn(
          'rounded-md border px-3 py-2.5 text-sm bg-surface text-text',
          'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary',
          'placeholder:text-text-muted',
          'disabled:bg-surface-hover disabled:cursor-not-allowed',
          error
            ? 'border-error focus:ring-error/20 focus:border-error'
            : 'border-border',
          className,
        )}
        {...props}
      />
      {error && <p className="text-xs text-error">{error}</p>}
      {helperText && !error && <p className="text-xs text-text-muted">{helperText}</p>}
    </div>
  )
}
