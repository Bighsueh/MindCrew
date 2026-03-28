import { useState, useRef, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { cn } from '../../lib/utils'

interface ChatInputProps {
  onSend: (content: string) => void
  onTypingStart?: () => void
  onTypingStop?: () => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  onSend,
  onTypingStart,
  onTypingStop,
  disabled = false,
  placeholder = '輸入訊息…（Enter 送出，Shift+Enter 換行）',
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const typingRef = useRef(false)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)

    if (!typingRef.current) {
      typingRef.current = true
      onTypingStart?.()
    }

    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(() => {
      typingRef.current = false
      onTypingStop?.()
    }, 2000)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return

    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    if (typingRef.current) {
      typingRef.current = false
      onTypingStop?.()
    }

    onSend(trimmed)
    setValue('')
  }

  return (
    <div className="flex gap-2 border-t border-border p-3">
      <textarea
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={2}
        className={cn(
          'flex-1 resize-none rounded-lg border border-border px-3 py-2 text-sm bg-surface text-text',
          'focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent',
          'placeholder:text-text-muted',
          'disabled:bg-surface-hover disabled:cursor-not-allowed',
        )}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className={cn(
          'flex-shrink-0 flex items-center justify-center rounded-lg px-4 py-2',
          'bg-accent text-white hover:bg-accent/90',
          'disabled:opacity-40 disabled:cursor-not-allowed',
          'transition-colors cursor-pointer',
        )}
        aria-label="送出"
      >
        <Send size={16} />
      </button>
    </div>
  )
}
