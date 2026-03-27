import { Bot } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Message } from '../../types/models'

interface ChatMessageProps {
  message: Message
  isOwn?: boolean
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function ChatMessage({ message, isOwn = false }: ChatMessageProps) {
  const isSystem = message.sender_type === 'system'
  const isAI = message.sender_type === 'ai'

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <div className="rounded-full bg-secondary/30 px-4 py-1.5 text-xs text-text-muted">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className={cn('flex gap-2 mb-3', isOwn ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm',
          isAI ? 'bg-primary/10 text-primary' : 'bg-accent/15 text-accent',
        )}
      >
        {isAI ? <Bot size={16} /> : (message.sender_name[0]?.toUpperCase() ?? '?')}
      </div>

      {/* Bubble */}
      <div className={cn('flex max-w-[70%] flex-col gap-1', isOwn ? 'items-end' : 'items-start')}>
        {/* Sender name */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-text-muted">{message.sender_name}</span>
          {isAI && (
            <span className="flex items-center gap-0.5 rounded-sm bg-primary/10 px-1 py-0.5 text-xs text-primary">
              <Bot size={10} />
              AI
            </span>
          )}
          <span className="text-xs text-text-muted">{formatTime(message.created_at)}</span>
        </div>

        {/* Content */}
        <div
          className={cn(
            'rounded-2xl px-4 py-2 text-sm leading-relaxed',
            isOwn
              ? 'rounded-tr-sm bg-primary/10 text-text'
              : isAI
                ? 'rounded-tl-sm bg-secondary/20 text-text'
                : 'rounded-tl-sm bg-primary/10 text-text',
          )}
        >
          {message.content}
        </div>
      </div>
    </div>
  )
}
