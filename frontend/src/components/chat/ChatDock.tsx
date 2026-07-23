import { useCallback, useEffect, useRef, useState } from 'react'
import { Bot, MessageCircle, Users } from 'lucide-react'
import { cn } from '../../lib/utils'
import { ChatPanel } from './ChatPanel'
import { ChatRosterCard } from './ChatRosterCard'
import { useDrawerLayout } from '../../hooks/useDrawerLayout'
import type { Seat } from '../../types/models'
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
// 群組頻道多了右側「隊友」列，預設寬度加大讓訊息區與清單都有餘裕。
const DEFAULT_WIDTH = 480
const MIN_WIDTH = 280
// 群組頻道時，頂部讓出獨立「隊友」臉堆 pill 的高度（pill + 間距），聊天視窗往下讓位。
const ROSTER_RESERVED_PX = 60
// 右緣常駐「聊天大頭」泡泡佔的寬度（泡泡 48 + 左右間距），面板與隊友卡都靠左讓位。
const BUBBLE_LANE_PX = 76

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
  /** 目前使用者是否為建立者 → 群組頻道隊友列可就地編輯 AI 人設。 */
  isCreator?: boolean
  /** 人設儲存成功 → 回傳更新後 Seat，父層更新座位 store。 */
  onPersonaSaved?: (seat: Seat) => void
}

export function ChatDock({
  projectId,
  currentUserId,
  sendWS,
  initialOpen = null,
  dim = false,
  onActiveChange,
  groupDisabled = false,
  isCreator = false,
  onPersonaSaved,
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

  // ── Esc 關閉 panel（忽略來自 tldraw 畫布的 Esc：貼便條/退出文字編輯會發 Esc，不應收合聊天） ──
  useEffect(() => {
    if (activeKind === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (isCanvasEventTarget(e.target)) return
      setActiveKind(null)
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

  // 點頻道泡泡：同一顆 → 收合（縮回泡泡）；不同顆 → 直接切換、不必先關。
  const toggleChannel = (kind: ChatKind) => {
    setActiveKind((cur) => (cur === kind ? null : kind))
  }

  const chatPanel = (
    <ChatPanel
      key={activeChatId}
      projectId={projectId}
      chatId={activeChatId}
      kind={effectiveKind}
      title={activeTitle}
      sendWS={sendWS}
      disabled={activeDisabled}
      onClose={handleClose}
      inputPlaceholder={activePlaceholder}
    />
  )

  // 群組頻道（desktop）旁掛常駐「隊友」列：AI 隊友資訊/編輯都收斂在聊天室元件內。
  const showRoster = effectiveKind === 'group' && !isDrawer

  return (
    <>
      <FloatingPanel
        open={isOpen}
        width={width}
        drawer={isDrawer}
        topOffsetPx={showRoster ? ROSTER_RESERVED_PX : undefined}
        rightPx={isDrawer ? undefined : BUBBLE_LANE_PX}
      >
        {!isDrawer && <ResizeHandle onMouseDown={beginResize} />}
        {isDrawer && <DrawerHandle />}
        {chatPanel}
      </FloatingPanel>

      {/* option C：與聊天分離的獨立「隊友」浮卡，疊在聊天視窗上方。 */}
      {showRoster && isOpen && (
        <ChatRosterCard
          projectId={projectId}
          currentUserId={currentUserId}
          isCreator={isCreator}
          onPersonaSaved={onPersonaSaved ?? (() => {})}
          width={width}
          rightPx={BUBBLE_LANE_PX}
        />
      )}

      {/* 聊天大頭（desktop）：右緣常駐兩顆頻道泡泡，本身就是入口。 */}
      {!isDrawer && (
        <div className="absolute right-3 top-1/2 z-40 flex -translate-y-1/2 flex-col gap-3">
          <ChannelBubble
            icon={<Users size={20} />}
            label={GROUP_TITLE}
            active={activeKind === 'group'}
            unread={groupUnread}
            dim={dim}
            onClick={() => toggleChannel('group')}
          />
          <ChannelBubble
            icon={<Bot size={20} />}
            label={PERSONAL_TITLE}
            active={activeKind === 'personal'}
            unread={personalUnread}
            dim={dim}
            disabled={!currentUserId}
            onClick={() => toggleChannel('personal')}
          />
        </div>
      )}

      {/* tablet drawer：維持原本 FAB + 頻道選單。 */}
      {isDrawer && !isOpen && (
        <div className="pointer-events-none absolute bottom-6 right-4 z-40 flex flex-col items-end gap-2">
          {popoverOpen && (
            <ChannelPopover
              groupUnread={groupUnread}
              personalUnread={personalUnread}
              onSelect={handleSelect}
              onClose={() => setPopoverOpen(false)}
            />
          )}
          <PrimaryFab
            visible
            dim={dim}
            totalUnread={totalUnread}
            expanded={popoverOpen}
            onClick={() => setPopoverOpen((v) => !v)}
          />
        </div>
      )}
    </>
  )
}

interface ChannelBubbleProps {
  icon: React.ReactNode
  label: string
  active: boolean
  unread: number
  dim: boolean
  disabled?: boolean
  onClick: () => void
}

/**
 * ChannelBubble — Messenger 風「聊天大頭」：右緣常駐圓形泡泡＝頻道入口。
 * active：套赤陶色外環 + 左側指示條；未讀：紅色數字 + 外圈輕呼吸；hover：左側浮出頻道名。
 */
function ChannelBubble({ icon, label, active, unread, dim, disabled, onClick }: ChannelBubbleProps) {
  return (
    <div className="group pointer-events-auto relative">
      {/* hover：左側頻道名標籤 */}
      <span className="pointer-events-none absolute right-full top-1/2 mr-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-text px-2 py-1 text-[11px] font-medium text-bg opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100">
        {label}
      </span>

      {/* active：左側赤陶色指示條 */}
      {active && (
        <span className="absolute -left-2 top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-supervisor" aria-hidden="true" />
      )}

      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        aria-pressed={active}
        className={cn(
          'relative flex h-12 w-12 items-center justify-center rounded-full bg-surface shadow-lg transition-all duration-200',
          active
            ? 'text-supervisor ring-2 ring-supervisor'
            : 'text-text-muted ring-1 ring-border hover:text-text hover:-translate-x-0.5',
          disabled && 'cursor-not-allowed opacity-40 hover:translate-x-0',
          dim && !active && 'opacity-40 hover:opacity-100',
        )}
      >
        {icon}

        {/* 未讀：外圈輕呼吸 */}
        {unread > 0 && (
          <span className="absolute inset-0 rounded-full ring-2 ring-error/40 animate-pulse" aria-hidden="true" />
        )}
        {/* 未讀：紅色數字 */}
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-error px-1 text-[10px] font-bold text-white ring-2 ring-bg">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
    </div>
  )
}

// ── 內部小元件 ───────────────────────────────────────────────────────────

interface FloatingPanelProps {
  open: boolean
  width: number
  drawer: boolean
  children: React.ReactNode
  /** desktop：聊天視窗頂端往下讓位（給上方的獨立隊友浮卡），預設 12px。 */
  topOffsetPx?: number
  /** desktop：右側讓位給常駐頻道泡泡，預設 12px。 */
  rightPx?: number
}

function FloatingPanel({ open, width, drawer, children, topOffsetPx, rightPx }: FloatingPanelProps) {
  // tablet portrait：底部 drawer（70vh）
  if (drawer) {
    return (
      <div
        aria-hidden={!open}
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
      aria-hidden={!open}
      onPointerDownCapture={commitCanvasTextEditing}
      className={cn(
        // origin-right：開合用「淡入＋從右緣縮放」取代水平滑入滑出，
        // 面板不再橫掃過白板（消除「白板左右位移」的錯覺），且像縮回右側泡泡。
        'absolute bottom-3 z-30 origin-right',
        'overflow-hidden rounded-xl shadow-xl border border-border bg-surface',
        'transition-[opacity,transform,top] duration-200 ease-out motion-reduce:transition-none',
        open ? 'scale-100 opacity-100' : 'pointer-events-none scale-95 opacity-0',
      )}
      style={{ width, top: topOffsetPx ?? 12, right: rightPx ?? 12 }}
    >
      {children}
    </div>
  )
}

/**
 * tldraw 便利貼一貼好會自動進入文字編輯；此時第一次點聊天輸入框會被 tldraw「退出編輯」
 * 吃掉，要再點一次才打得到字（盲測 2026-06-08：「要先點白板空白處取消選取才能打字」）。
 * 在聊天面板 pointerdown 的 capture 階段，先把 tldraw 內仍 focus 的編輯元素 blur（＝提交編輯），
 * 讓同一下點擊能直接落到聊天輸入框。只在 active 元素確實位於 `.tl-container` 內時動作，正常聊天
 * 時為 no-op，零副作用。
 */
function commitCanvasTextEditing(): void {
  const active = document.activeElement as HTMLElement | null
  if (active && active.closest('.tl-container')) {
    active.blur()
  }
}

/**
 * 事件是否來自 tldraw 畫布內（便利貼 `.tl-shape` 或容器 `.tl-container`）。tldraw 以原生 Esc
 * 退出文字編輯 / 取消選取，該 Esc 會冒泡到 document；聊天的全域 Esc-關閉監聽若不過濾來源，
 * 貼完便條就會誤把聊天面板收合成泡泡（盲測 2026-06-09）。selector 與
 * `useActivityHighlightGlobal.ts` 一致。
 */
function isCanvasEventTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    target.closest('.tl-shape, .tl-container') !== null
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
