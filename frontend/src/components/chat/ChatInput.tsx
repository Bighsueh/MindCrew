import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Send, Hand, SkipForward } from 'lucide-react'
import { cn } from '../../lib/utils'
import { CUE_EVENT_NAME, type CueEventDetail } from '../../hooks/useCueNotification'
import type { SeatRole, TurnPolicy, TurnAllowedAction } from '../../types/models'

interface ChatInputProps {
  onSend: (content: string) => void
  onTypingStart?: () => void
  onTypingStop?: () => void
  disabled?: boolean
  placeholder?: string
  /** Phase 28：當前 turn-taking 規則；undefined 視為 cued (向下相容)。 */
  turnPolicy?: TurnPolicy
  /** Phase 28：當前是否輪到我；undefined 視為 true (向下相容)。 */
  isMyTurn?: boolean
  /** Phase 28：本回合允許的動作子集（speak/pass/raise_hand），未提供時依 isMyTurn 推。 */
  allowedActions?: TurnAllowedAction[]
  /** Phase 28：我的 seat_role；觸發 raise_hand / pass 時需要帶上。 */
  mySeatRole?: SeatRole
  /** Phase 28：按 Pass 按鈕時呼叫（送 WS agent_action）。 */
  onPass?: (seatRole: SeatRole) => void
  /** Phase 28：按「我要發言」按鈕時呼叫（送 WS agent_action）。 */
  onRaiseHand?: (seatRole: SeatRole) => void
}

export function ChatInput({
  onSend,
  onTypingStart,
  onTypingStop,
  disabled = false,
  placeholder = '輸入訊息…（Enter 送出，Shift+Enter 換行）',
  turnPolicy,
  isMyTurn,
  allowedActions,
  mySeatRole,
  onPass,
  onRaiseHand,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [cueFlash, setCueFlash] = useState(false)
  const typingRef = useRef(false)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Phase 28：被 cue 時邊框閃爍兩次 (200ms × 2)
  useEffect(() => {
    if (!mySeatRole) return
    const handler = (event: Event) => {
      const custom = event as CustomEvent<CueEventDetail>
      if (custom.detail?.target_seat_role !== mySeatRole) return
      setCueFlash(true)
      window.setTimeout(() => setCueFlash(false), 600)
    }
    window.addEventListener(CUE_EVENT_NAME, handler)
    return () => window.removeEventListener(CUE_EVENT_NAME, handler)
  }, [mySeatRole])

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
    // 注音/IME 選字按 Enter 不可誤觸送出 — 組字中直接 return
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled || !canSpeak) return

    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    if (typingRef.current) {
      typingRef.current = false
      onTypingStop?.()
    }

    onSend(trimmed)
    setValue('')
  }

  const handlePass = () => {
    if (mySeatRole && onPass) onPass(mySeatRole)
  }

  const handleRaiseHand = () => {
    if (mySeatRole && onRaiseHand) onRaiseHand(mySeatRole)
  }

  // ── 條件式按鈕渲染 () ──
  // 預設 (沒 controller 資訊) 視為可講，以便向下相容既有頁面。
  const myTurn = isMyTurn ?? true
  const allowed = allowedActions ?? (myTurn ? ['speak', 'pass'] : [])
  const canSpeak =
    !disabled && (turnPolicy === 'open_floor' || myTurn || allowed.includes('speak'))
  const showPass = myTurn && allowed.includes('pass') && !!onPass && !!mySeatRole
  const showRaiseHand =
    turnPolicy === 'open_floor' && !!onRaiseHand && !!mySeatRole

  const sendDisabled = disabled || !value.trim() || !canSpeak
  const sendTooltip = !canSpeak ? '現在不是你的回合' : undefined

  return (
    <div
      className={cn(
        'flex gap-2 border-t p-3 transition-colors',
        cueFlash
          ? 'border-warning ring-2 ring-warning/40'
          : 'border-border',
      )}
      data-testid="chat-input"
    >
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
      {showRaiseHand && (
        <button
          onClick={handleRaiseHand}
          disabled={disabled}
          title="我要發言"
          aria-label="我要發言"
          data-testid="raise-hand-btn"
          className={cn(
            'flex-shrink-0 flex items-center justify-center gap-1 rounded-lg px-3 py-2',
            'border border-warning/40 bg-warning/10 text-warning hover:bg-warning/20',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-colors cursor-pointer text-xs',
          )}
        >
          <Hand size={14} />
          <span className="hidden sm:inline">我要發言</span>
        </button>
      )}
      {showPass && (
        <button
          onClick={handlePass}
          disabled={disabled}
          title="Pass — 跳過此回合"
          aria-label="Pass"
          data-testid="pass-btn"
          className={cn(
            'flex-shrink-0 flex items-center justify-center gap-1 rounded-lg px-3 py-2',
            'border border-border bg-surface text-text-muted hover:bg-surface-hover',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-colors cursor-pointer text-xs',
          )}
        >
          <SkipForward size={14} />
          <span className="hidden sm:inline">Pass</span>
        </button>
      )}
      <button
        onClick={handleSend}
        disabled={sendDisabled}
        title={sendTooltip}
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
