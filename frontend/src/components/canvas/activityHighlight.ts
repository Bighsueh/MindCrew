/**
 * Phase 24 — 對話活動高亮共用層。
 *
 * 規格：_discussion/specs/19-activity-highlight-draft.md
 *
 * 「對話活動」= 同一作者 (type:name) + 時間差在 ACTIVITY_WINDOW_MS 內。
 * 配對 key 採 `${type}:${name}`，因為便利貼 meta.author 目前只存 display name。
 */

import { parseAuthor } from './NoteAuthorOverlay'

export const ACTIVITY_WINDOW_MS = 30_000

export type ActivitySource = 'chat' | 'note'

export interface ActivityAnchor {
  /** `${type}:${name}` */
  key: string
  /** epoch ms；NaN 代表無時間資訊（缺 created_at） */
  anchorMs: number
  source: ActivitySource
}

export function chatActivityKey(
  senderType: string,
  senderName: string,
): string {
  const type = senderType === 'human' ? 'human' : senderType === 'ai' ? 'ai' : 'other'
  return `${type}:${senderName}`
}

export function noteActivityKey(rawAuthor: unknown): string {
  const { name, type } = parseAuthor(rawAuthor)
  return `${type}:${name}`
}

/**
 * 解析 ISO 8601 / sidecar createdAt 字串為 epoch ms。
 * 缺失或無效 → NaN（呼叫端應判斷）。
 */
export function parseCreatedAt(raw: unknown): number {
  if (typeof raw !== 'string' || raw.length === 0) return NaN
  const ms = Date.parse(raw)
  return Number.isFinite(ms) ? ms : NaN
}

/**
 * 判斷某 artifact 是否落在 anchor 的時間窗內。
 * - 若 anchorMs 為 NaN 或 otherMs 為 NaN → 退化為「不限時間，只比作者」。
 *   呼叫端仍需自行比對 key。
 */
export function isInActivityWindow(
  otherMs: number,
  anchorMs: number,
  windowMs: number = ACTIVITY_WINDOW_MS,
): boolean {
  if (!Number.isFinite(otherMs) || !Number.isFinite(anchorMs)) return true
  return Math.abs(otherMs - anchorMs) <= windowMs
}

/**
 * 完整配對：key 必須相等且時間窗成立。
 */
export function isInActivity(
  candidate: { key: string; otherMs: number },
  anchor: ActivityAnchor,
  windowMs: number = ACTIVITY_WINDOW_MS,
): boolean {
  if (candidate.key !== anchor.key) return false
  return isInActivityWindow(candidate.otherMs, anchor.anchorMs, windowMs)
}

/**
 * Phase 24 — 聊天氣泡高亮樣式計算（pure，可單測）。
 *
 * 回傳 inline style：
 *  - 未在 active 視窗 → undefined（不疊樣式）
 *  - 在視窗內 → box-shadow 2px ring (accent)
 *  - 同時是觸發來源（chat 自己 hover/click） → 額外加 outline + offset 區分
 *
 * 抽出原因：避免在 component 測試中需要 jsdom，純函式即可驗證高亮決策。
 */
export interface ChatHighlightStyle {
  boxShadow: string
  outline?: string
  outlineOffset?: string
}

/**
 * Phase 24 — 便利貼高亮 overlay 樣式計算（pure，可單測）。
 *
 * 回傳：
 *  - null：該便利貼不在 active 視窗內 → 不渲染 overlay
 *  - 物件：border / outline 的 inline 值（單位 px）
 */
export interface NoteHighlightStyle {
  border: string
  outline?: string
  outlineOffset?: string
}

export function computeNoteHighlightStyle(args: {
  noteKey: string
  noteCreatedAtMs: number
  active: ActivityAnchor | null
  accentColor: string
  zoom: number
}): NoteHighlightStyle | null {
  const { noteKey, noteCreatedAtMs, active, accentColor, zoom } = args
  if (!active) return null
  if (!isInActivity({ key: noteKey, otherMs: noteCreatedAtMs }, active)) return null
  const isSource = active.source === 'note' && active.anchorMs === noteCreatedAtMs
  const borderPx = Math.max(2, 2 * zoom)
  return {
    border: `${borderPx}px solid ${accentColor}`,
    outline: isSource ? `2px solid ${accentColor}` : undefined,
    outlineOffset: isSource ? '2px' : undefined,
  }
}

export function computeChatHighlightStyle(args: {
  key: string
  anchorMs: number
  active: ActivityAnchor | null
  accentColor: string
}): ChatHighlightStyle | undefined {
  const { key, anchorMs, active, accentColor } = args
  if (!active) return undefined
  if (!isInActivity({ key, otherMs: anchorMs }, active)) return undefined
  const isSource = active.source === 'chat' && active.anchorMs === anchorMs
  return {
    boxShadow: `0 0 0 2px ${accentColor}`,
    outline: isSource ? `2px solid ${accentColor}` : undefined,
    outlineOffset: isSource ? '2px' : undefined,
  }
}
