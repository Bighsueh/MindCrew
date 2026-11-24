import { useEffect, useState } from 'react'
import { cn } from '../../lib/utils'
import {
  interviewError, interviewRequestId, interviewService,
  type Interview, type InterviewSummary, type PersonaCatalog,
  type PersonaDraft, type PersonaField, type SourceRef,
} from '../../services/interviewService'
import { dateFormat, input, panel, primary, secondary } from './styles'

const types = { short: '短文字', long: '長文字', list: '清單' } as const
const sourceKey = (ref: SourceRef) => `${ref.session_id}:${ref.sequence}:${ref.speaker}`

function sessionLabel(session: InterviewSummary) {
  return `${session.scenario.title} · ${session.stakeholder.name} · ${dateFormat.format(new Date(session.started_at))}`
}

export function PersonaWorkspace({ sessions }: { sessions: InterviewSummary[] }) {
  const [catalog, setCatalog] = useState<PersonaCatalog>()
  const [draft, setDraft] = useState<PersonaDraft>()
  const [personaId, setPersonaId] = useState('')
  const [pending, setPending] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [load, setLoad] = useState(0)
  const [label, setLabel] = useState('')
  const [type, setType] = useState<PersonaField['type']>('short')
  const [sourceSession, setSourceSession] = useState('')
  const [selectedRef, setSelectedRef] = useState<string>()
  const [targetField, setTargetField] = useState('sources')

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.personas(controller.signal).then(next => {
      if (!controller.signal.aborted) setCatalog(next)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [load])

  function edit(next: PersonaDraft) {
    setDraft(next)
    setDirty(true)
    setNotice('')
  }

  function updateField(id: string, patch: Partial<PersonaField>) {
    if (!draft) return
    edit({ ...draft, fields: draft.fields.map(field => field.field_id === id ? { ...field, ...patch } : field) })
  }

  async function open(id: string) {
    if (!catalog || pending) return
    if (dirty && !window.confirm('這份 Persona 有未儲存變更。確定要切換嗎？')) return
    setError('')
    setNotice('')
    if (!id) {
      setDraft({ title: '', fields: catalog.groups.flatMap(group => group.fields) })
      setPersonaId('')
      setTargetField('sources')
      setDirty(false)
      return
    }
    setPending(true)
    try {
      const next = await interviewService.persona(id)
      setDraft(next)
      setPersonaId(next.id)
      setTargetField(next.fields.some(field => field.field_id === 'sources') ? 'sources' : next.fields[0]?.field_id ?? '')
      setDirty(false)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setPending(false)
    }
  }

  async function save() {
    if (!draft?.title.trim() || pending) return
    setPending(true)
    setError('')
    try {
      const next = await interviewService.savePersona({ title: draft.title, fields: draft.fields }, personaId || undefined)
      setPersonaId(next.id)
      setDraft(next)
      setDirty(false)
      setNotice('Persona 已儲存。')
      setCatalog(current => current && {
        ...current, personas: [next, ...current.personas.filter(item => item.id !== next.id)],
      })
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setPending(false)
    }
  }

  const defaults = new Set(catalog?.groups.flatMap(group => group.fields.map(field => field.field_id)))
  const custom = draft?.fields.filter(field => !defaults.has(field.field_id)) ?? []
  const target = draft?.fields.find(field => field.field_id === targetField)

  function addField() {
    if (!draft || !label.trim() || draft.fields.length >= 64) return
    const field: PersonaField = {
      field_id: interviewRequestId(), label: label.trim(), type, value: type === 'list' ? [] : '', source_refs: [],
    }
    edit({ ...draft, fields: [...draft.fields, field] })
    setLabel('')
  }

  function move(fieldId: string, offset: number) {
    if (!draft) return
    const index = custom.findIndex(field => field.field_id === fieldId)
    const neighbor = custom[index + offset]
    if (!neighbor) return
    const moved = draft.fields.slice()
    const from = moved.findIndex(field => field.field_id === fieldId)
    const to = moved.findIndex(field => field.field_id === neighbor.field_id)
    moved[from] = neighbor
    moved[to] = custom[index]
    edit({ ...draft, fields: moved })
  }

  function remove(field: PersonaField) {
    if (!draft) return
    const filled = Array.isArray(field.value) ? field.value.some(value => value.trim()) : Boolean(field.value.trim())
    if ((filled || field.source_refs.length) && !window.confirm(`移除「${field.label}」及其內容和引用？`)) return
    edit({ ...draft, fields: draft.fields.filter(item => item.field_id !== field.field_id) })
    if (targetField === field.field_id) setTargetField('sources')
  }

  function renderField(field: PersonaField, index?: number) {
    const isCustom = index !== undefined
    const text = Array.isArray(field.value) ? field.value.join('\n') : field.value
    return (
      <div key={field.field_id} className="min-w-0 space-y-2 rounded-lg border border-border p-3">
        {isCustom && (
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-40 flex-1 text-sm text-text">自訂欄位名稱
              <input className={input} required maxLength={120} value={field.label} onChange={event => updateField(field.field_id, { label: event.target.value })} />
            </label>
            <button type="button" className={secondary} disabled={index === 0} aria-label={`上移 ${field.label}`} onClick={() => move(field.field_id, -1)}>上移</button>
            <button type="button" className={secondary} disabled={index === custom.length - 1} aria-label={`下移 ${field.label}`} onClick={() => move(field.field_id, 1)}>下移</button>
            <button type="button" className={secondary} aria-label={`移除 ${field.label}`} onClick={() => remove(field)}>移除</button>
          </div>
        )}
        <label className="block space-y-1 text-sm text-text">
          <span>{isCustom ? '欄位內容' : field.label}{field.type === 'list' && '（每行一項）'}</span>
          {field.type === 'short'
            ? <input className={input} maxLength={280} value={text} onChange={event => updateField(field.field_id, { value: event.target.value })} />
            : <textarea rows={3} className={input} maxLength={12000} value={text}
                onChange={event => updateField(field.field_id, { value: field.type === 'list' ? event.target.value.split('\n', 101) : event.target.value })} />}
        </label>
        {field.source_refs.length > 0 && <ul className="space-y-2">
          {field.source_refs.map(ref => {
            const session = sessions.find(item => item.id === ref.session_id)
            const key = sourceKey(ref)
            return <li key={key} className="flex flex-wrap items-center gap-2 text-sm">
              <button type="button" className={secondary} onClick={() => {
                setSourceSession(ref.session_id)
                setSelectedRef(key)
                setTargetField(field.field_id)
                document.getElementById('persona-interview-source')?.scrollIntoView({ block: 'nearest' })
              }}>{session?.scenario.title ?? '訪談'} · 第 {ref.sequence} 題 · {ref.speaker === 'student' ? '提問' : '回答'}</button>
              <button type="button" className={secondary} aria-label={`移除第 ${ref.sequence} 題的引用`} onClick={() => updateField(field.field_id, {
                source_refs: field.source_refs.filter(item => sourceKey(item) !== key),
              })}>移除引用</button>
            </li>
          })}
        </ul>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <section className={cn(panel, 'space-y-3 p-4')}>
        <h2 className="text-xl font-semibold text-text">我的 Persona</h2>
        {error && !draft && <p role="alert" className="text-sm text-error">{error}</p>}
        {catalog ? (
          <div className="flex flex-wrap items-end gap-3">
            <button type="button" className={primary} disabled={pending} onClick={() => void open('')}>建立空白 Persona</button>
            <label className="min-w-48 text-sm text-text">開啟已儲存 Persona
              <select className={input} value={personaId} disabled={pending || !catalog.personas.length} onChange={event => void open(event.target.value)}>
                {!personaId && <option value="" disabled>選擇 Persona</option>}
                {catalog.personas.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
              </select>
            </label>
          </div>
        ) : error
          ? <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入</button>
          : <p role="status" className="text-sm text-text-muted">載入 Persona 清單中…</p>}
      </section>

      {draft && (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
          <form className={cn(panel, 'min-w-0 p-4')} onSubmit={event => { event.preventDefault(); void save() }}>
            <fieldset className="space-y-5" disabled={pending}>
              <label className="block text-sm font-semibold text-text">Persona 名稱
                <input className={input} required value={draft.title} maxLength={120} onChange={event => edit({ ...draft, title: event.target.value })} />
              </label>
              {catalog?.groups.map(group => (
                <section key={group.id} className="space-y-2">
                  <h3 className="font-semibold text-text">{group.label}</h3>
                  {group.fields.map(({ field_id }) => {
                    const field = draft.fields.find(item => item.field_id === field_id)
                    return field && renderField(field)
                  })}
                </section>
              ))}
              <section className="space-y-2">
                <h3 className="font-semibold text-text">自訂欄位</h3>
                {custom.map(renderField)}
                <div className="flex flex-wrap items-end gap-2">
                  <label className="min-w-40 flex-1 text-sm text-text">新欄位名稱
                    <input className={input} value={label} maxLength={120} onChange={event => setLabel(event.target.value)} />
                  </label>
                  <label className="text-sm text-text">型別
                    <select className={input} value={type} onChange={event => setType(event.target.value as PersonaField['type'])}>
                      {Object.entries(types).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                    </select>
                  </label>
                  <button type="button" className={secondary} disabled={!label.trim() || draft.fields.length >= 64} onClick={addField}>新增欄位</button>
                </div>
              </section>
              <div className="flex flex-wrap items-center gap-2">
                <button type="submit" className={primary} disabled={!draft.title.trim()}>{pending ? '處理中…' : '儲存 Persona'}</button>
                <span role="status" className="text-sm text-text-muted">{dirty ? '有未儲存變更' : notice}</span>
              </div>
            </fieldset>
            {error && <p role="alert" className="mt-2 text-sm text-error">{error}</p>}
          </form>
          <section id="persona-interview-source" className={cn(panel, 'min-w-0 space-y-3 p-4 lg:sticky lg:top-24')}>
            <h3 className="font-semibold text-text">參考訪談原文</h3>
            <label className="block text-sm text-text">訪談場次
              <select className={input} value={sourceSession} disabled={!sessions.length} onChange={event => { setSourceSession(event.target.value); setSelectedRef(undefined) }}>
                <option value="">{sessions.length ? '選擇自己的訪談' : '尚無訪談場次'}</option>
                {sessions.map(session => <option key={session.id} value={session.id}>{sessionLabel(session)}</option>)}
              </select>
            </label>
            {sourceSession && <>
              <label className="block text-sm text-text">引用到欄位
                <select className={input} value={targetField} disabled={pending} onChange={event => setTargetField(event.target.value)}>
                  {draft.fields.map(field => <option key={field.field_id} value={field.field_id}>{field.label}</option>)}
                </select>
              </label>
              <SourceTranscript key={sourceSession} id={sourceSession} selectedRef={selectedRef} target={target}
                disabled={pending}
                onAttach={ref => {
                  if (target && !target.source_refs.some(item => sourceKey(item) === sourceKey(ref))) {
                    updateField(target.field_id, { source_refs: [...target.source_refs, ref] })
                  }
                }}
              />
            </>}
          </section>
        </div>
      )}
    </div>
  )
}

function SourceTranscript({ id, selectedRef, target, disabled, onAttach }: {
  id: string
  selectedRef?: string
  target?: PersonaField
  disabled: boolean
  onAttach: (ref: SourceRef) => void
}) {
  const [session, setSession] = useState<Interview>()
  const [error, setError] = useState('')
  const [load, setLoad] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.get(id, controller.signal).then(next => {
      if (!controller.signal.aborted) setSession(next)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [id, load])

  useEffect(() => {
    if (selectedRef && session) document.getElementById(`persona-source-${selectedRef}`)?.scrollIntoView({ block: 'nearest' })
  }, [selectedRef, session])

  function message(sequence: number, speaker: SourceRef['speaker'], text: string) {
    const ref = { session_id: id, sequence, speaker }
    const key = sourceKey(ref)
    const attached = target?.source_refs.some(item => sourceKey(item) === key)
    return (
      <div id={`persona-source-${key}`} className={cn('space-y-2 rounded-lg border p-2', selectedRef === key ? 'border-primary bg-primary/10' : 'border-border')}>
        <p className="text-xs font-medium text-text-muted">第 {sequence} 題 · {speaker === 'student' ? '訪談者' : session?.stakeholder.name}</p>
        <p className="whitespace-pre-wrap break-words text-sm text-text">{text}</p>
        <button type="button" className={secondary} disabled={disabled || !target || attached || target.source_refs.length >= 80} onClick={() => onAttach(ref)}>
          {attached ? '已引用' : '引用這則訊息'}
        </button>
      </div>
    )
  }

  if (error) return <div className="space-y-2"><p role="alert" className="text-sm text-error">{error}</p>
    <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入原文</button>
  </div>
  if (!session) return <p role="status" className="text-sm text-text-muted">載入原文中…</p>
  return (
    <div className="max-h-[55vh] space-y-3 overflow-auto">
      {!session.exchanges.length && <p className="text-sm text-text-muted">這場訪談尚無訊息。</p>}
      {session.exchanges.map(exchange => (
        <div key={exchange.id} className="space-y-2">
          {message(exchange.sequence, 'student', exchange.question)}
          {exchange.answer !== null && message(exchange.sequence, 'stakeholder', exchange.answer)}
        </div>
      ))}
    </div>
  )
}
