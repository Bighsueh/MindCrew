import { useCallback, useEffect, useRef, useState } from 'react'
import { Bot, MessageCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import { ChatPanel } from './ChatPanel'
import { useDrawerLayout } from '../../hooks/useDrawerLayout'
import { staggerStyle } from '../../lib/motion'
import {
  buildGroupChatId,
  buildPersonalChatId,
} from '../../lib/chatId'
import {
  useChatChannel,
  useChatStore,
  type ChatKind,
} from '../../stores/chatStore'
import type { WSClientMessage } from '../../types/ws'

// ── 顯示文案常數（主專案沒有 mocks/coach；ChatDock 直接 hardcode 即可） ──
const GROUP_TITLE = '群組聊天室'
const PERSONAL_TITLE = '個人助理'
const GROUP_PLACEHOLDER = '輸入訊息，按 Enter 送出…'
const PERSONAL_PLACEHOLDER = '與個人助理對話…'

// ── Panel 尺寸 ────────────────────────────────────────────────────────────
const DEFAULT_WIDTH = 380
const MIN_WIDTH = 280
const PANEL_GAP_PX = 12

function clampWidth(w: number): number {
  return Math.min(Math.max(w, MIN_WIDTH), window.innerWidth * 0.45)
}

// ── ChatDock Props ────────────────────────────────────────────────────────
//
// 由 Workspace 提供 projectId / currentUserId / sendWS，
// ChatDock 內部自管 activeKind / popoverOpen / width 等 UI state。
//
// 不接收 group/personal 的 meta：直接從 chatStore 讀 unread；
// chat_id 由 lib/chatId.ts 工具函式組裝。
export interface ChatDockProps {
  projectId: string
  /** 用來組 personal chat_id；缺省時不顯示個人助理（或 disabled）。 */
  currentUserId: string
  /** WS 送出 callback；ChatPanel 內會送 chat_message / typing_start / typing_stop。 */
  sendWS: (msg: WSClientMessage) => void
  /** 哪個 channel 預設打開？undefined / null = 都關（顯示 FAB）。 */
  initialOpen?: ChatKind | null
  /** 白板進入繪圖模式時，FAB 半透明化以避免遮擋筆觸。 */
  dim?: boolean
  /** 主動 channel 變化時通知 Workspace（讓 onboarding tour anchor 同步）。 */
  onActiveChange?: (kind: ChatKind | null) => void
  /** group channel 是否 disabled（例如 observer 模式）。 */
  groupDisabled?: boolean
}

export function ChatDock({
  projectId,
  currentUserId,
  sendWS,
  initialOpen = null,
  dim = false,
  onActiveChange,
  groupDisabled = false,
}: ChatDockProps) {
  const [activeKind, setActiveKind] = useState<ChatKind | null>(initialOpen ?? null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const [popoverOpen, setPopoverOpen] = useState(false)
  const isResizing = useRef(false)
  const isDrawer = useDrawerLayout()

  // 直接訂閱兩 channel 的 unread；零 prop drilling。
  const groupUnread = useChatChannel('group').unreadCount
  const personalUnread = useChatChannel('personal').unreadCount

  const resetUnread = useChatStore((s) => s.resetUnread)
  const loadHistory = useChatStore((s) => s.loadHistory)

  // ── 對外通知：activeKind 變化 ──
  useEffect(() => {
    onActiveChange?.(activeKind)
  }, [activeKind, onActiveChange])

  // ── 切換 channel 時：載入歷史 + reset unread ──
  useEffect(() => {
    if (activeKind === null) return
    if (activeKind === 'personal' && !currentUserId) return
    loadHistory(projectId, activeKind, currentUserId)
    resetUnread(activeKind)
  }, [activeKind, projectId, currentUserId, loadHistory, resetUnread])

  // ── Esc 關閉 panel ──
  useEffect(() => {
    if (activeKind === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActiveKind(null)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [activeKind])

  // ── Panel 寬度拖曳（僅 desktop） ──
  const beginResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      isResizing.current = true
      const startX = e.clientX
      const startWidth = width

      const onMove = (ev: MouseEvent) => {
        if (!isResizing.current) return
        const delta = startX - ev.clientX
        setWidth(clampWidth(startWidth + delta))
      }
      const onUp = () => {
        isResizing.current = false
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [width],
  )

  const isOpen = activeKind !== null
  const handleClose = () => setActiveKind(null)
  const totalUnread = groupUnread + personalUnread

  // FAB 容器須在面板左側讓位；drawer 模式時 FAB 永遠固定在右下角。
  const openPanelsWidth = isOpen && !isDrawer ? width + PANEL_GAP_PX : 0

  const handleSelect = (kind: ChatKind) => {
    setPopoverOpen(false)
    setActiveKind(kind)
  }

  // 計算當前 panel 的 chatId / title / placeholder。
  // 注意：personal 缺 userId 時 fallback 為 group，避免錯誤組 chat_id。
  const effectiveKind: ChatKind =
    activeKind === 'personal' && !currentUserId ? 'group' : (activeKind ?? 'group')

  const activeChatId =
    effectiveKind === 'personal'
      ? buildPersonalChatId(projectId, currentUserId)
      : buildGroupChatId(projectId)

  const activeTitle = effectiveKind === 'personal' ? PERSONAL_TITLE : GROUP_TITLE
  const activePlaceholder =
    effectiveKind === 'personal' ? PERSONAL_PLACEHOLDER : GROUP_PLACEHOLDER
  const activeDisabled = effectiveKind === 'group' ? groupDisabled : false

  const titleSlot = (
    <ChannelTabs
      activeKind={effectiveKind}
      groupUnread={groupUnread}
      personalUnread={personalUnread}
      onChange={setActiveKind}
    />
  )

  return (
    <>
      <FloatingPanel open={isOpen} width={width} drawer={isDrawer}>
        {!isDrawer && <ResizeHandle onMouseDown={beginResize} />}
        {isDrawer && <DrawerHandle />}
        <ChatPanel
          key={activeChatId}
          projectId={projectId}
          chatId={activeChatId}
          kind={effectiveKind}
          title={activeTitle}
          titleSlot={titleSlot}
          sendWS={sendWS}
          disabled={activeDisabled}
          onClose={handleClose}
          inputPlaceholder={activePlaceholder}
        />
      </FloatingPanel>

      <div
        className="pointer-events-none absolute bottom-6 z-40 flex flex-col items-end gap-2 transition-[right] duration-300 ease-out motion-reduce:transition-none"
        style={{ right: `calc(1rem + ${openPanelsWidth}px)` }}
      >
        {popoverOpen && !isOpen && (
          <ChannelPopover
            groupUnread={groupUnread}
            personalUnread={personalUnread}
            onSelect={handleSelect}
            onClose={() => setPopoverOpen(false)}
          />
        )}
        <PrimaryFab
          visible={!isOpen}
          dim={dim}
          totalUnread={totalUnread}
          expanded={popoverOpen}
          onClick={() => setPopoverOpen((v) => !v)}
        />
      </div>
    </>
  )
}

// ── 內部小元件 ───────────────────────────────────────────────────────────

interface ChannelTabsProps {
  activeKind: ChatKind
  groupUnread: number
  personalUnread: number
  onChange: (kind: ChatKind) => void
}

function ChannelTabs({ activeKind, groupUnread, personalUnread, onChange }: ChannelTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="聊天頻道切換"
      className="flex items-center gap-1 rounded-full bg-surface-hover p-0.5"
    >
      <ChannelTab
        active={activeKind === 'group'}
        onClick={() => onChange('group')}
        icon={<MessageCircle size={14} />}
        label={GROUP_TITLE}
        unread={activeKind === 'group' ? 0 : groupUnread}
      />
      <ChannelTab
        active={activeKind === 'personal'}
        onClick={() => onChange('personal')}
        icon={<Bot size={14} />}
        label={PERSONAL_TITLE}
        unread={activeKind === 'personal' ? 0 : personalUnread}
      />
    </div>
  )
}

interface ChannelTabProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
  unread: number
}

function ChannelTab({ active, onClick, icon, label, unread }: ChannelTabProps) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer',
        active ? 'bg-surface text-text shadow-sm' : 'text-text-muted hover:text-text',
      )}
    >
      {icon}
      <span>{label}</span>
      {unread > 0 && (
        <span className="flex items-center justify-center min-w-[1.125rem] h-4 rounded-full bg-error px-1 text-[10px] font-bold text-white">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </button>
  )
}

interface FloatingPanelProps {
  open: boolean
  width: number
  drawer: boolean
  children: React.ReactNode
}

function FloatingPanel({ open, width, drawer, children }: FloatingPanelProps) {
  // tablet portrait：底部 drawer（70vh）
  if (drawer) {
    return (
      <div
        className={cn(
          'absolute inset-x-0 bottom-0 z-30',
          'overflow-hidden rounded-t-2xl shadow-xl border-t border-x border-border bg-surface',
          'transition-transform duration-300 ease-out motion-reduce:transition-none',
          open ? 'translate-y-0' : 'translate-y-[calc(100%+16px)] pointer-events-none',
        )}
        style={{ height: '70vh' }}
      >
        {children}
      </div>
    )
  }

  // desktop：右側浮動視窗
  return (
    <div
      className={cn(
        'absolute top-3 bottom-3 right-3 z-30',
        'overflow-hidden rounded-xl shadow-xl border border-border bg-surface',
        'transition-transform duration-300 ease-out motion-reduce:transition-none',
        open ? 'translate-x-0' : 'translate-x-[calc(100%+24px)] pointer-events-none',
      )}
      style={{ width }}
    >
      {children}
    </div>
  )
}

function ResizeHandle({ onMouseDown }: { onMouseDown: (e: React.MouseEvent) => void }) {
  return (
    <div
      className="absolute left-0 top-12 bottom-3 z-10 w-1.5 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors"
      onMouseDown={onMouseDown}
    />
  )
}

function DrawerHandle() {
  return (
    <div className="flex justify-center pt-2 pb-1">
      <div className="w-10 h-1 rounded-full bg-border" aria-hidden />
    </div>
  )
}

interface PrimaryFabProps {
  visible: boolean
  dim: boolean
  totalUnread: number
  expanded: boolean
  onClick: () => void
}

function PrimaryFab({ visible, dim, totalUnread, expanded, onClick }: PrimaryFabProps) {
  return (
    <button
      onClick={onClick}
      data-tour="chat-fab"
      aria-label="開啟聊天"
      aria-expanded={expanded}
      aria-haspopup="menu"
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
      className={cn(
        'pointer-events-auto relative flex items-center justify-center w-14 h-14 rounded-full',
        'bg-accent text-white shadow-lg hover:bg-accent/90 cursor-pointer',
        'transition-all duration-300 ease-out motion-reduce:transition-none',
        visible ? 'scale-100' : 'opacity-0 pointer-events-none scale-90',
        visible && dim && !expanded
          ? 'opacity-30 hover:opacity-100 focus-visible:opacity-100'
          : visible
            ? 'opacity-100'
            : '',
      )}
      style={{ transitionDuration: dim ? '200ms' : undefined }}
    >
      <MessageCircle size={22} />
      {totalUnread > 0 && (
        <span
          className={cn(
            'absolute -top-1 -right-1 flex items-center justify-center min-w-[1.25rem] h-5 rounded-full',
            'bg-error px-1.5 text-[10px] font-bold text-white ring-2 ring-surface',
            'animate-notif-ring',
          )}
        >
          {totalUnread > 99 ? '99+' : totalUnread}
        </span>
      )}
    </button>
  )
}

interface ChannelPopoverProps {
  groupUnread: number
  personalUnread: number
  onSelect: (kind: ChatKind) => void
  onClose: () => void
}

function ChannelPopover({ groupUnread, personalUnread, onSelect, onClose }: ChannelPopoverProps) {
  const ref = useRef<HTMLDivElement>(null)

  // 外部點擊 / Esc 關閉
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onPointer = (e: PointerEvent) => {
      if (!ref.current) return
      if (e.target instanceof Node && !ref.current.contains(e.target)) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      role="menu"
      className="pointer-events-auto mb-2 w-56 rounded-xl border border-border bg-surface shadow-xl p-1.5 animate-popover-enter"
    >
      <PopoverRow
        index={0}
        icon={<MessageCircle size={16} />}
        label={GROUP_TITLE}
        unread={groupUnread}
        onClick={() => onSelect('group')}
      />
      <PopoverRow
        index={1}
        icon={<Bot size={16} />}
        label={PERSONAL_TITLE}
        unread={personalUnread}
        onClick={() => onSelect('personal')}
      />
    </div>
  )
}

interface PopoverRowProps {
  index: number
  icon: React.ReactNode
  label: string
  unread: number
  onClick: () => void
}

function PopoverRow({ index, icon, label, unread, onClick }: PopoverRowProps) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      style={staggerStyle(index, 30)}
      className={cn(
        'stagger-children-item flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5',
        'text-sm font-medium text-text hover:bg-surface-hover transition-colors cursor-pointer',
      )}
    >
      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-surface-hover text-text-muted">
        {icon}
      </span>
      <span className="flex-1 text-left">{label}</span>
      {unread > 0 && (
        <span className="flex items-center justify-center min-w-[1.125rem] h-4 rounded-full bg-error px-1 text-[10px] font-bold text-white">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </button>
  )
}
