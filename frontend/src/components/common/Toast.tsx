import { useEffect } from 'react'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

type ToastVariant = 'info' | 'error' | 'success'

interface ToastProps {
  message: string
  variant?: ToastVariant
  onClose: () => void
  /** 自動關閉毫秒數；預設 5 秒。 */
  autoCloseMs?: number
}

const VARIANT_STYLES: Record<ToastVariant, string> = {
  info: 'bg-surface border-border text-text',
  error: 'bg-red-50 border-red-300 text-red-800',
  success: 'bg-green-50 border-green-300 text-green-800',
}

/**
 * 輕量級頂部置中 toast。無全域佇列，單純依 props 顯示；自動關閉並支援手動關閉。
 * 用於跨頁提示（如 lobby 無權限導回專案列表後的說明）。
 */
export function Toast({
  message,
  variant = 'info',
  onClose,
  autoCloseMs = 5000,
}: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, autoCloseMs)
    return () => clearTimeout(timer)
  }, [onClose, autoCloseMs])

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'fixed left-1/2 top-6 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl border px-4 py-3 shadow-lg',
        VARIANT_STYLES[variant],
      )}
    >
      <span className="text-sm font-medium">{message}</span>
      <button
        type="button"
        onClick={onClose}
        aria-label="關閉"
        className="opacity-60 transition-opacity hover:opacity-100"
      >
        <X size={16} />
      </button>
    </div>
  )
}
