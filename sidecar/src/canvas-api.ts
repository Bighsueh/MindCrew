import { Router, Request, Response } from 'express'
import {
  addNote,
  editNote,
  deleteNote,
  moveNote,
  groupNotes,
  arrangeGroups,
  tidyNotes,
  autoLayout,
  checkOverlap,
  getCanvasState,
  getCanvasStateFull,
  batchUpdateCoordinates,
  updateSingleNoteCoordinates,
  updateNoteGroupId,
  updateNoteCites,
  setNoteMetadata,
} from './yjs-utils.js'
import { getMoveEvents } from './move-events.js'

export const canvasRouter = Router()

// POST /api/projects/:id/notes — add note
canvasRouter.post('/projects/:id/notes', (req: Request, res: Response) => {
  const { id } = req.params
  const {
    content, author, color, position, createdAt,
    // Spec 27 (Phase 36) 便條欄位
    kind, group_id,
    // Spec 06 v4.25 (Phase 42 C0)：cites（引用鏈）/ time_box_forced（C2 強推標記）
    cites, time_box_forced,
  } = req.body

  if (!content || !author) {
    res.status(400).json({ detail: 'content and author are required' })
    return
  }

  if (typeof author !== 'string' || author.length === 0) {
    console.warn('[canvas-api] rejected note: author must be a non-empty string', { author })
    res.status(400).json({ detail: 'author must be a non-empty string' })
    return
  }

  const createdAtOverride =
    typeof createdAt === 'string' && createdAt.length > 0 ? createdAt : undefined
  const concept = {
    kind: kind === 'label' ? 'label' as const : 'content' as const,
    group_id: typeof group_id === 'string' ? group_id : null,
    cites: Array.isArray(cites) ? (cites as string[]) : undefined,
    time_box_forced: time_box_forced === true,
  }
  const note = addNote(id, content, author, color || 'yellow', position, createdAtOverride, concept)
  res.status(201).json(note)
})

// PATCH /api/projects/:id/notes/:noteId — edit note
canvasRouter.patch('/projects/:id/notes/:noteId', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const { content } = req.body

  if (!content) {
    res.status(400).json({ detail: 'content is required' })
    return
  }

  const updated = editNote(id, noteId, content)
  if (!updated) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json(updated)
})

// PATCH /api/projects/:id/notes/:noteId/group — update semantic concept group_id
canvasRouter.patch('/projects/:id/notes/:noteId/group', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const { group_id } = req.body

  // group_id may be null to clear grouping
  if (!('group_id' in req.body)) {
    res.status(400).json({ detail: 'group_id is required' })
    return
  }

  const updated = updateNoteGroupId(id, noteId, group_id ?? null)
  if (!updated) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json(updated)
})

// PATCH /api/projects/:id/notes/:noteId/cites — 全量覆蓋引用鏈（Spec 06 v4.25, Phase 42 C0）
canvasRouter.patch('/projects/:id/notes/:noteId/cites', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const { cites } = req.body

  if (!Array.isArray(cites)) {
    res.status(400).json({ detail: 'cites must be an array of note ids' })
    return
  }

  const updated = updateNoteCites(id, noteId, cites)
  if (!updated) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json(updated)
})

// PATCH /api/projects/:id/notes/:noteId/metadata — 合併 metadata（gate_violation 標記）
canvasRouter.patch('/projects/:id/notes/:noteId/metadata', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const { metadata } = req.body

  if (!metadata || typeof metadata !== 'object') {
    res.status(400).json({ detail: 'metadata object is required' })
    return
  }

  const updated = setNoteMetadata(id, noteId, metadata as Record<string, unknown>)
  if (!updated) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json(updated)
})

// DELETE /api/projects/:id/notes/:noteId — delete note
canvasRouter.delete('/projects/:id/notes/:noteId', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const ok = deleteNote(id, noteId)
  if (!ok) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json({ message: 'Deleted' })
})

// POST /api/projects/:id/notes/:noteId/move — move to group
canvasRouter.post('/projects/:id/notes/:noteId/move', (req: Request, res: Response) => {
  const { id, noteId } = req.params
  const { target_group } = req.body

  if (!target_group) {
    res.status(400).json({ detail: 'target_group is required' })
    return
  }

  const ok = moveNote(id, noteId, target_group)
  if (!ok) {
    res.status(404).json({ detail: 'Note not found' })
    return
  }
  res.json({ message: 'Moved' })
})

// POST /api/projects/:id/groups — group notes [DEPRECATED: use Python arrange_notes]
canvasRouter.post('/projects/:id/groups', (req: Request, res: Response) => {
  console.warn('[DEPRECATED] POST /groups called — use Python Layout Engine instead')
  const { id } = req.params
  const { note_ids, group_name } = req.body

  if (!note_ids?.length || !group_name) {
    res.status(400).json({ detail: 'note_ids and group_name are required' })
    return
  }

  const group = groupNotes(id, note_ids, group_name)
  if (!group) {
    res.status(404).json({ detail: 'One or more notes not found' })
    return
  }
  res.status(201).json(group)
})

// POST /api/projects/:id/arrange-groups [DEPRECATED: use Python arrange_notes]
canvasRouter.post('/projects/:id/arrange-groups', (req: Request, res: Response) => {
  console.warn('[DEPRECATED] POST /arrange-groups called — use Python Layout Engine instead')
  const { id } = req.params
  const { arrangement } = req.body
  const ok = arrangeGroups(id, arrangement || 'grid')
  if (!ok) {
    res.status(404).json({ detail: 'Project not found' })
    return
  }
  res.json({ message: 'Groups arranged', arrangement: arrangement || 'grid' })
})

// POST /api/projects/:id/tidy [DEPRECATED: use Python tidy_area]
canvasRouter.post('/projects/:id/tidy', (req: Request, res: Response) => {
  console.warn('[DEPRECATED] POST /tidy called — use Python Layout Engine instead')
  const { id } = req.params
  const { scope, strategy } = req.body
  const ok = tidyNotes(id, scope || 'ungrouped', strategy || 'spread')
  if (!ok) {
    res.status(404).json({ detail: 'Project not found' })
    return
  }
  res.json({ message: 'Notes tidied', scope: scope || 'ungrouped', strategy: strategy || 'spread' })
})

// POST /api/projects/:id/auto-layout [DEPRECATED: use Python tidy_area]
canvasRouter.post('/projects/:id/auto-layout', (req: Request, res: Response) => {
  console.warn('[DEPRECATED] POST /auto-layout called — use Python Layout Engine instead')
  const { id } = req.params
  const { strategy } = req.body
  const ok = autoLayout(id, strategy || 'grid')
  if (!ok) {
    res.status(404).json({ detail: 'Project not found' })
    return
  }
  res.json({ message: 'Layout applied', strategy: strategy || 'grid' })
})

// GET /api/projects/:id/overlap-check — check for overlapping notes
canvasRouter.get('/projects/:id/overlap-check', (req: Request, res: Response) => {
  const { id } = req.params
  const result = checkOverlap(id)
  res.json(result)
})

// GET /api/projects/:id/state — get canvas state
canvasRouter.get('/projects/:id/state', (req: Request, res: Response) => {
  const { id } = req.params
  const state = getCanvasState(id)
  res.json(state)
})

// GET /api/projects/:id/canvas-state/full — full geometry for all shapes
canvasRouter.get('/projects/:id/canvas-state/full', (req: Request, res: Response) => {
  const { id } = req.params
  const shapes = getCanvasStateFull(id)
  res.json(shapes)
})

// GET /api/projects/:id/move-events?since=<seq> — move-delta 可讀事件（Spec 10 v2.0 §4.7）
canvasRouter.get('/projects/:id/move-events', (req: Request, res: Response) => {
  const { id } = req.params
  const since = Number.parseInt(String(req.query.since ?? '0'), 10)
  const result = getMoveEvents(id, Number.isFinite(since) ? since : 0)
  res.json(result)
})

// POST /api/projects/:id/batch-update-coordinates — atomic batch coordinate update
canvasRouter.post('/projects/:id/batch-update-coordinates', (req: Request, res: Response) => {
  const { id } = req.params
  const { updates, moved_by } = req.body

  if (!Array.isArray(updates) || updates.length === 0) {
    res.status(400).json({ detail: 'updates array is required and must not be empty' })
    return
  }

  for (const u of updates) {
    if (!u.id || typeof u.x !== 'number' || typeof u.y !== 'number') {
      res.status(400).json({ detail: 'Each update must have id (string), x (number), y (number)' })
      return
    }
  }

  const ok = batchUpdateCoordinates(
    id, updates, typeof moved_by === 'string' && moved_by.length > 0 ? moved_by : undefined,
  )
  if (!ok) {
    res.status(404).json({ detail: 'Project or one or more notes not found' })
    return
  }
  res.json({ message: 'Coordinates updated', count: updates.length })
})

// POST /api/projects/:id/staggered-update-coordinates — one-by-one with delays
canvasRouter.post('/projects/:id/staggered-update-coordinates', (req: Request, res: Response) => {
  const { id } = req.params
  const { updates, moving_by } = req.body
  // Phase 42 D1b (spec 12 §3.3 v4.1)：stagger 下限 400ms（舊預設 150 廢除——低於使用者跟不上）。
  const stagger_ms = Math.max(400, Number(req.body.stagger_ms) || 400)

  if (!Array.isArray(updates) || updates.length === 0) {
    res.status(400).json({ detail: 'updates array is required and must not be empty' })
    return
  }

  for (const u of updates) {
    if (!u.id || typeof u.x !== 'number' || typeof u.y !== 'number') {
      res.status(400).json({ detail: 'Each update must have id, x, y' })
      return
    }
  }

  // Apply updates one by one with stagger delays (non-blocking)
  updates.forEach((u: { id: string; x: number; y: number }, i: number) => {
    setTimeout(() => {
      updateSingleNoteCoordinates(id, u.id, u.x, u.y, moving_by)
    }, i * stagger_ms)
  })

  // Respond immediately — updates are applied asynchronously
  res.json({ message: 'Staggered updates scheduled', count: updates.length, stagger_ms })
})
