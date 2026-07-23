/**
 * Move-delta 可讀事件（Spec 10 v2.0 §4.7，Phase 42 C0）。
 *
 * 觀察 shapes map 的 x/y/group_id 變化，產出「誰把什麼從哪移到哪、現在旁邊是誰」
 * 的語意事件，存 per-project in-memory ring buffer（cap 100、遞增 seq；重啟即失，
 * 後端以 Redis cursor 拉取，C0 裁定 1）。
 *
 * 歸因（moved_by）：
 *   - HTTP 寫入路徑 transaction origin = { moved_by: "<author tag>" }（AI 工具／系統讓位）
 *   - WS origin（前端 Yjs 同步進來的更新）= 真人拖曳 → moved_by = '__human__'，
 *     後端 ingest 時以席位表解析顯示名（單真人席前提）
 *   - 其餘（sidecar 內部 transact，無 origin）= 系統
 *
 * 真人拖曳以 ~800ms debounce 合併成一筆（C0 裁定 2）；AI / 系統移動即時成事件。
 */
import type * as Y from 'yjs'

export interface MoveNeighbor {
  id: string
  content: string
  group_id: string | null
}

export interface MoveEvent {
  seq: number
  note_id: string
  content: string
  moved_by: string
  is_human: boolean
  before: { x: number; y: number; group_id: string | null }
  after: { x: number; y: number; group_id: string | null }
  neighbors_after: MoveNeighbor[]
  moved_at: string
}

interface MovingNote {
  x: number
  y: number
  group_id?: string | null
  content?: string
  kind?: string
}

const RING_CAP = 100
const HUMAN_DEBOUNCE_MS = 800
// 鄰近判定：中心距 < ~320px（便條 200×150，約等於「緊鄰一格」），C0 裁定 2。
const NEIGHBOR_DISTANCE_PX = 320
const NEIGHBOR_LIMIT = 4
const CONTENT_SUMMARY_LEN = 24

interface ProjectBuffer {
  events: MoveEvent[]
  nextSeq: number
  // 真人拖曳 debounce：noteId → 移動前狀態 + timer
  pendingHuman: Map<string, { before: MoveEvent['before']; content: string; timer: NodeJS.Timeout }>
}

const buffers = new Map<string, ProjectBuffer>()
const observed = new Set<string>()

function getBuffer(projectId: string): ProjectBuffer {
  let buf = buffers.get(projectId)
  if (!buf) {
    buf = { events: [], nextSeq: 1, pendingHuman: new Map() }
    buffers.set(projectId, buf)
  }
  return buf
}

function summarize(content: unknown): string {
  const text = typeof content === 'string' ? content : ''
  return text.length > CONTENT_SUMMARY_LEN ? `${text.slice(0, CONTENT_SUMMARY_LEN)}…` : text
}

function computeNeighbors(
  shapes: Y.Map<unknown>,
  noteId: string,
  x: number,
  y: number,
): MoveNeighbor[] {
  const result: { dist: number; neighbor: MoveNeighbor }[] = []
  shapes.forEach((value: unknown, key: string) => {
    if (key === noteId) return
    const s = value as MovingNote | null
    if (!s || typeof s.x !== 'number' || typeof s.y !== 'number') return
    if (s.kind === 'label') return
    const dx = s.x - x
    const dy = s.y - y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < NEIGHBOR_DISTANCE_PX) {
      result.push({
        dist,
        neighbor: { id: key, content: summarize(s.content), group_id: s.group_id ?? null },
      })
    }
  })
  result.sort((a, b) => a.dist - b.dist)
  return result.slice(0, NEIGHBOR_LIMIT).map((r) => r.neighbor)
}

function pushEvent(
  projectId: string,
  shapes: Y.Map<unknown>,
  noteId: string,
  content: string,
  movedBy: string,
  isHuman: boolean,
  before: MoveEvent['before'],
): void {
  const current = shapes.get(noteId) as MovingNote | undefined
  if (!current) return
  const after = { x: current.x, y: current.y, group_id: current.group_id ?? null }
  // 無實質位移（座標與群皆未變）不成事件
  if (after.x === before.x && after.y === before.y && after.group_id === before.group_id) return

  const buf = getBuffer(projectId)
  buf.events.push({
    seq: buf.nextSeq++,
    note_id: noteId,
    content,
    moved_by: movedBy,
    is_human: isHuman,
    before,
    after,
    neighbors_after: computeNeighbors(shapes, noteId, after.x, after.y),
    moved_at: new Date().toISOString(),
  })
  if (buf.events.length > RING_CAP) {
    buf.events.splice(0, buf.events.length - RING_CAP)
  }
}

/**
 * 掛上 move observer（每 project 一次）。getShapesMap 與 index.ts 的
 * ensureDocListener 同時機呼叫。
 */
export function ensureMoveObserver(projectId: string, doc: Y.Doc): void {
  if (observed.has(projectId)) return
  observed.add(projectId)

  const shapes = doc.getMap('shapes')
  shapes.observe((event, transaction) => {
    const origin = transaction.origin as unknown
    const originMovedBy =
      origin && typeof origin === 'object' && 'moved_by' in (origin as Record<string, unknown>)
        ? String((origin as Record<string, unknown>).moved_by)
        : null
    // origin 非 moved_by 物件且非空 → WS client（真人）；null/undefined → sidecar 內部（系統）
    const isHuman = originMovedBy === null && origin != null

    event.changes.keys.forEach((change, key) => {
      if (change.action !== 'update') return
      const oldValue = change.oldValue as MovingNote | null
      const newValue = shapes.get(key) as MovingNote | undefined
      if (!oldValue || !newValue) return
      if (typeof oldValue.x !== 'number' || typeof newValue.x !== 'number') return
      const moved =
        oldValue.x !== newValue.x ||
        oldValue.y !== newValue.y ||
        (oldValue.group_id ?? null) !== (newValue.group_id ?? null)
      if (!moved) return

      const content = summarize(newValue.content)
      const before = {
        x: oldValue.x,
        y: oldValue.y,
        group_id: oldValue.group_id ?? null,
      }

      if (isHuman) {
        // 真人拖曳：debounce 合併（保留最早的 before，flush 時取最終 after）
        const buf = getBuffer(projectId)
        const pending = buf.pendingHuman.get(key)
        if (pending) {
          clearTimeout(pending.timer)
          pending.timer = setTimeout(() => flushHuman(projectId, shapes, key), HUMAN_DEBOUNCE_MS)
        } else {
          buf.pendingHuman.set(key, {
            before,
            content,
            timer: setTimeout(() => flushHuman(projectId, shapes, key), HUMAN_DEBOUNCE_MS),
          })
        }
      } else {
        pushEvent(
          projectId, shapes, key, content,
          originMovedBy ?? 'system', false, before,
        )
      }
    })
  })
}

function flushHuman(projectId: string, shapes: Y.Map<unknown>, noteId: string): void {
  const buf = getBuffer(projectId)
  const pending = buf.pendingHuman.get(noteId)
  if (!pending) return
  buf.pendingHuman.delete(noteId)
  pushEvent(projectId, shapes, noteId, pending.content, '__human__', true, pending.before)
}

/** GET /move-events 用：回 seq > since 的事件與最新 seq。 */
export function getMoveEvents(
  projectId: string,
  since: number,
): { events: MoveEvent[]; latest_seq: number } {
  const buf = buffers.get(projectId)
  if (!buf) return { events: [], latest_seq: since }
  const events = buf.events.filter((e) => e.seq > since)
  return { events, latest_seq: buf.nextSeq - 1 }
}
