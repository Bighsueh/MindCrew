import { useEffect, useRef, useCallback, useMemo, useState, type ReactNode } from 'react'
import { X, Bell } from 'lucide-react'
import { useChatStore, useChatChannel, type ChatKind } from '../../stores/chatStore'
import { useAuthStore } from '../../stores/authStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useProjectStore } from '../../stores/projectStore'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { getCoachIntro } from '../../lib/coachIntro'
import { useCueNotification } from '../../hooks/useCueNotification'
import type { WSClientMessage, WSSendChatMessage } from '../../types/ws'
import type { Seat, SeatRole, Message } from '../../types/models'

interface ChatPanelProps {
  projectId: string
  sendWS: (msg: WSClientMessage) => void
  disabled?: boolean
  onClose?: () => void

  // ── NEW (Phase 20)：個人聊天支援 ──
  /** chat_id：`${projectId}:group` | `${projectId}:personal:${userId}`；缺省則僅在送 WS 時不附 chat_id（後端 default group）。 */
  chatId?: string
  /** kind：default 'group'。決定要讀寫哪個 channel state。 */
  kind?: ChatKind
  /** Header 顯示文字；缺省依 kind 推斷。 */
  title?: string
  /** 自訂 header 左側內容（例如群組/個人切換 tab）；若提供會覆蓋 title。 */
  titleSlot?: ReactNode
  /** 輸入框 placeholder。 */
  inputPlaceholder?: string
}

function getSeatRole(seats: Seat[], senderId: string): SeatRole | undefined {
  return seats.find((s) => s.user_id === senderId || s.agent_id === senderId)?.seat_role
}

function defaultTitle(kind: ChatKind): string {
  return kind === 'group' ? '群組聊天室' : '個人助理'
}

export function ChatPanel({
  projectId,
  sendWS,
  disabled = false,
  onClose,
  chatId,
  kind = 'group',
  title,
  titleSlot,
  inputPlaceholder,
}: ChatPanelProps) {
  const { messages, typingUsers, typingAgents, hasMore, isLoading } = useChatChannel(kind)
  const loadHistory = useChatStore((s) => s.loadHistory)
  const loadMore = useChatStore((s) => s.loadMore)
  const { user } = useAuthStore()
  const { seats } = useSeatStore()
  const { currentStage } = useStageStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  // mount：載入歷史。
  // personal channel 需要 userId 才會發 request（store 內部已 guard）。
  useEffect(() => {
    loadHistory(projectId, kind, user?.id)
  }, [projectId, kind, user?.id, loadHistory])

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
      loadMore(projectId, kind, user?.id)
    }
  }

  const handleSend = useCallback(
    (content: string) => {
      // 樂觀顯示：立即把自己的訊息加進 channel，不等 WS echo。echo 走 Redis 來回、且可能被
      // 歷史 fetch 競態覆蓋（盲測 2026-06-09：人類打字看不到、以為壞了）。echo 回來時
      // addMessage 以 (sender_id, content) 對帳此 pending 並就地取代、清 pending。
      if (user) {
        useChatStore.getState().addMessage(kind, {
          id: `optimistic:${crypto.randomUUID()}`,
          project_id: projectId,
          sender_type: 'human',
          sender_id: user.id,
          sender_name: user.display_name,
          content,
          stage: currentStage,
          created_at: new Date().toISOString(),
          chat_id: chatId,
          pending: true,
        })
      }
      // chatId 缺省時，後端 default 視為 `${projectId}:group`（既有 caller 行為不變）
      const payload: WSSendChatMessage['payload'] = chatId
        ? { content, chat_id: chatId }
        : { content }
      sendWS({ type: 'chat_message', payload })
    },
    [sendWS, chatId, kind, projectId, user, currentStage],
  )

  // typing 指示器：個人聊天不送（純 1-on-1，沒人需要看）
  const handleTypingStart = useCallback(() => {
    if (kind === 'group') sendWS({ type: 'typing_start', payload: {} })
  }, [sendWS, kind])
  const handleTypingStop = useCallback(() => {
    if (kind === 'group') sendWS({ type: 'typing_stop', payload: {} })
  }, [sendWS, kind])

  // typing 列：人類 + AI（D2/WP9 #9）。AI typing 只在群組 channel（個人 channel 不發、
  // typingAgents 永遠空）；chat 與人類合併成「正在輸入…」、canvas 另成「正在白板上寫…」。
  const humanTypers = Object.values(typingUsers)
  const agentTypers = kind === 'group' ? Object.values(typingAgents) : []
  const chatTypers = Array.from(
    new Set([
      ...humanTypers,
      ...agentTypers.filter((a) => a.kind === 'chat').map((a) => a.displayName),
    ]),
  )
  const canvasTypers = Array.from(
    new Set(agentTypers.filter((a) => a.kind === 'canvas').map((a) => a.displayName)),
  )

  // UX intro（純前端，不寫 store/DB）——只在 personal channel 且 messages 為空且非載入中時呈現。
  // 一旦使用者真正送出第一句，messages 不再為空，intro 自然消失。
  const introMessage = useMemo<Message | null>(() => {
    if (kind !== 'personal') return null
    if (messages.length > 0) return null
    if (isLoading) return null
    return {
      id: '__coach_intro__',
      project_id: projectId,
      sender_type: 'ai',
      sender_id: 'dt-coach',
      sender_name: 'DT 教練',
      content: getCoachIntro(currentStage),
      stage: currentStage,
      created_at: new Date().toISOString(),
    }
  }, [kind, messages.length, isLoading, projectId, currentStage])

  const headerTitle = title ?? defaultTitle(kind)

  // Phase 28：當前 seat / turnState 用於 ChatInput 條件式按鈕
  const mySeat = useMemo(
    () => seats.find((s) => s.user_id === user?.id),
    [seats, user?.id],
  )
  const mySeatRole = mySeat?.seat_role
  const turnPolicy = useProjectStore((s) => s.currentProject?.turn_policy)
  const turnState = useProjectStore((s) => s.turnState)
  const isMyTurn = useMemo(() => {
    if (kind !== 'group') return true // personal chat 不受輪流規則限制
    if (!turnState) return true // 沒有 turnState 資訊時保守視為可講 (Cued/OpenFloor 預設行為)
    if (turnPolicy === 'open_floor') return true
    return turnState.next_speaker === mySeatRole
  }, [kind, turnState, turnPolicy, mySeatRole])

  // Phase 28：被 cue 時顯示 2 秒黃底 banner
  const [cueBanner, setCueBanner] = useState(false)
  useCueNotification(mySeatRole, () => {
    setCueBanner(true)
    window.setTimeout(() => setCueBanner(false), 2000)
  })

  const handlePass = useCallback(
    (seatRole: SeatRole) => {
      sendWS({ type: 'agent_action', payload: { action: 'pass', seat_role: seatRole } })
    },
    [sendWS],
  )
  const handleRaiseHand = useCallback(
    (seatRole: SeatRole) => {
      sendWS({
        type: 'agent_action',
        payload: { action: 'raise_hand', seat_role: seatRole },
      })
    },
    [sendWS],
  )

  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        {titleSlot ?? <h3 className="text-sm font-semibold text-text">{headerTitle}</h3>}
        {onClose && (
          <button
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 rounded-md text-text-muted hover:text-text hover:bg-surface-hover transition-colors cursor-pointer"
            aria-label={`關閉${headerTitle}`}
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
        {introMessage && (
          <ChatMessage
            key={introMessage.id}
            message={introMessage}
            isOwn={false}
            seatRole={undefined}
          />
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

      {/* Typing indicator（人類 + AI chat） */}
      {chatTypers.length > 0 && (
        <div className="px-4 py-1 text-xs text-text-muted italic">
          {chatTypers.join('、')} 正在輸入…
        </div>
      )}
      {/* AI 白板動作前置（D2/WP9 #9） */}
      {canvasTypers.length > 0 && (
        <div className="px-4 py-1 text-xs text-text-muted italic">
          {canvasTypers.join('、')} 正在白板上寫…
        </div>
      )}

      {/* Phase 28：被 cue 時的黃底通知 banner (2 秒自動消失) */}
      {cueBanner && (
        <div
          role="status"
          data-testid="cue-banner"
          className="flex items-center gap-2 border-t border-warning/30 bg-warning/15 px-4 py-2 text-sm text-warning"
        >
          <Bell size={14} className="shrink-0" />
          <span>輪到你了！</span>
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onTypingStart={handleTypingStart}
        onTypingStop={handleTypingStop}
        disabled={disabled}
        placeholder={inputPlaceholder}
        turnPolicy={kind === 'group' ? turnPolicy : undefined}
        isMyTurn={isMyTurn}
        allowedActions={kind === 'group' ? turnState?.allowed_actions : undefined}
        mySeatRole={kind === 'group' ? mySeatRole : undefined}
        onPass={kind === 'group' ? handlePass : undefined}
        onRaiseHand={kind === 'group' ? handleRaiseHand : undefined}
      />
    </div>
  )
}
