import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useAuthStore } from '../../stores/authStore'
import {
  interviewError, interviewRequestId, interviewService,
  type InterviewSummary, type ScenarioSummary,
} from '../../services/interviewService'
import { Conversation } from './Conversation'
import { InterviewNotes } from './InterviewNotes'
import { PersonaWorkspace } from './PersonaWorkspace'
import { ScenarioWorkspace } from './ScenarioWorkspace'
import { dateFormat, input, panel, primary, secondary } from './styles'

export function InterviewPage() {
  const teacher = useAuthStore(state => state.user?.role === 'teacher')
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>()
  const [sessions, setSessions] = useState<InterviewSummary[]>([])
  const [active, setActive] = useState('')
  const [legacy, setLegacy] = useState('')
  const [persona, setPersona] = useState(false)
  const [openedPersona, setOpenedPersona] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [load, setLoad] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([interviewService.scenarios(controller.signal), interviewService.sessions(controller.signal)])
      .then(([next, history]) => {
        if (!controller.signal.aborted) {
          setScenarios(next)
          setSessions(history)
        }
      }).catch(err => {
        if (!controller.signal.aborted) setError(interviewError(err))
      })
    return () => controller.abort()
  }, [load])

  const updateScenario = useCallback((next: ScenarioSummary) => {
    setScenarios(current => current?.some(item => item.id === next.id)
      ? current.map(item => item.id === next.id ? next : item)
      : [next, ...(current ?? [])])
  }, [])

  function updateSession(next: InterviewSummary) {
    setSessions(current => current.some(item => item.id === next.id)
      ? current.map(item => item.id === next.id ? next : item)
      : [next, ...current])
  }

  function draftProps(key: string) {
    return {
      draft: drafts[key],
      onEdit: (body: string) => setDrafts(current => ({ ...current, [key]: body })),
      onSave: (body: string) => setDrafts(current => {
        if (current[key] !== body) return current
        const next = { ...current }
        delete next[key]
        return next
      }),
    }
  }

  const scenario = scenarios?.find(item => item.id === active)
  const historical = sessions.filter(session => !session.scenario_id || !scenarios?.some(item => item.id === session.scenario_id))
  const old = historical.find(item => item.id === legacy)

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold text-text">模擬訪談</h1>
        <p className="text-sm text-text-muted">人物與情境均為合成資料。請勿輸入個人資料。</p>
      </header>
      <nav aria-label="模擬訪談工作區" className="flex gap-2">
        <button type="button" aria-pressed={!persona} className={!persona ? primary : secondary} onClick={() => setPersona(false)}>訪談</button>
        <button type="button" aria-pressed={persona} className={persona ? primary : secondary}
          onClick={() => { setPersona(true); setOpenedPersona(true) }}>Persona</button>
      </nav>
      {openedPersona && <div hidden={!persona}><PersonaWorkspace sessions={sessions} /></div>}
      <div hidden={persona} className="space-y-4">
        {!scenarios ? (error
          ? <div><p role="alert" className="text-error">{error}</p>
            <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入</button></div>
          : <p role="status" className="text-text-muted">載入情境中…</p>)
          : scenario ? (
            <ScenarioWorkspace key={scenario.id} scenario={scenario} teacher={teacher}
              sessions={sessions.filter(item => item.scenario_id === scenario.id)}
              onScenario={updateScenario} onSession={updateSession}
              onBack={() => setActive('')} {...draftProps(`scenario:${scenario.id}`)} />
          ) : old ? (
            <>
              <button type="button" className={secondary} onClick={() => setLegacy('')}>返回情境選擇</button>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(15rem,0.65fr)]">
                <Conversation key={old.id} id={old.id} role={old.stakeholder} limit={600} onEnded={updateSession} />
                <InterviewNotes key={old.id} id={old.id} {...draftProps(`legacy:${old.id}`)} />
              </div>
            </>
          ) : (
            <>
              <ScenarioPicker scenarios={scenarios} teacher={teacher} onOpen={setActive} onCreate={next => {
                updateScenario(next)
                setActive(next.id)
              }} />
              {historical.length > 0 && (
                <section className={`${panel} space-y-2 p-4`}>
                  <h2 className="font-semibold text-text">其他歷史訪談</h2>
                  {historical.map(session => (
                    <button type="button" key={session.id} className={secondary} onClick={() => setLegacy(session.id)}>
                      {session.scenario.title} · {session.stakeholder.name} · {dateFormat.format(new Date(session.started_at))}
                    </button>
                  ))}
                </section>
              )}
            </>
          )}
      </div>
    </div>
  )
}

function ScenarioPicker({ scenarios, teacher, onOpen, onCreate }: {
  scenarios: ScenarioSummary[]
  teacher: boolean
  onOpen: (id: string) => void
  onCreate: (scenario: ScenarioSummary) => void
}) {
  const [kind, setKind] = useState<'custom' | 'teacher'>('custom')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [fileData, setFileData] = useState<{ title: string; description: string; profiles?: unknown }>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<{ signature: string; id: string }>()

  async function readFile(file?: File) {
    setError('')
    setFileData(undefined)
    if (!file) return
    setBusy(true)
    try {
      if (file.size > 250000) throw new Error()
      const parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()))
      if (!parsed || typeof parsed.title !== 'string' || typeof parsed.description !== 'string'
        || !parsed.title.trim() || !parsed.description.trim() || parsed.title.trim().length > 120
        || parsed.description.trim().length > 2400 || (parsed.profiles != null && !Array.isArray(parsed.profiles))) throw new Error()
      setFileData({ title: parsed.title, description: parsed.description, profiles: parsed.profiles })
    } catch {
      setError('請選擇 UTF-8 JSON 檔，並填寫 title 和 description。profiles 應為角色陣列。')
    } finally {
      setBusy(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const body = kind === 'teacher' ? fileData : { title, description }
    if (busy || !body?.title.trim() || !body.description.trim()) return
    setBusy(true)
    setError('')
    try {
      const signature = JSON.stringify([kind, body])
      if (request.current?.signature !== signature) request.current = { signature, id: interviewRequestId() }
      onCreate(await interviewService.createScenario({ ...body, request_id: request.current.id }, kind === 'teacher'))
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <section className={`${panel} space-y-3 p-4`}>
        <h2 className="text-lg font-semibold text-text">選擇既有情境</h2>
        {scenarios.length === 0 && <p className="text-sm text-text-muted">尚無可用情境。</p>}
        {scenarios.map(item => (
          <article className="space-y-2 rounded-lg border border-border p-3" key={item.id}>
            <h3 className="font-semibold text-text">{item.title}</h3>
            <p className="whitespace-pre-wrap break-words text-sm text-text-muted">{item.description}</p>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={secondary} onClick={() => onOpen(item.id)}>開啟情境</button>
              <span className="text-xs text-text-muted">
                {item.kind === 'preset' ? '預設示例' : item.kind === 'teacher' ? (item.published ? '教師已發佈' : '教師匯入草稿') : '自訂情境'}
              </span>
            </div>
          </article>
        ))}
      </section>
      <form className={`${panel} space-y-3 p-4`} onSubmit={event => void submit(event)}>
        <h2 className="text-lg font-semibold text-text">{kind === 'teacher' ? '匯入情境' : '建立自訂情境'}</h2>
        {teacher && <div className="flex gap-2">
          <button type="button" className={secondary} disabled={busy} aria-pressed={kind === 'custom'} onClick={() => { setKind('custom'); setError('') }}>自訂</button>
          <button type="button" className={secondary} disabled={busy} aria-pressed={kind === 'teacher'} onClick={() => { setKind('teacher'); setError('') }}>教師匯入</button>
        </div>}
        {kind === 'teacher' ? (
          <>
            <label className="block text-sm text-text">選擇 UTF-8 JSON 檔
              <input type="file" accept=".json,application/json" className={input} disabled={busy} onChange={event => void readFile(event.target.files?.[0])} />
            </label>
            {fileData && <div className="space-y-1 break-words rounded-lg border border-border p-3 text-sm text-text">
              <strong>{fileData.title}</strong><p>{fileData.description}</p>
            </div>}
          </>
        ) : (
          <>
            <label className="block text-sm text-text">題目名稱
              <input required className={input} maxLength={120} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} />
            </label>
            <label className="block text-sm text-text">情境描述
              <textarea required className={input} maxLength={2400} rows={5} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} />
            </label>
          </>
        )}
        {error && <p role="alert" className="text-sm text-error">{error}</p>}
        <button type="submit" className={primary} disabled={busy || (kind === 'teacher' ? !fileData : !title.trim() || !description.trim())}>
          {busy ? '處理中…' : kind === 'teacher' ? '匯入並預覽' : '儲存並生成受訪者'}
        </button>
      </form>
    </div>
  )
}
