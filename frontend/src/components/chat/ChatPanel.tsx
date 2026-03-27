import { useEffect, useRef, useCallback } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAuthStore } from '../../stores/authStore'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import type { WSClientMessage } from '../../types/ws'

interface ChatPanelProps {
  projectId: string
  sendWS: (msg: WSClientMessage) => void
  disabled?: boolean
}

export function ChatPanel({ projectId, sendWS, disabled = false }: ChatPanelProps) {
  const { messages, typingUsers, hasMore, isLoading, loadHistory, loadMore } = useChatStore()
  const { user } = useAuthStore()
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
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="border-b border-gray-200 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-700">💬 聊天室</h3>
      </div>

      {/* Message list */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-3"
      >
        {isLoading && (
          <div className="flex justify-center py-2">
            <span className="text-xs text-gray-400">載入中…</span>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            isOwn={msg.sender_id === user?.id}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Typing indicator */}
      {typingNames.length > 0 && (
        <div className="px-4 py-1 text-xs text-gray-500 italic">
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
