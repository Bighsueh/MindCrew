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
        <div className="rounded-full bg-gray-100 px-4 py-1.5 text-xs text-gray-500">
          📢 {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className={['flex gap-2 mb-3', isOwn ? 'flex-row-reverse' : 'flex-row'].join(' ')}>
      {/* Avatar */}
      <div
        className={[
          'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm',
          isAI ? 'bg-violet-100 text-violet-700' : 'bg-blue-100 text-blue-700',
        ].join(' ')}
      >
        {isAI ? '🤖' : message.sender_name[0]?.toUpperCase() ?? '?'}
      </div>

      {/* Bubble */}
      <div className={['flex max-w-[70%] flex-col gap-1', isOwn ? 'items-end' : 'items-start'].join(' ')}>
        {/* Sender name */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-gray-600">{message.sender_name}</span>
          {isAI && (
            <span className="rounded-sm bg-violet-100 px-1 py-0.5 text-xs text-violet-600">
              AI
            </span>
          )}
          <span className="text-xs text-gray-400">{formatTime(message.created_at)}</span>
        </div>

        {/* Content */}
        <div
          className={[
            'rounded-2xl px-4 py-2 text-sm leading-relaxed',
            isOwn
              ? 'rounded-tr-sm bg-blue-600 text-white'
              : isAI
                ? 'rounded-tl-sm bg-violet-50 text-gray-800 border border-violet-200'
                : 'rounded-tl-sm bg-gray-100 text-gray-800',
          ].join(' ')}
        >
          {message.content}
        </div>
      </div>
    </div>
  )
}
