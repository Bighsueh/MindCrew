import { Bot } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Message, SeatRole } from '../../types/models'

interface ChatMessageProps {
  message: Message
  isOwn?: boolean
  seatRole?: SeatRole
}

function parseUTCDate(iso: string): Date {
  if (!iso.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(iso)) {
    return new Date(iso + 'Z')
  }
  return new Date(iso)
}

function formatTime(iso: string): string {
  const d = parseUTCDate(iso)
  return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function ChatMessage({ message, isOwn = false, seatRole }: ChatMessageProps) {
  const isSystem = message.sender_type === 'system'
  const isAI = message.sender_type === 'ai'
  const isSupervisor = seatRole === 'supervisor'

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
          isSupervisor && 'bg-supervisor/15 text-supervisor ring-2 ring-supervisor/30',
          !isSupervisor && isAI && 'bg-accent/15 text-accent',
          !isSupervisor && !isAI && 'bg-accent/15 text-accent',
        )}
      >
        {isAI ? <Bot size={16} /> : (message.sender_name[0]?.toUpperCase() ?? '?')}
      </div>

      {/* Bubble */}
      <div className={cn('flex max-w-[70%] flex-col gap-1', isOwn ? 'items-end' : 'items-start')}>
        {/* Sender name + badges */}
        <div className="flex items-center gap-1.5">
          <span className={cn(
            'text-xs text-text-muted',
            isSupervisor ? 'font-semibold text-supervisor' : 'font-medium',
          )}>
            {message.sender_name}
          </span>
          {isSupervisor && (
            <span className="rounded-sm bg-supervisor/15 px-1 py-0.5 text-xs font-medium text-supervisor">
              組長
            </span>
          )}
          {isAI && (
            <span className="flex items-center gap-0.5 rounded-sm bg-accent/10 px-1 py-0.5 text-xs text-accent">
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
              ? 'rounded-tr-sm bg-accent/10 text-text'
              : isSupervisor
                ? 'rounded-tl-sm border-l-3 border-supervisor bg-supervisor-light text-text'
                : isAI
                  ? 'rounded-tl-sm border-l-2 border-accent/30 bg-secondary/20 text-text'
                  : 'rounded-tl-sm bg-bg-warm text-text',
          )}
        >
          {message.content}
        </div>
      </div>
    </div>
  )
}
