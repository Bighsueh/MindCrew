import { useState, useRef, type KeyboardEvent } from 'react'

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
    <div className="flex gap-2 border-t border-gray-200 p-3">
      <textarea
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={2}
        className={[
          'flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm',
          'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
          'disabled:bg-gray-100 disabled:cursor-not-allowed',
        ].join(' ')}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className={[
          'flex-shrink-0 rounded-lg px-4 py-2 text-sm font-medium',
          'bg-blue-600 text-white hover:bg-blue-700',
          'disabled:bg-gray-300 disabled:cursor-not-allowed',
          'transition-colors duration-150',
        ].join(' ')}
      >
        送出
      </button>
    </div>
  )
}
