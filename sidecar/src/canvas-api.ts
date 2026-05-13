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
} from './yjs-utils.js'

export const canvasRouter = Router()

// POST /api/projects/:id/notes — add note
canvasRouter.post('/projects/:id/notes', (req: Request, res: Response) => {
  const { id } = req.params
  const { content, author, color, position } = req.body

  if (!content || !author) {
    res.status(400).json({ detail: 'content and author are required' })
    return
  }

  if (typeof author !== 'string' || author.length === 0) {
    console.warn('[canvas-api] rejected note: author must be a non-empty string', { author })
    res.status(400).json({ detail: 'author must be a non-empty string' })
    return
  }

  const note = addNote(id, content, author, color || 'yellow', position)
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

// POST /api/projects/:id/batch-update-coordinates — atomic batch coordinate update
canvasRouter.post('/projects/:id/batch-update-coordinates', (req: Request, res: Response) => {
  const { id } = req.params
  const { updates } = req.body

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

  const ok = batchUpdateCoordinates(id, updates)
  if (!ok) {
    res.status(404).json({ detail: 'Project or one or more notes not found' })
    return
  }
  res.json({ message: 'Coordinates updated', count: updates.length })
})

// POST /api/projects/:id/staggered-update-coordinates — one-by-one with delays
canvasRouter.post('/projects/:id/staggered-update-coordinates', (req: Request, res: Response) => {
  const { id } = req.params
  const { updates, stagger_ms = 150, moving_by } = req.body

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
