import type { ChatKind } from '../stores/chatStore'

// ── ChatKind 常數別名 ────────────────────────────────────────────────────────
export const GROUP: ChatKind = 'group'
export const PERSONAL: ChatKind = 'personal'

/** 取得 channel 顯示名稱（UI 預設文案）。 */
export const channelLabel = (kind: ChatKind): string =>
  kind === 'group' ? '群組聊天室' : '個人助理'

// ── chat_id 組裝 helpers ────────────────────────────────────────────────────
// 必須與後端 app/chat/chat_id.py 對齊：
//   - group:    `${project_id}:group`
//   - personal: `${project_id}:personal:${user_id}`

/** 群組 chat_id：每個 project 一個共用 channel。 */
export const buildGroupChatId = (projectId: string): string =>
  `${projectId}:group`

/** 個人 chat_id：每個 (project, user) 一個獨立 channel。 */
export const buildPersonalChatId = (projectId: string, userId: string): string =>
  `${projectId}:personal:${userId}`

/** 判斷一個 chat_id 是否屬於 personal kind。 */
export const isPersonalChatId = (chatId: string | null | undefined): boolean =>
  !!chatId && chatId.includes(':personal:')
