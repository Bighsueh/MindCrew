import { useMemo } from 'react'
import { Bot } from 'lucide-react'
import { cn } from '../../lib/utils'
import { renderEmphasis } from '../../lib/emphasis'
import { useAuthorColor } from '../../hooks/useAuthorColor'
import { SeatIcon } from '../../lib/seatIcons'
import type { Message, SeatRole } from '../../types/models'
import {
  chatActivityKey,
  computeChatHighlightStyle,
  parseCreatedAt,
} from '../canvas/activityHighlight'
import {
  selectActiveAnchor,
  useActivityHighlightStore,
} from '../../stores/activityHighlightStore'

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
  // Phase 22：拿席位識別色（兼用於 avatar、bubble、dot）
  const { token: authorColorToken, scheme } = useAuthorColor(
    message.sender_id,
    message.sender_type,
  )
  // Phase 22+：每個角色一個專屬色（含 supervisor）。氣泡色 = 該席位便條色。
  // supervisor 不再寫死陶土；改用其席位色（red＝陶土），身分改靠「組長」badge 標示。
  const hasAuthorColor = authorColorToken !== null && !isSystem

  // Phase 24：activity highlight
  const myKey = useMemo(
    () => chatActivityKey(message.sender_type, message.sender_name),
    [message.sender_type, message.sender_name],
  )
  const myAnchorMs = useMemo(
    () => parseCreatedAt(parseUTCDate(message.created_at).toISOString()),
    [message.created_at],
  )
  const active = useActivityHighlightStore(selectActiveAnchor)
  const setHover = useActivityHighlightStore((s) => s.setHover)
  const clearHover = useActivityHighlightStore((s) => s.clearHover)
  const togglePinned = useActivityHighlightStore((s) => s.togglePinned)

  const highlightStyle = !isSystem
    ? computeChatHighlightStyle({
        key: myKey,
        anchorMs: myAnchorMs,
        active,
        accentColor: scheme.accent,
      })
    : undefined

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <div className="rounded-full bg-secondary/30 px-4 py-1.5 text-xs text-text-muted">
          {message.content}
        </div>
      </div>
    )
  }

  const handleEnter = (): void => {
    setHover({ key: myKey, anchorMs: myAnchorMs, source: 'chat' })
  }
  const handleLeave = (): void => {
    clearHover()
  }
  const handleClick = (): void => {
    togglePinned({ key: myKey, anchorMs: myAnchorMs, source: 'chat' })
  }

  return (
    <div
      data-activity-highlight="chat"
      data-activity-key={myKey}
      tabIndex={0}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleEnter}
      onBlur={handleLeave}
      onClick={handleClick}
      className={cn(
        'flex gap-2 mb-3 cursor-pointer rounded-lg p-1 transition-shadow outline-none',
        isOwn ? 'flex-row-reverse' : 'flex-row',
        message.pending && 'opacity-60',
      )}
      style={highlightStyle}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm',
          isSupervisor && hasAuthorColor && 'ring-2 ring-supervisor/30',
          !hasAuthorColor && 'bg-accent/15 text-accent',
        )}
        style={
          hasAuthorColor
            ? { backgroundColor: scheme.bubbleBg, color: scheme.accent }
            : undefined
        }
        title={authorColorToken ?? undefined}
      >
        {isAI ? (
          <SeatIcon
            seatRole={seatRole ?? 'crew_1'}
            isAI
            isSupervisor={isSupervisor}
            size={16}
          />
        ) : (
          message.sender_name[0]?.toUpperCase() ?? '?'
        )}
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
            isOwn ? 'rounded-tr-sm' : 'rounded-tl-sm',
            !hasAuthorColor && (isOwn
              ? 'bg-accent/10 text-text'
              : isAI
                ? 'border-l-2 border-accent/30 bg-secondary/20 text-text'
                : 'bg-bg-warm text-text'),
          )}
          style={
            hasAuthorColor
              ? {
                  backgroundColor: scheme.bubbleBg,
                  color: scheme.text,
                  borderLeft: isOwn ? undefined : `3px solid ${scheme.accent}`,
                }
              : undefined
          }
        >
          {/* D2/WP9 #12：強調格式僅 supervisor 渲染，crew／人類去標記純文字。 */}
          {renderEmphasis(message.content, isSupervisor)}
        </div>
      </div>
    </div>
  )
}
