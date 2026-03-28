import { useEffect, useRef, useCallback } from 'react'
import { X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAuthStore } from '../../stores/authStore'
import { useSeatStore } from '../../stores/seatStore'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import type { WSClientMessage } from '../../types/ws'
import type { Seat, SeatRole } from '../../types/models'

interface ChatPanelProps {
  projectId: string
  sendWS: (msg: WSClientMessage) => void
  disabled?: boolean
  onClose?: () => void
}

function getSeatRole(seats: Seat[], senderId: string): SeatRole | undefined {
  return seats.find(s => s.user_id === senderId || s.agent_id === senderId)?.seat_role
}

export function ChatPanel({ projectId, sendWS, disabled = false, onClose }: ChatPanelProps) {
  const { messages, typingUsers, hasMore, isLoading, loadHistory, loadMore } = useChatStore()
  const { user } = useAuthStore()
  const { seats } = useSeatStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  useEffect(() => {
    loadHistory(projectId)
  }, [projectId, loadHistory])

  useEffect(() => {
    if (autoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
    autoScrollRef.current = isNearBottom

    if (el.scrollTop < 50 && hasMore && !isLoading) {
      loadMore(projectId)
    }
  }

  const handleSend = useCallback(
    (content: string) => {
      sendWS({ type: 'chat_message', payload: { content } })
    },
    [sendWS],
  )

  const handleTypingStart = useCallback(() => {
    sendWS({ type: 'typing_start', payload: {} })
  }, [sendWS])

  const handleTypingStop = useCallback(() => {
    sendWS({ type: 'typing_stop', payload: {} })
  }, [sendWS])

  const typingNames = Array.from(typingUsers.values()).map((u) => u.name)

  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-text">聊天室</h3>
        {onClose && (
          <button
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 rounded-md text-text-muted hover:text-text hover:bg-surface-hover transition-colors cursor-pointer"
            aria-label="關閉聊天室"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Message list */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-3"
      >
        {isLoading && (
          <div className="flex justify-center py-2">
            <span className="text-xs text-text-muted">載入中…</span>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            isOwn={msg.sender_id === user?.id}
            seatRole={getSeatRole(seats, msg.sender_id)}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Typing indicator */}
      {typingNames.length > 0 && (
        <div className="px-4 py-1 text-xs text-text-muted italic">
          {typingNames.join('、')} 正在輸入…
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onTypingStart={handleTypingStart}
        onTypingStop={handleTypingStop}
        disabled={disabled}
      />
    </div>
  )
}
