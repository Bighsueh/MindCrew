import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { interviewError, interviewService, type InterviewNote } from '../../services/interviewService'
import { dateFormat, input, panel, primary, secondary } from './styles'

export function NotePreview({ body }: { body: string }) {
  return <ReactMarkdown skipHtml disallowedElements={['img', 'a']} unwrapDisallowed>{body}</ReactMarkdown>
}

export function InterviewNotes({ id, draft, onEdit, onSave }: {
  id: string
  draft?: string
  onEdit: (value: string) => void
  onSave: (value: string) => void
}) {
  const [saved, setSaved] = useState<InterviewNote>()
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const value = draft ?? saved?.body ?? ''

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.note(id, controller.signal).then(note => {
      if (!controller.signal.aborted) setSaved(note)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [id, reload])

  async function save() {
    setSaving(true)
    setError('')
    try {
      const result = await interviewService.saveNote(id, value)
      setSaved(result)
      onSave(value)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${panel} space-y-3 p-4`}>
      <h2 className="text-lg font-semibold text-text">我的筆記</h2>
      {error && <p role="alert" className="text-sm text-error">{error}</p>}
      {!saved ? (error
        ? <button type="button" className={secondary} onClick={() => { setError(''); setReload(value => value + 1) }}>重新載入筆記</button>
        : <p role="status" className="text-sm text-text-muted">載入筆記中…</p>
      ) : <>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={secondary} aria-pressed={!preview} onClick={() => setPreview(false)}>編輯</button>
          <button type="button" className={secondary} aria-pressed={preview} onClick={() => setPreview(true)}>預覽</button>
        </div>
        {preview ? (
          <div className="min-h-36 space-y-2 whitespace-pre-wrap break-words rounded-lg border border-border bg-bg p-3 text-sm text-text [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5 [&_h1]:font-bold [&_h2]:font-semibold">
            {value ? <NotePreview body={value} /> : <p>尚無筆記。</p>}
          </div>
        ) : (
          <textarea aria-label="訪談筆記" className={input} rows={9} maxLength={30000} value={value}
            placeholder="記下你的觀察，可使用 Markdown。"
            onChange={event => onEdit(event.target.value)} />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={primary} disabled={saving || value === saved.body} onClick={() => void save()}>
            {saving ? '儲存中…' : error ? '重試儲存' : '儲存筆記'}
          </button>
          <span role="status" className="text-xs text-text-muted">
            {value !== saved.body ? '有未儲存變更' : saved.updated_at ? `已儲存 · ${dateFormat.format(new Date(saved.updated_at))}` : ''}
          </span>
        </div>
      </>}
    </section>
  )
}
