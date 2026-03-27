import * as Y from 'yjs'

// Per-project Yjs doc store
const docs = new Map<string, Y.Doc>()

export function getOrCreateDoc(projectId: string): Y.Doc {
  let doc = docs.get(projectId)
  if (!doc) {
    doc = new Y.Doc()
    docs.set(projectId, doc)
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
const GRID_COL_WIDTH = 250
const GRID_ROW_HEIGHT = 200
const GRID_COLS = 5

// Parse position hint like "near:note_123" or absolute {x, y}
// Falls back to grid layout based on current note count
function resolvePosition(
  doc: Y.Doc,
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
      // Place near the reference note with slight offset
      return {
        x: refNote.x + GRID_COL_WIDTH + Math.random() * 20 - 10,
        y: refNote.y + Math.random() * 20 - 10,
      }
    }
  }
  // Auto grid layout: place in next available grid cell
  const shapes = getShapesMap(doc)
  const count = shapes.size
  const col = count % GRID_COLS
  const row = Math.floor(count / GRID_COLS)
  return {
    x: GRID_START_X + col * GRID_COL_WIDTH + Math.random() * 15,
    y: GRID_START_Y + row * GRID_ROW_HEIGHT + Math.random() * 15,
  }
}

export function addNote(
  projectId: string,
  content: string,
  author: string,
  color: string = 'yellow',
  position?: string | { x: number; y: number }
): NoteShape {
  const doc = getOrCreateDoc(projectId)
  const shapes = getShapesMap(doc)
  const pos = resolvePosition(doc, position)
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
