import { create } from 'zustand'
import type { Message } from '../types/models'
import { getMessages } from '../services/projectService'

// ── Types ───────────────────────────────────────────────────────────────────

export type ChatKind = 'group' | 'personal'

/** D2/WP9 #9：AI 席位 typing 狀態（chat=正在輸入；canvas=正在白板上寫）。 */
export type AgentTypingKind = 'chat' | 'canvas'

export interface AgentTyping {
  displayName: string
  kind: AgentTypingKind
}

export interface ChannelState {
  messages: Message[]
  /** Map of identifier → display name of users currently typing. */
  typingUsers: Record<string, string>
  /** D2/WP9 #9：AI typing，key=seat_id（與人類 typingUsers 並存、共用 UI 列）。 */
  typingAgents: Record<string, AgentTyping>
  unreadCount: number
  isLoading: boolean
  hasMore: boolean
  oldestTimestamp: string | null
}

interface ChatStore {
  group: ChannelState
  personal: ChannelState

  // ── Generic actions（kind 顯式）──
  addMessage: (kind: ChatKind, message: Message) => void
  setMessages: (kind: ChatKind, messages: Message[], hasMore?: boolean) => void
  prependMessages: (kind: ChatKind, messages: Message[], hasMore: boolean) => void
  setLoading: (kind: ChatKind, isLoading: boolean) => void
  setTyping: (kind: ChatKind, userId: string, displayName: string, isTyping: boolean) => void
  setAgentTyping: (
    kind: ChatKind,
    seatId: string,
    displayName: string,
    agentKind: AgentTypingKind,
    isTyping: boolean,
  ) => void
  incrementUnread: (kind: ChatKind) => void
  resetUnread: (kind: ChatKind) => void
  resetChannel: (kind: ChatKind) => void
  reset: () => void

  // ── 歷史載入：依 kind 路由不同 chat_id ──
  /**
   * Load message history for the given kind.
   * - kind defaults to 'group' for legacy callers
   * - currentUserId is required when kind === 'personal'
   */
  loadHistory: (projectId: string, kind?: ChatKind, currentUserId?: string) => Promise<void>
  loadMore: (projectId: string, kind?: ChatKind, currentUserId?: string) => Promise<void>
}

// ── Constants ───────────────────────────────────────────────────────────────

const initialChannelState: ChannelState = {
  messages: [],
  typingUsers: {},
  typingAgents: {},
  unreadCount: 0,
  isLoading: false,
  hasMore: false,
  oldestTimestamp: null,
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 依 kind + currentUserId 組出 chat_id。
 * - group：傳 undefined（不附 chat_id，後端 default 視為 group），避免無端綁定 project 字串。
 * - personal：必須有 userId，否則回傳 undefined（caller 會跳過 fetch）。
 */
function buildChatId(
  projectId: string,
  kind: ChatKind,
  currentUserId?: string,
): string | undefined {
  if (kind === 'group') return `${projectId}:group`
  if (!currentUserId) return undefined
  return `${projectId}:personal:${currentUserId}`
}

/**
 * 移除 displayName 相符的 AI typing 條目（不可變）。AI 真正訊息落地時呼叫，
 * 作為後端 `agent_typing` stop 事件的雙保險（漏接 stop 也不會卡住 typing 列）。
 */
function dropAgentTypingByName(
  agents: Record<string, AgentTyping>,
  displayName: string,
): Record<string, AgentTyping> {
  const entries = Object.entries(agents).filter(([, a]) => a.displayName !== displayName)
  if (entries.length === Object.keys(agents).length) return agents
  return Object.fromEntries(entries)
}

// 同頻道歷史載入的併發合併：同一 (project,kind,chatId) 同時有三處 caller（Workspace index /
// ChatDock / ChatPanel mount）會各做一次「整段取代」而互相覆蓋掉剛送出/剛 echo 的訊息。
// 用 in-flight key 把併發載入合併成一次（盲測 2026-06-09 人類訊息消失主因之一）。
const _historyInFlight = new Set<string>()

// Phase 42 補正 R4（稽核 §4.3）：agent typing 前端 TTL 兜底——backend 硬死／WS 斷線
// 漏接 stop、重連不重置 typingAgents 時，條目 90s 自動過期，不永久卡「正在輸入…」。
// 後端 try/finally 是主保險，本 timer 只兜「stop 事件永遠不會來」的終局。
const TYPING_TTL_MS = 90_000
const _typingTtlTimers = new Map<string, ReturnType<typeof setTimeout>>()

// ── Store ───────────────────────────────────────────────────────────────────

export const useChatStore = create<ChatStore>((set, get) => ({
  group: { ...initialChannelState },
  personal: { ...initialChannelState },

  addMessage: (kind, message) => {
    set((state) => {
      const channel = state[kind]
      // De-duplicate by id
      if (channel.messages.some((m) => m.id === message.id)) return state
      // AI 訊息落地 → 清掉該席位的 typing 列（雙保險於 agent_typing stop 事件）。
      const typingAgents =
        message.sender_type === 'ai'
          ? dropAgentTypingByName(channel.typingAgents, message.sender_name)
          : channel.typingAgents
      // server echo（非 pending）對帳先前樂觀送出的 pending：同 sender + content → 就地取代、
      // 清 pending、採用 server id/時間，避免出現「自己的話重複兩則」或永遠 pending。
      if (!message.pending) {
        const idx = channel.messages.findIndex(
          (m) =>
            m.pending === true &&
            m.sender_id === message.sender_id &&
            m.content === message.content,
        )
        if (idx !== -1) {
          const next = [...channel.messages]
          next[idx] = { ...message, pending: false }
          return { [kind]: { ...channel, messages: next, typingAgents } } as Partial<ChatStore>
        }
      }
      return {
        [kind]: {
          ...channel,
          messages: [...channel.messages, message],
          typingAgents,
        },
      } as Partial<ChatStore>
    })
  },

  setMessages: (kind, messages, hasMore) => {
    set((state) => ({
      [kind]: {
        ...state[kind],
        messages,
        hasMore: hasMore ?? state[kind].hasMore,
        oldestTimestamp: messages.length > 0 ? messages[0].created_at : null,
      },
    } as Partial<ChatStore>))
  },

  prependMessages: (kind, messages, hasMore) => {
    set((state) => ({
      [kind]: {
        ...state[kind],
        messages: [...messages, ...state[kind].messages],
        hasMore,
        oldestTimestamp:
          messages.length > 0 ? messages[0].created_at : state[kind].oldestTimestamp,
      },
    } as Partial<ChatStore>))
  },

  setLoading: (kind, isLoading) => {
    set((state) => ({
      [kind]: { ...state[kind], isLoading },
    } as Partial<ChatStore>))
  },

  setTyping: (kind, userId, displayName, isTyping) => {
    set((state) => {
      const channel = state[kind]
      const next: Record<string, string> = { ...channel.typingUsers }
      if (isTyping) {
        next[userId] = displayName
      } else {
        delete next[userId]
      }
      return {
        [kind]: { ...channel, typingUsers: next },
      } as Partial<ChatStore>
    })
  },

  setAgentTyping: (kind, seatId, displayName, agentKind, isTyping) => {
    // TTL 兜底：start 排一支過期 timer；stop／過期／重複 start 都先清舊 timer。
    const ttlKey = `${kind}:${seatId}`
    const prevTimer = _typingTtlTimers.get(ttlKey)
    if (prevTimer) clearTimeout(prevTimer)
    if (isTyping) {
      _typingTtlTimers.set(
        ttlKey,
        setTimeout(() => {
          _typingTtlTimers.delete(ttlKey)
          get().setAgentTyping(kind, seatId, displayName, agentKind, false)
        }, TYPING_TTL_MS),
      )
    } else {
      _typingTtlTimers.delete(ttlKey)
    }
    set((state) => {
      const channel = state[kind]
      const next: Record<string, AgentTyping> = { ...channel.typingAgents }
      if (isTyping) {
        next[seatId] = { displayName, kind: agentKind }
      } else {
        delete next[seatId]
      }
      return {
        [kind]: { ...channel, typingAgents: next },
      } as Partial<ChatStore>
    })
  },

  incrementUnread: (kind) => {
    set((state) => ({
      [kind]: { ...state[kind], unreadCount: state[kind].unreadCount + 1 },
    } as Partial<ChatStore>))
  },

  resetUnread: (kind) => {
    set((state) => ({
      [kind]: { ...state[kind], unreadCount: 0 },
    } as Partial<ChatStore>))
  },

  resetChannel: (kind) => {
    set(() => ({
      [kind]: { ...initialChannelState },
    } as Partial<ChatStore>))
  },

  reset: () => {
    set({
      group: { ...initialChannelState },
      personal: { ...initialChannelState },
    })
  },

  // ── 歷史載入 ──

  loadHistory: async (projectId, kind = 'group', currentUserId) => {
    const chatId = buildChatId(projectId, kind, currentUserId)
    // personal 但沒有 userId → 不發 request，靜默 noop（避免拿到別人的訊息）
    if (kind === 'personal' && !chatId) return

    const flightKey = `${projectId}:${kind}:${chatId ?? 'group'}`
    if (_historyInFlight.has(flightKey)) return // 合併併發載入，避免互相覆蓋
    _historyInFlight.add(flightKey)

    set((state) => ({
      [kind]: { ...state[kind], isLoading: true },
    } as Partial<ChatStore>))

    try {
      const result = await getMessages(projectId, { limit: 50, chatId })
      const sorted = [...result.messages].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      set((state) => {
        // merge-preserve：保住本地較新 / 仍 pending 的訊息，避免整段取代把剛送出的
        // optimistic、或剛 echo 回來（晚於此快照）的訊息洗掉。
        const sortedIds = new Set(sorted.map((m) => m.id))
        const newest = sorted.length
          ? new Date(sorted[sorted.length - 1].created_at).getTime()
          : 0
        const keep = state[kind].messages.filter(
          (m) =>
            !sortedIds.has(m.id) &&
            (m.pending === true || new Date(m.created_at).getTime() >= newest),
        )
        return {
          [kind]: {
            ...state[kind],
            messages: [...sorted, ...keep],
            hasMore: result.has_more,
            isLoading: false,
            oldestTimestamp: sorted.length > 0 ? sorted[0].created_at : null,
          },
        } as Partial<ChatStore>
      })
    } catch {
      set((state) => ({
        [kind]: { ...state[kind], isLoading: false },
      } as Partial<ChatStore>))
    } finally {
      _historyInFlight.delete(flightKey)
    }
  },

  loadMore: async (projectId, kind = 'group', currentUserId) => {
    const channel = get()[kind]
    if (channel.isLoading || !channel.oldestTimestamp) return

    const chatId = buildChatId(projectId, kind, currentUserId)
    if (kind === 'personal' && !chatId) return

    set((state) => ({
      [kind]: { ...state[kind], isLoading: true },
    } as Partial<ChatStore>))

    try {
      const result = await getMessages(projectId, {
        limit: 50,
        before: channel.oldestTimestamp,
        chatId,
      })
      const sorted = [...result.messages].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      set((state) => ({
        [kind]: {
          ...state[kind],
          messages: [...sorted, ...state[kind].messages],
          hasMore: result.has_more,
          isLoading: false,
          oldestTimestamp:
            sorted.length > 0 ? sorted[0].created_at : state[kind].oldestTimestamp,
        },
      } as Partial<ChatStore>))
    } catch {
      set((state) => ({
        [kind]: { ...state[kind], isLoading: false },
      } as Partial<ChatStore>))
    }
  },
}))

// ── Selectors ───────────────────────────────────────────────────────────────

/**
 * Select an individual chat channel's state. Use this in components that only
 * need to read messages/typingUsers/unread for one channel.
 */
export const useChatChannel = (kind: ChatKind): ChannelState =>
  useChatStore((s) => s[kind])
