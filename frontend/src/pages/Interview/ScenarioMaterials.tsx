import { useEffect, useState } from 'react'
import { interviewError, interviewService, type InterviewNote, type ScenarioWorkspaceData } from '../../services/interviewService'
import { NotePreview } from './InterviewNotes'
import { dateFormat, input, panel, primary, secondary } from './styles'

export function ScenarioMaterials({ id, sessionId, draft, onEdit, onSave }: {
  id: string
  sessionId?: string
  draft?: string
  onEdit: (body: string) => void
  onSave: (body: string) => void
}) {
  const [workspace, setWorkspace] = useState<ScenarioWorkspaceData>()
  const [preview, setPreview] = useState(false)
  const [guide, setGuide] = useState<{ title: string; body: string }>()
  const [noteBusy, setNoteBusy] = useState(false)
  const [guideBusy, setGuideBusy] = useState(false)
  const [guideError, setGuideError] = useState('')
  const [noteError, setNoteError] = useState('')
  const [load, setLoad] = useState(0)
  const note = draft ?? workspace?.note.body ?? ''
  const current = workspace?.guides.find(item => item.id === workspace.current_guide_id)

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.workspace(id, controller.signal).then(next => {
      if (!controller.signal.aborted) setWorkspace(next)
    }).catch(err => {
      if (!controller.signal.aborted) setNoteError(interviewError(err))
    })
    return () => controller.abort()
  }, [id, load])

  async function saveNote() {
    if (noteBusy) return
    setNoteBusy(true)
    setNoteError('')
    try {
      const saved = await interviewService.saveScenarioNote(id, note)
      setWorkspace(data => data && { ...data, note: saved })
      onSave(note)
    } catch (err) {
      setNoteError(interviewError(err))
    } finally {
      setNoteBusy(false)
    }
  }

  async function changeGuide(guideId: string) {
    setGuideBusy(true)
    setGuideError('')
    try {
      await interviewService.selectGuide(id, guideId || null)
      setWorkspace(data => data && { ...data, current_guide_id: guideId || null })
    } catch (err) {
      setGuideError(interviewError(err))
    } finally {
      setGuideBusy(false)
    }
  }

  async function saveGuide() {
    if (!guide?.title.trim() || guideBusy) return
    setGuideBusy(true)
    setGuideError('')
    try {
      const saved = await interviewService.saveGuide(id, guide.title, guide.body)
      setWorkspace(data => data && { ...data, guides: [saved, ...data.guides], current_guide_id: saved.id })
      setGuide(undefined)
    } catch (err) {
      setGuideError(interviewError(err))
    } finally {
      setGuideBusy(false)
    }
  }

  if (!workspace) return <section className={`${panel} p-4`}>
    <h2 className="mb-2 text-lg font-semibold text-text">筆記與訪綱</h2>
    {noteError ? <>
      <p role="alert" className="text-sm text-error">{noteError}</p>
      <button type="button" className={secondary} onClick={() => { setNoteError(''); setLoad(value => value + 1) }}>重新載入</button>
    </> : <p role="status" className="text-sm text-text-muted">載入情境工作區…</p>}
  </section>

  return (
    <div className="space-y-4">
      <section className={`${panel} space-y-3 p-4`}>
        <h2 className="text-lg font-semibold text-text">我的筆記</h2>
        {noteError && <p role="alert" className="text-sm text-error">{noteError}</p>}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={secondary} aria-pressed={!preview} onClick={() => setPreview(false)}>編輯</button>
          <button type="button" className={secondary} aria-pressed={preview} onClick={() => setPreview(true)}>預覽</button>
        </div>
        {preview ? <div className="space-y-2 whitespace-pre-wrap break-words rounded border border-border p-2 text-sm text-text [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5">
          {note ? <NotePreview body={note} /> : '尚無筆記。'}
        </div> : <textarea aria-label="我的情境筆記" className={input} rows={6} maxLength={30000} value={note} onChange={event => onEdit(event.target.value)} />}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={primary} disabled={noteBusy || note === workspace.note.body} onClick={() => void saveNote()}>
            {noteBusy ? '儲存中…' : noteError ? '重試儲存' : '儲存筆記'}
          </button>
          <button type="button" className={secondary} disabled={guideBusy || !!guide} onClick={() => setGuide({ title: '', body: note })}>整理為訪綱</button>
        </div>
        <p role="status" className="text-xs text-text-muted">
          {note !== workspace.note.body ? '有未儲存變更' : workspace.note.updated_at
            ? `已儲存 · ${dateFormat.format(new Date(workspace.note.updated_at))}` : ''}
        </p>
        {sessionId && <LegacySessionNote key={sessionId} id={sessionId} onCopy={body => {
          const merged = note ? `${note}\n\n${body}` : body
          if (merged.length > 30000) {
            setNoteError('複製後的筆記超過 30000 字。請只複製所需片段。')
            return
          }
          onEdit(merged)
          setPreview(false)
        }} />}
      </section>
      <section className={`${panel} space-y-3 p-4`}>
        <h2 className="text-lg font-semibold text-text">我的訪綱</h2>
        {guideError && <p role="alert" className="text-sm text-error">{guideError}</p>}
        <label className="block text-sm text-text">載入訪綱
          <select className={input} value={workspace.current_guide_id ?? ''} disabled={guideBusy || !workspace.guides.length}
            onChange={event => void changeGuide(event.target.value)}>
            <option value="">未選訪綱</option>
            {workspace.guides.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </label>
        {current && <article className="space-y-2">
          <h3 className="font-medium text-text">{current.title}</h3>
          <div className="space-y-2 whitespace-pre-wrap break-words text-sm text-text [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5">
            <NotePreview body={current.body} />
          </div>
          <button type="button" className={secondary} disabled={guideBusy || !!guide} onClick={() => setGuide({ title: current.title, body: current.body })}>編輯後另存</button>
        </article>}
        {guide && <form className="space-y-2 border-t border-border pt-3" onSubmit={event => { event.preventDefault(); void saveGuide() }}>
          <label className="block text-sm text-text">訪綱名稱
            <input required className={input} maxLength={120} value={guide.title} disabled={guideBusy} onChange={event => setGuide({ ...guide, title: event.target.value })} />
          </label>
          <label className="block text-sm text-text">訪綱內容
            <textarea className={input} rows={6} maxLength={30000} value={guide.body} disabled={guideBusy} onChange={event => setGuide({ ...guide, body: event.target.value })} />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={primary} disabled={guideBusy || !guide.title.trim()}>{guideBusy ? '儲存中…' : '另存訪綱'}</button>
            <button type="button" className={secondary} disabled={guideBusy} onClick={() => setGuide(undefined)}>取消編輯</button>
          </div>
        </form>}
      </section>
    </div>
  )
}

function LegacySessionNote({ id, onCopy }: { id: string; onCopy: (body: string) => void }) {
  const [note, setNote] = useState<InterviewNote>()
  const [error, setError] = useState('')
  const [opened, setOpened] = useState(false)
  const [load, setLoad] = useState(0)
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    void interviewService.note(id, controller.signal).then(next => {
      if (!controller.signal.aborted) setNote(next)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [id, load, opened])

  return (
    <details className="space-y-2 text-sm text-text" onToggle={event => setOpened(event.currentTarget.open)}>
      <summary className="cursor-pointer">查看此場舊筆記</summary>
      {error ? <>
        <p role="alert" className="text-error">{error}</p>
        <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入</button>
      </> : note ? (note.body ? <>
        <p className="whitespace-pre-wrap break-words">{note.body}</p>
        <button type="button" className={secondary} onClick={() => onCopy(note.body)}>附加到情境筆記草稿</button>
      </> : <p className="text-text-muted">此場沒有舊筆記。</p>) : <p role="status">載入中…</p>}
    </details>
  )
}
