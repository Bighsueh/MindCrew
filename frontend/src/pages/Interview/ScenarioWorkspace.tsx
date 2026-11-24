import { useEffect, useState } from 'react'
import { cn } from '../../lib/utils'
import {
  interviewError, interviewService, type InterviewSummary, type ScenarioSummary,
} from '../../services/interviewService'
import { Conversation } from './Conversation'
import { ScenarioMaterials } from './ScenarioMaterials'
import { dateFormat, input, panel, primary, secondary } from './styles'

export function ScenarioWorkspace({ scenario, sessions, teacher, draft, onEdit, onSave, onScenario, onSession, onBack }: {
  scenario: ScenarioSummary
  sessions: InterviewSummary[]
  teacher: boolean
  draft?: string
  onEdit: (body: string) => void
  onSave: (body: string) => void
  onScenario: (scenario: ScenarioSummary) => void
  onSession: (session: InterviewSummary) => void
  onBack: () => void
}) {
  const [role, setRole] = useState('')
  const [selectedSession, setSelectedSession] = useState(sessions[0]?.id ?? '')
  const [pane, setPane] = useState<'conversation' | 'materials'>('materials')
  const [generationBusy, setGenerationBusy] = useState(false)
  const [starting, setStarting] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [studentEmails, setStudentEmails] = useState('')
  const [error, setError] = useState('')
  const active = sessions.find(item => item.id === selectedSession)
  const selectedRole = role || scenario.profiles[0]?.id || ''
  const isDraft = teacher && scenario.kind === 'teacher' && scenario.mine && !scenario.published

  useEffect(() => {
    if (!['pending', 'generating'].includes(scenario.generation_state) && !generationBusy) return
    const controller = new AbortController()
    const timer = setInterval(() => {
      void interviewService.scenario(scenario.id, controller.signal).then(next => {
        if (!controller.signal.aborted && next.generation_state !== 'pending') onScenario(next)
      }).catch(() => { /* The action itself reports network errors. */ })
    }, 2000)
    return () => { clearInterval(timer); controller.abort() }
  }, [generationBusy, onScenario, scenario.generation_state, scenario.id])

  async function generate() {
    if (generationBusy) return
    setError('')
    setGenerationBusy(true)
    try {
      onScenario(await interviewService.generateProfiles(scenario.id))
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setGenerationBusy(false)
    }
  }

  async function start() {
    if (!selectedRole || starting) return
    setError('')
    setStarting(true)
    try {
      const session = await interviewService.start(selectedRole, scenario.id)
      onSession(session)
      setSelectedSession(session.id)
      setPane('conversation')
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setStarting(false)
    }
  }

  async function publish() {
    const recipients = studentEmails.split(/[\s,，;；]+/).filter(Boolean)
    if (!recipients.length || publishing || !window.confirm(`確認將此情境發佈給填寫的 ${recipients.length} 個學生帳號？`)) return
    setError('')
    setPublishing(true)
    try {
      onScenario(await interviewService.publishScenario(scenario.id, recipients))
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setPublishing(false)
    }
  }

  return (
    <div className="space-y-4">
      <button type="button" className={secondary} onClick={onBack}>返回情境選擇</button>
      <header className={`${panel} space-y-2 p-4`}>
        <h2 className="break-words text-xl font-semibold text-text">{scenario.title}</h2>
        <p className="whitespace-pre-wrap break-words text-sm text-text-muted">{scenario.description}</p>
      </header>
      {error && <p role="alert" className="text-sm text-error">{error}</p>}
      <div className="grid items-start gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className={`${panel} space-y-4 p-4`}>
          <fieldset className="space-y-2" disabled={starting}>
            <legend className="font-semibold text-text">{isDraft ? '受訪者預覽' : '選擇受訪者'}</legend>
            {scenario.profiles.map(profile => (
              <label key={profile.id} className={cn('flex items-start gap-2 rounded-lg border p-2 text-sm', profile.id === selectedRole ? 'border-primary' : 'border-border')}>
                <input type="radio" name="scenario-profile" className="mt-1 accent-primary" checked={profile.id === selectedRole} onChange={() => setRole(profile.id)} />
                <span className="min-w-0 break-words text-text"><strong className="block">{profile.name}</strong>{profile.description}</span>
              </label>
            ))}
          </fieldset>
          {scenario.generation_state !== 'ready' && (
            generationBusy || scenario.generation_state === 'generating'
              ? <p role="status" className="text-sm text-text-muted">正在生成合成受訪者。你可以先寫筆記。</p>
              : <div className="space-y-2">
                {scenario.generation_error && <p role="alert" className="text-sm text-error">{scenario.generation_error}</p>}
                {scenario.mine && <button type="button" className={secondary} onClick={() => void generate()}>{scenario.generation_state === 'pending' ? '生成受訪者' : '重試生成受訪者'}</button>}
              </div>
          )}
          {scenario.generation_state === 'ready' && !isDraft && <button type="button" className={primary} disabled={starting || !selectedRole} onClick={() => void start()}>
            {starting ? '建立中…' : '開始新訪談'}
          </button>}
          {isDraft && scenario.generation_state === 'ready' && (
            <form className="space-y-2" onSubmit={event => { event.preventDefault(); void publish() }}>
              <label className="block text-sm text-text">指定學生帳號 Email（每行一個）
                <textarea rows={3} className={input} value={studentEmails} disabled={publishing} onChange={event => setStudentEmails(event.target.value)} />
              </label>
              <button type="submit" className={primary} disabled={publishing || !studentEmails.trim()}>{publishing ? '發佈中…' : '確認發佈'}</button>
            </form>
          )}
          <label className="block space-y-1 text-sm text-text">
            <span>本情境的訪談紀錄</span>
            <select className={input} value={selectedSession} disabled={!sessions.length || starting} onChange={event => {
              setSelectedSession(event.target.value)
              setPane('conversation')
            }}>
              {!selectedSession && <option value="">{sessions.length ? '選擇場次' : '尚無訪談'}</option>}
              {sessions.map(item => <option key={item.id} value={item.id}>
                {item.stakeholder.name} · {dateFormat.format(new Date(item.started_at))}{item.ended_at ? ' · 已結束' : ''}
              </option>)}
            </select>
          </label>
        </aside>
        <div className="min-w-0 space-y-3">
          {active && (
            <div className="flex gap-2 lg:hidden">
              <button type="button" className={pane === 'conversation' ? primary : secondary} aria-pressed={pane === 'conversation'} onClick={() => setPane('conversation')}>對話</button>
              <button type="button" className={pane === 'materials' ? primary : secondary} aria-pressed={pane === 'materials'} onClick={() => setPane('materials')}>筆記與訪綱</button>
            </div>
          )}
          <div className={cn('grid items-start gap-4', active && 'lg:grid-cols-[minmax(0,1fr)_minmax(14rem,0.7fr)]')}>
            {active && <div className={cn('min-w-0', pane !== 'conversation' && 'hidden lg:block')}>
              <Conversation key={active.id} id={active.id} role={active.stakeholder} limit={600} onEnded={onSession} />
            </div>}
            <div className={cn('min-w-0', active && pane !== 'materials' && 'hidden lg:block')}>
              <ScenarioMaterials id={scenario.id} sessionId={active?.id} draft={draft} onEdit={onEdit} onSave={onSave} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
