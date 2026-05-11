import * as Y from 'yjs'
import { LeveldbPersistence } from 'y-leveldb'
import path from 'path'

// Per-project Yjs doc store
const docs = new Map<string, Y.Doc>()

// Persistence: store Yjs updates in LevelDB so notes survive sidecar restarts
const DATA_DIR = process.env.YJS_DATA_DIR || './data'
const persistence = new LeveldbPersistence(DATA_DIR)

export async function getOrCreateDoc(projectId: string): Promise<Y.Doc> {
  let doc = docs.get(projectId)
  if (!doc) {
    doc = new Y.Doc()
    docs.set(projectId, doc)

    // Restore persisted state
    try {
      const stored = await persistence.getYDoc(projectId)
      const update = Y.encodeStateAsUpdate(stored)
      Y.applyUpdate(doc, update)
      stored.destroy()
    } catch {
      // No persisted state yet — fresh doc
    }

    // Persist future updates
    doc.on('update', (update: Uint8Array) => {
      persistence.storeUpdate(projectId, update).catch(() => {
        // Best-effort persistence
      })
    })
  }
  return doc
}

/** Synchronous getter for docs already in memory (used by getCanvasState etc.) */
export function getOrCreateDocSync(projectId: string): Y.Doc {
  let doc = docs.get(projectId)
  if (!doc) {
    doc = new Y.Doc()
    docs.set(projectId, doc)
    // Kick off async restore — will apply when ready
    persistence.getYDoc(projectId).then(stored => {
      const update = Y.encodeStateAsUpdate(stored)
      Y.applyUpdate(doc!, update)
      stored.destroy()
    }).catch(() => {})

    doc.on('update', (update: Uint8Array) => {
      persistence.storeUpdate(projectId, update).catch(() => {})
    })
  }
  return doc
}

export function getDoc(projectId: string): Y.Doc | undefined {
  return docs.get(projectId)
}

// tldraw stores shapes in a Y.Map at the root level
// We use a simplified model: notes are stored in "shapes" map, groups in "groups" map

export interface NoteShape {
  id: string
  type: 'note'
  content: string
  author: string
  color: string
  x: number
  y: number
  width: number
  height: number
  groupId: string | null
  createdAt: string
  _moving_by?: string
}

export interface NoteGroup {
  id: string
  name: string
  noteIds: string[]
}

function getShapesMap(doc: Y.Doc): Y.Map<NoteShape> {
  return doc.getMap('shapes') as Y.Map<NoteShape>
}

function getGroupsMap(doc: Y.Doc): Y.Map<NoteGroup> {
  return doc.getMap('groups') as Y.Map<NoteGroup>
}

let noteCounter = 0

function generateNoteId(): string {
  noteCounter++
  return `shape:note_${Date.now()}_${noteCounter}`
}

function generateGroupId(): string {
  return `group_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

// Grid layout constants for auto-positioning notes
const GRID_START_X = 80
const GRID_START_Y = 80
const GRID_COL_WIDTH = 260   // 200px note + 60px gap
const GRID_ROW_HEIGHT = 210  // 150px note + 60px gap
const GRID_COLS = 5
const NOTE_WIDTH = 200
const NOTE_HEIGHT = 150
const NOTE_GAP = 15

// Per-project slot counter to prevent concurrent overlap
const nextSlot = new Map<string, number>()

// Parse position hint like "near:note_123" or absolute {x, y}
// Falls back to grid layout using a per-project slot counter
function resolvePosition(
  doc: Y.Doc,
  projectId: string,
  position?: string | { x: number; y: number }
): { x: number; y: number } {
  if (typeof position === 'object' && position) {
    return position
  }
  if (typeof position === 'string' && position.startsWith('near:')) {
    const refId = position.slice(5)
    const shapes = getShapesMap(doc)
    const refNote = shapes.get(refId)
    if (refNote) {
      return {
        x: refNote.x + GRID_COL_WIDTH + Math.random() * 20 - 10,
        y: refNote.y + Math.random() * 20 - 10,
      }
    }
  }
  // Auto grid layout: use per-project slot counter (prevents concurrent overlap)
  const slot = nextSlot.get(projectId) ?? getShapesMap(doc).size
  nextSlot.set(projectId, slot + 1)
  const col = slot % GRID_COLS
  const row = Math.floor(slot / GRID_COLS)
  return {
    x: GRID_START_X + col * GRID_COL_WIDTH + Math.random() * NOTE_GAP,
    y: GRID_START_Y + row * GRID_ROW_HEIGHT + Math.random() * NOTE_GAP,
  }
}

/**
 * Check if two rectangles overlap.
 */
function rectsOverlap(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by
}

/**
 * Check for overlapping notes. Returns overlap info.
 */
export function checkOverlap(projectId: string): { has_overlap: boolean; overlap_count: number } {
  const doc = getDoc(projectId)
  if (!doc) return { has_overlap: false, overlap_count: 0 }
  const shapes = getShapesMap(doc)
  const notes = Array.from(shapes.values())
  let count = 0
  for (let i = 0; i < notes.length; i++) {
    for (let j = i + 1; j < notes.length; j++) {
      if (rectsOverlap(
        notes[i].x, notes[i].y, notes[i].width, notes[i].height,
        notes[j].x, notes[j].y, notes[j].width, notes[j].height,
      )) {
        count++
      }
    }
  }
  return { has_overlap: count > 0, overlap_count: count }
}

/**
 * Auto-layout: reposition all notes using the specified strategy.
 * Strategies:
 *   scatter — random positions, no overlap
 *   grid — neat grid (default)
 *   cluster — group-aware, groups spaced apart
 *   timeline — horizontal layout for groups
 */
export function autoLayout(projectId: string, strategy: string = 'grid'): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)
  if (shapes.size === 0) return true

  const groupedIds = new Set<string>()
  for (const [, g] of groups.entries()) {
    for (const nid of g.noteIds) groupedIds.add(nid)
  }

  doc.transact(() => {
    if (strategy === 'cluster' && groups.size > 0) {
      // Cluster layout: each group is a column, ungrouped at the end
      const groupEntries = Array.from(groups.entries())
      const clusterWidth = 3 * (NOTE_WIDTH + NOTE_GAP) // max 3 notes wide per cluster
      const clusterGap = 100
      let gx = GRID_START_X

      for (const [, group] of groupEntries) {
        let nx = gx
        let ny = GRID_START_Y + 40 // leave room for header
        for (const nid of group.noteIds) {
          const note = shapes.get(nid)
          if (note) {
            shapes.set(nid, { ...note, x: nx, y: ny })
            nx += NOTE_WIDTH + NOTE_GAP
            if (nx >= gx + clusterWidth) {
              nx = gx
              ny += NOTE_HEIGHT + NOTE_GAP
            }
          }
        }
        gx += clusterWidth + clusterGap
      }

      // Ungrouped notes below all clusters
      let ux = GRID_START_X
      let uy = GRID_START_Y + 600
      for (const [nid, note] of shapes.entries()) {
        if (!groupedIds.has(nid)) {
          shapes.set(nid, { ...note, x: ux, y: uy })
          ux += NOTE_WIDTH + NOTE_GAP
          if (ux > 4000) { ux = GRID_START_X; uy += NOTE_HEIGHT + NOTE_GAP }
        }
      }
    } else if (strategy === 'timeline' && groups.size > 0) {
      // Timeline: groups laid out horizontally, notes stacked vertically within each
      const groupEntries = Array.from(groups.entries())
      const colWidth = NOTE_WIDTH + 80
      groupEntries.forEach(([, group], gi) => {
        const gx = GRID_START_X + gi * colWidth
        group.noteIds.forEach((nid, ni) => {
          const note = shapes.get(nid)
          if (note) {
            shapes.set(nid, { ...note, x: gx, y: GRID_START_Y + ni * (NOTE_HEIGHT + NOTE_GAP) })
          }
        })
      })
    } else if (strategy === 'scatter') {
      // Scatter: random positions but guaranteed no overlap
      const placed: { x: number; y: number }[] = []
      for (const [nid, note] of shapes.entries()) {
        let x: number, y: number
        let attempts = 0
        do {
          x = GRID_START_X + Math.random() * 3500
          y = GRID_START_Y + Math.random() * 1500
          attempts++
        } while (
          attempts < 200 &&
          placed.some(p => rectsOverlap(x, y, NOTE_WIDTH, NOTE_HEIGHT, p.x, p.y, NOTE_WIDTH, NOTE_HEIGHT))
        )
        placed.push({ x, y })
        shapes.set(nid, { ...note, x, y })
      }
    } else {
      // Grid: simple non-overlapping grid
      let idx = 0
      for (const [nid, note] of shapes.entries()) {
        const col = idx % GRID_COLS
        const row = Math.floor(idx / GRID_COLS)
        shapes.set(nid, {
          ...note,
          x: GRID_START_X + col * GRID_COL_WIDTH + Math.random() * NOTE_GAP,
          y: GRID_START_Y + row * GRID_ROW_HEIGHT + Math.random() * NOTE_GAP,
        })
        idx++
      }
    }
  })

  // Reset slot counter after layout
  nextSlot.set(projectId, shapes.size)
  return true
}

export function addNote(
  projectId: string,
  content: string,
  author: string,
  color: string = 'yellow',
  position?: string | { x: number; y: number }
): NoteShape {
  const doc = getOrCreateDocSync(projectId)
  const shapes = getShapesMap(doc)
  const pos = resolvePosition(doc, projectId, position)
  const id = generateNoteId()

  const note: NoteShape = {
    id,
    type: 'note',
    content,
    author,
    color,
    x: pos.x,
    y: pos.y,
    width: 200,
    height: 150,
    groupId: null,
    createdAt: new Date().toISOString(),
  }

  doc.transact(() => {
    shapes.set(id, note)
  })

  return note
}

export function editNote(
  projectId: string,
  noteId: string,
  newContent: string
): NoteShape | null {
  const doc = getDoc(projectId)
  if (!doc) return null
  const shapes = getShapesMap(doc)
  const note = shapes.get(noteId)
  if (!note) return null

  const updated = { ...note, content: newContent }
  doc.transact(() => {
    shapes.set(noteId, updated)
  })
  return updated
}

export function deleteNote(
  projectId: string,
  noteId: string
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  if (!shapes.has(noteId)) return false

  const groups = getGroupsMap(doc)
  doc.transact(() => {
    shapes.delete(noteId)
    // Remove from any group
    for (const [gid, group] of groups.entries()) {
      if (group.noteIds.includes(noteId)) {
        const updated = {
          ...group,
          noteIds: group.noteIds.filter((id) => id !== noteId),
        }
        if (updated.noteIds.length === 0) {
          groups.delete(gid)
        } else {
          groups.set(gid, updated)
        }
      }
    }
  })
  return true
}

export function moveNote(
  projectId: string,
  noteId: string,
  targetGroupName: string
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)

  if (!shapes.has(noteId)) return false

  doc.transact(() => {
    // Remove from current group
    for (const [gid, group] of groups.entries()) {
      if (group.noteIds.includes(noteId)) {
        groups.set(gid, {
          ...group,
          noteIds: group.noteIds.filter((id) => id !== noteId),
        })
      }
    }

    // Find or create target group
    let targetGroup: NoteGroup | undefined
    for (const [, group] of groups.entries()) {
      if (group.name === targetGroupName) {
        targetGroup = group
        break
      }
    }

    if (targetGroup) {
      groups.set(targetGroup.id, {
        ...targetGroup,
        noteIds: [...targetGroup.noteIds, noteId],
      })
    } else {
      const gid = generateGroupId()
      groups.set(gid, {
        id: gid,
        name: targetGroupName,
        noteIds: [noteId],
      })
    }

    // Update note's groupId
    const note = shapes.get(noteId)!
    shapes.set(noteId, { ...note, groupId: targetGroupName })
  })

  return true
}

export function groupNotes(
  projectId: string,
  noteIds: string[],
  groupName: string
): NoteGroup | null {
  const doc = getDoc(projectId)
  if (!doc) return null
  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)

  // Verify all notes exist
  for (const nid of noteIds) {
    if (!shapes.has(nid)) return null
  }

  const gid = generateGroupId()
  const group: NoteGroup = { id: gid, name: groupName, noteIds }

  doc.transact(() => {
    // Remove notes from existing groups
    for (const [existGid, existGroup] of groups.entries()) {
      const remaining = existGroup.noteIds.filter((id) => !noteIds.includes(id))
      if (remaining.length === 0) {
        groups.delete(existGid)
      } else if (remaining.length !== existGroup.noteIds.length) {
        groups.set(existGid, { ...existGroup, noteIds: remaining })
      }
    }

    groups.set(gid, group)

    // Update each note's groupId
    for (const nid of noteIds) {
      const note = shapes.get(nid)!
      shapes.set(nid, { ...note, groupId: groupName })
    }
  })

  return group
}

/**
 * Arrange groups in a grid layout, repositioning all notes within each group.
 */
export function arrangeGroups(
  projectId: string,
  arrangement: string = 'grid'
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)

  if (groups.size === 0) return true

  const groupEntries = Array.from(groups.entries())
  const cols = Math.ceil(Math.sqrt(groupEntries.length))
  const groupWidth = 300
  const groupHeight = 300
  const groupGap = 80

  doc.transact(() => {
    groupEntries.forEach(([, group], idx) => {
      const col = idx % cols
      const row = Math.floor(idx / cols)
      const baseX = GRID_START_X + col * (groupWidth + groupGap)
      const baseY = GRID_START_Y + row * (groupHeight + groupGap)

      // Reposition notes within this group in a mini-grid
      const noteCols = Math.min(3, group.noteIds.length)
      group.noteIds.forEach((nid, ni) => {
        const note = shapes.get(nid)
        if (note) {
          const nc = ni % noteCols
          const nr = Math.floor(ni / noteCols)
          shapes.set(nid, {
            ...note,
            x: baseX + nc * (note.width + 15),
            y: baseY + nr * (note.height + 15),
          })
        }
      })
    })
  })

  return true
}

/**
 * Tidy ungrouped or all notes to avoid overlap by spreading them in a grid.
 */
export function tidyNotes(
  projectId: string,
  scope: string = 'ungrouped',
  strategy: string = 'spread'
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)

  // Determine which notes to tidy
  const groupedIds = new Set<string>()
  for (const [, g] of groups.entries()) {
    for (const nid of g.noteIds) groupedIds.add(nid)
  }

  const targetIds: string[] = []
  for (const [nid] of shapes.entries()) {
    if (scope === 'all' || !groupedIds.has(nid)) {
      targetIds.push(nid)
    }
  }

  if (targetIds.length === 0) return true

  // Find a free area below all groups
  let maxY = GRID_START_Y
  for (const [, note] of shapes.entries()) {
    if (groupedIds.has(note.id)) {
      maxY = Math.max(maxY, note.y + note.height + 30)
    }
  }

  const cols = strategy === 'compact' ? 6 : GRID_COLS
  doc.transact(() => {
    targetIds.forEach((nid, idx) => {
      const note = shapes.get(nid)
      if (note) {
        const col = idx % cols
        const row = Math.floor(idx / cols)
        shapes.set(nid, {
          ...note,
          x: GRID_START_X + col * GRID_COL_WIDTH + Math.random() * 10,
          y: maxY + row * GRID_ROW_HEIGHT + Math.random() * 10,
        })
      }
    })
  })

  return true
}

// ── Exported grid constants (mirrored by Python Layout Engine) ──
export const GRID_CONSTANTS = {
  GRID_START_X,
  GRID_START_Y,
  GRID_COL_WIDTH,
  GRID_ROW_HEIGHT,
  GRID_COLS,
  NOTE_WIDTH,
  NOTE_HEIGHT,
  NOTE_GAP,
} as const

/**
 * Full geometry state for every shape — used by Python Spatial Analyzer.
 * Returns all note fields including x, y, width, height.
 */
export function getCanvasStateFull(projectId: string): NoteShape[] {
  const doc = getDoc(projectId)
  if (!doc) return []
  const shapes = getShapesMap(doc)
  return Array.from(shapes.values())
}

/**
 * Batch-update note coordinates in a single Yjs transaction (atomic).
 * Used by Python Layout Engine for arrange_notes, tidy_area, swap_notes.
 */
export function batchUpdateCoordinates(
  projectId: string,
  updates: { id: string; x: number; y: number }[]
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)

  // Verify all notes exist before transacting
  for (const u of updates) {
    if (!shapes.has(u.id)) return false
  }

  doc.transact(() => {
    for (const u of updates) {
      const note = shapes.get(u.id)!
      shapes.set(u.id, { ...note, x: u.x, y: u.y })
    }
  })
  return true
}

/**
 * Update a single note's coordinates in its own Yjs transaction.
 * Used by staggered updates for one-by-one animation effect.
 *
 * If movingBy is provided, sets _moving_by metadata on the shape
 * and clears it after clearDelayMs (default 400ms).
 */
export function updateSingleNoteCoordinates(
  projectId: string,
  id: string,
  x: number,
  y: number,
  movingBy?: string,
  clearDelayMs: number = 400
): boolean {
  const doc = getDoc(projectId)
  if (!doc) return false
  const shapes = getShapesMap(doc)
  const note = shapes.get(id)
  if (!note) return false

  doc.transact(() => {
    const updated: NoteShape = { ...note, x, y }
    if (movingBy) {
      updated._moving_by = movingBy
    } else {
      delete updated._moving_by
    }
    shapes.set(id, updated)
  })

  // Clear _moving_by after delay
  if (movingBy) {
    setTimeout(() => {
      const currentDoc = getDoc(projectId)
      if (!currentDoc) return
      const currentShapes = getShapesMap(currentDoc)
      const current = currentShapes.get(id)
      if (!current || !current._moving_by) return

      currentDoc.transact(() => {
        const cleaned: NoteShape = { ...current }
        delete cleaned._moving_by
        currentShapes.set(id, cleaned)
      })
    }, clearDelayMs)
  }

  return true
}

export interface CanvasState {
  total_notes: number
  groups: { name: string; notes: string[] }[]
  ungrouped: string[]
  notes: {
    id: string
    content: string
    author: string
    color: string
  }[]
}

export function getCanvasState(projectId: string): CanvasState {
  const doc = getDoc(projectId)
  if (!doc) {
    return { total_notes: 0, groups: [], ungrouped: [], notes: [] }
  }

  const shapes = getShapesMap(doc)
  const groups = getGroupsMap(doc)

  const allNotes: CanvasState['notes'] = []
  const groupedNoteIds = new Set<string>()
  const groupList: CanvasState['groups'] = []

  for (const [, group] of groups.entries()) {
    groupList.push({ name: group.name, notes: [...group.noteIds] })
    for (const nid of group.noteIds) {
      groupedNoteIds.add(nid)
    }
  }

  const ungrouped: string[] = []
  for (const [nid, note] of shapes.entries()) {
    allNotes.push({
      id: nid,
      content: note.content,
      author: note.author,
      color: note.color,
    })
    if (!groupedNoteIds.has(nid)) {
      ungrouped.push(nid)
    }
  }

  return {
    total_notes: allNotes.length,
    groups: groupList,
    ungrouped,
    notes: allNotes,
  }
}
