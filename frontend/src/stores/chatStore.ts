import { create } from 'zustand'
import type { Message } from '../types/models'
import { getMessages } from '../services/projectService'

interface TypingUser {
  name: string
  timestamp: number
}

interface ChatState {
  messages: Message[]
  typingUsers: Map<string, TypingUser>
  hasMore: boolean
  isLoading: boolean
  oldestTimestamp: string | null
  unreadCount: number

  addMessage: (message: Message) => void
  loadHistory: (projectId: string) => Promise<void>
  loadMore: (projectId: string) => Promise<void>
  setTyping: (userName: string, isTyping: boolean) => void
  clearMessages: () => void
  incrementUnread: () => void
  resetUnread: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  typingUsers: new Map(),
  hasMore: false,
  isLoading: false,
  oldestTimestamp: null,
  unreadCount: 0,

  addMessage: (message: Message) => {
    set((state) => {
      // Avoid duplicate messages
      const exists = state.messages.some((m) => m.id === message.id)
      if (exists) return state
      return { messages: [...state.messages, message] }
    })
  },

  loadHistory: async (projectId: string) => {
    set({ isLoading: true })
    try {
      const result = await getMessages(projectId, 50)
      const sorted = [...result.messages].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      set({
        messages: sorted,
        hasMore: result.has_more,
        isLoading: false,
        oldestTimestamp: sorted.length > 0 ? sorted[0].created_at : null,
      })
    } catch {
      set({ isLoading: false })
    }
  },

  loadMore: async (projectId: string) => {
    const { oldestTimestamp, isLoading } = get()
    if (isLoading || !oldestTimestamp) return

    set({ isLoading: true })
    try {
      const result = await getMessages(projectId, 50, oldestTimestamp)
      const sorted = [...result.messages].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      set((state) => ({
        messages: [...sorted, ...state.messages],
        hasMore: result.has_more,
        isLoading: false,
        oldestTimestamp: sorted.length > 0 ? sorted[0].created_at : state.oldestTimestamp,
      }))
    } catch {
      set({ isLoading: false })
    }
  },

  setTyping: (userName: string, isTyping: boolean) => {
    set((state) => {
      const next = new Map(state.typingUsers)
      if (isTyping) {
        next.set(userName, { name: userName, timestamp: Date.now() })
      } else {
        next.delete(userName)
      }
      return { typingUsers: next }
    })
  },

  clearMessages: () => {
    set({ messages: [], hasMore: false, oldestTimestamp: null, unreadCount: 0 })
  },

  incrementUnread: () => {
    set((state) => ({ unreadCount: state.unreadCount + 1 }))
  },

  resetUnread: () => {
    set({ unreadCount: 0 })
  },
}))
