import { create } from 'zustand'
import type { Message } from '../types/models'
import { getMessages } from '../services/projectService'

// ── Types ───────────────────────────────────────────────────────────────────

export type ChatKind = 'group' | 'personal'

export interface ChannelState {
  messages: Message[]
  /** Map of identifier → display name of users currently typing. */
  typingUsers: Record<string, string>
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

// ── Store ───────────────────────────────────────────────────────────────────

export const useChatStore = create<ChatStore>((set, get) => ({
  group: { ...initialChannelState },
  personal: { ...initialChannelState },

  addMessage: (kind, message) => {
    set((state) => {
      const channel = state[kind]
      // De-duplicate by id
      if (channel.messages.some((m) => m.id === message.id)) return state
      return {
        [kind]: {
          ...channel,
          messages: [...channel.messages, message],
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

    set((state) => ({
      [kind]: { ...state[kind], isLoading: true },
    } as Partial<ChatStore>))

    try {
      const result = await getMessages(projectId, { limit: 50, chatId })
      const sorted = [...result.messages].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      set((state) => ({
        [kind]: {
          ...state[kind],
          messages: sorted,
          hasMore: result.has_more,
          isLoading: false,
          oldestTimestamp: sorted.length > 0 ? sorted[0].created_at : null,
        },
      } as Partial<ChatStore>))
    } catch {
      set((state) => ({
        [kind]: { ...state[kind], isLoading: false },
      } as Partial<ChatStore>))
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
