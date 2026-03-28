import { Bot, User, Radio } from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatRelativeTime } from '../../utils/formatters'
import type { Message } from '../../types/models'

interface TypingUser {
  name: string
  isTyping: boolean
}

interface LiveActivityFeedProps {
  messages: Message[]
  typingUsers: Map<string, TypingUser>
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'failed'
  embedded?: boolean
}

const STATUS_CONFIG = {
  connected: { label: '即時連線中', className: 'bg-success' },
  connecting: { label: '連線中…', className: 'bg-warning animate-pulse' },
  disconnected: { label: '離線', className: 'bg-text-muted' },
  failed: { label: '連線失敗', className: 'bg-error' },
} as const

export function LiveActivityFeed({
  messages,
  typingUsers,
  wsStatus,
  embedded = false,
}: LiveActivityFeedProps) {
  const statusConfig = STATUS_CONFIG[wsStatus]
  const typingList = Array.from(typingUsers.values()).filter((t) => t.isTyping)

  return (
    <div className={embedded ? '' : 'rounded-xl border border-border bg-surface p-5 shadow-sm'}>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio size={16} className="text-accent" />
          <h3 className="text-sm font-semibold text-text">即時動態</h3>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={cn('h-2 w-2 rounded-full', statusConfig.className)} />
          <span className="text-xs text-text-muted">{statusConfig.label}</span>
        </div>
      </div>

      {/* Messages */}
      <div className="space-y-3">
        {messages.length === 0 && typingList.length === 0 && (
          <p className="py-4 text-center text-sm text-text-muted">尚無對話訊息</p>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className="flex items-start gap-2.5 transition-opacity">
            {/* Avatar */}
            <div
              className={cn(
                'mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full',
                msg.sender_type === 'ai'
                  ? 'bg-accent/15 text-accent'
                  : msg.sender_type === 'system'
                    ? 'bg-info/15 text-info'
                    : 'bg-primary/10 text-primary',
              )}
            >
              {msg.sender_type === 'ai' ? (
                <Bot size={12} />
              ) : (
                <User size={12} />
              )}
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-medium text-text">
                  {msg.sender_name}
                </span>
                <span className="text-xs text-text-muted">
                  {formatRelativeTime(msg.created_at)}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-text-muted line-clamp-2 leading-relaxed">
                {msg.content}
              </p>
            </div>
          </div>
        ))}

        {/* Typing indicators */}
        {typingList.map((t) => (
          <div
            key={t.name}
            className="flex items-center gap-2 text-xs text-text-muted"
          >
            <Bot size={12} className="text-accent" />
            <span>{t.name} 正在思考</span>
            <span className="inline-flex gap-0.5">
              <span className="animate-bounce [animation-delay:0ms]">.</span>
              <span className="animate-bounce [animation-delay:150ms]">.</span>
              <span className="animate-bounce [animation-delay:300ms]">.</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
