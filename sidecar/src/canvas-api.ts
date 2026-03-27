import { Router, Request, Response } from 'express'
import {
  addNote,
  editNote,
  deleteNote,
  moveNote,
  groupNotes,
  getCanvasState,
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

// POST /api/projects/:id/groups — group notes
canvasRouter.post('/projects/:id/groups', (req: Request, res: Response) => {
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

// GET /api/projects/:id/state — get canvas state
canvasRouter.get('/projects/:id/state', (req: Request, res: Response) => {
  const { id } = req.params
  const state = getCanvasState(id)
  res.json(state)
})
