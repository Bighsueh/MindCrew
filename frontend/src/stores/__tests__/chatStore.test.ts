import { describe, it, expect, beforeEach, vi } from 'vitest'

// Stub browser globals before importing the store (api.ts reads localStorage at import time).
vi.hoisted(() => {
  const memoryStore: Record<string, string> = {}
  const localStorageStub = {
    getItem: (k: string): string | null => (k in memoryStore ? memoryStore[k] : null),
    setItem: (k: string, v: string): void => {
      memoryStore[k] = v
    },
    removeItem: (k: string): void => {
      delete memoryStore[k]
    },
    clear: (): void => {
      for (const k of Object.keys(memoryStore)) delete memoryStore[k]
    },
    key: (i: number): string | null => Object.keys(memoryStore)[i] ?? null,
    get length(): number {
      return Object.keys(memoryStore).length
    },
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).localStorage = localStorageStub
})

// Mock projectService.getMessages so loadHistory tests can run without network.
vi.mock('../../services/projectService', () => ({
  getMessages: vi.fn(),
}))

import { useChatStore } from '../chatStore'
import { getMessages } from '../../services/projectService'
import type { Message } from '../../types/models'

function makeMsg(id: string, content = 'hi'): Message {
  return {
    id,
    project_id: 'p1',
    sender_type: 'human',
    sender_id: 'u1',
    sender_name: 'Alice',
    content,
    stage: 'discover',
    created_at: new Date().toISOString(),
  }
}

describe('chatStore — dual channel', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('starts with both channels empty and unread=0', () => {
    const s = useChatStore.getState()
    expect(s.group.messages).toEqual([])
    expect(s.personal.messages).toEqual([])
    expect(s.group.unreadCount).toBe(0)
    expect(s.personal.unreadCount).toBe(0)
    expect(s.group.typingUsers).toEqual({})
    expect(s.personal.typingUsers).toEqual({})
  })

  it("addMessage('group') only mutates the group channel", () => {
    useChatStore.getState().addMessage('group', makeMsg('m1'))
    const s = useChatStore.getState()
    expect(s.group.messages).toHaveLength(1)
    expect(s.personal.messages).toHaveLength(0)
  })

  it("addMessage('personal') only mutates the personal channel", () => {
    useChatStore.getState().addMessage('personal', makeMsg('m1'))
    const s = useChatStore.getState()
    expect(s.personal.messages).toHaveLength(1)
    expect(s.group.messages).toHaveLength(0)
  })

  it('addMessage de-duplicates by id within a channel', () => {
    useChatStore.getState().addMessage('group', makeMsg('m1', 'first'))
    useChatStore.getState().addMessage('group', makeMsg('m1', 'second'))
    expect(useChatStore.getState().group.messages).toHaveLength(1)
    expect(useChatStore.getState().group.messages[0].content).toBe('first')
  })

  it('incrementUnread / resetUnread are isolated per channel', () => {
    useChatStore.getState().incrementUnread('group')
    useChatStore.getState().incrementUnread('group')
    useChatStore.getState().incrementUnread('personal')
    expect(useChatStore.getState().group.unreadCount).toBe(2)
    expect(useChatStore.getState().personal.unreadCount).toBe(1)

    useChatStore.getState().resetUnread('group')
    expect(useChatStore.getState().group.unreadCount).toBe(0)
    expect(useChatStore.getState().personal.unreadCount).toBe(1)
  })

  it('setTyping toggles per-user typing flag per channel', () => {
    useChatStore.getState().setTyping('group', 'u1', 'Alice', true)
    expect(useChatStore.getState().group.typingUsers).toEqual({ u1: 'Alice' })
    expect(useChatStore.getState().personal.typingUsers).toEqual({})

    useChatStore.getState().setTyping('group', 'u1', 'Alice', false)
    expect(useChatStore.getState().group.typingUsers).toEqual({})
  })

  it("resetChannel('personal') clears only personal", () => {
    useChatStore.getState().addMessage('group', makeMsg('g1'))
    useChatStore.getState().addMessage('personal', makeMsg('p1'))
    useChatStore.getState().resetChannel('personal')
    const s = useChatStore.getState()
    expect(s.group.messages).toHaveLength(1)
    expect(s.personal.messages).toHaveLength(0)
  })
})

describe('chatStore.loadHistory', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    vi.mocked(getMessages).mockReset()
  })

  it("loadHistory(projectId) defaults to 'group' kind and calls getMessages with chat_id={pid}:group", async () => {
    vi.mocked(getMessages).mockResolvedValue({ messages: [makeMsg('m1')], has_more: false })
    await useChatStore.getState().loadHistory('p1')
    expect(getMessages).toHaveBeenCalledWith('p1', { limit: 50, chatId: 'p1:group' })
    expect(useChatStore.getState().group.messages).toHaveLength(1)
    expect(useChatStore.getState().personal.messages).toHaveLength(0)
  })

  it("loadHistory(projectId, 'personal', userId) calls getMessages with chat_id={pid}:personal:{uid}", async () => {
    vi.mocked(getMessages).mockResolvedValue({ messages: [makeMsg('m2')], has_more: false })
    await useChatStore.getState().loadHistory('p1', 'personal', 'u42')
    expect(getMessages).toHaveBeenCalledWith('p1', { limit: 50, chatId: 'p1:personal:u42' })
    expect(useChatStore.getState().personal.messages).toHaveLength(1)
    expect(useChatStore.getState().group.messages).toHaveLength(0)
  })

  it("loadHistory(projectId, 'personal') without userId is a no-op (avoids leaking other users' messages)", async () => {
    await useChatStore.getState().loadHistory('p1', 'personal')
    expect(getMessages).not.toHaveBeenCalled()
    expect(useChatStore.getState().personal.isLoading).toBe(false)
  })

  it('on failure, isLoading is reset to false', async () => {
    vi.mocked(getMessages).mockRejectedValue(new Error('boom'))
    await useChatStore.getState().loadHistory('p1', 'group')
    expect(useChatStore.getState().group.isLoading).toBe(false)
  })
})
