import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Copy, Download, RotateCw, Send } from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  interviewError, interviewRequestId, interviewService,
  type Interview, type InterviewSummary, type Stakeholder,
} from '../../services/interviewService'
import { input, panel, primary, secondary } from './styles'

const timeFormat = new Intl.DateTimeFormat('zh-TW', { timeStyle: 'short' })

export function Conversation({ id, role, limit, onEnded }: {
  id: string
  role: Stakeholder
  limit: number
  onEnded: (session: InterviewSummary) => void
}) {
  const [session, setSession] = useState<Interview>()
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [closing, setClosing] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [copyText, setCopyText] = useState('')
  const [reload, setReload] = useState(0)
  const request = useRef<{ id: string; question: string }>()
  const log = useRef<HTMLDivElement>(null)
  const last = session?.exchanges[session.exchanges.length - 1]
  const waiting = last?.status === 'waiting'
  const ended = Boolean(session?.ended_at)
  const shouldPoll = !ended && (busy || waiting)
  const retryAfter = last?.retry_after_seconds ?? 0

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      try {
        const next = await interviewService.get(id, controller.signal)
        if (controller.signal.aborted) return
        setSession(current => current?.ended_at && !next.ended_at ? current : next)
        if (next.exchanges.some(item => item.request_id === request.current?.id)) {
          request.current = undefined
          setDraft('')
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(interviewError(err))
      } finally {
        if (shouldPoll && !controller.signal.aborted) timer = setTimeout(() => void load(), 1500)
      }
    }
    void load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [id, reload, shouldPoll])

  useEffect(() => {
    if (ended || !retryAfter) return
    const timer = setTimeout(() => setReload(value => value + 1), Math.min(retryAfter, 60) * 1000)
    return () => clearTimeout(timer)
  }, [ended, reload, retryAfter])

  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [last?.sequence, last?.status])

  async function send(event?: FormEvent) {
    event?.preventDefault()
    if (!draft.trim() || busy || closing || waiting || ended || last?.status === 'failed' || !session?.remaining_questions) return
    setBusy(true)
    setError('')
    try {
      const pending = request.current?.question === draft
        ? request.current
        : { id: interviewRequestId(), question: draft }
      request.current = pending
      await interviewService.ask(id, pending.question, pending.id)
      request.current = undefined
      setDraft('')
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setBusy(false)
      setReload(value => value + 1)
    }
  }

  async function resolve(sequence: number, action: 'retry' | 'skip') {
    setBusy(true)
    setError('')
    try {
      await interviewService.resolve(id, sequence, action)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setBusy(false)
      setReload(value => value + 1)
    }
  }

  async function finish() {
    if (!window.confirm('結束這場訪談？結束後仍可回看和匯出紀錄。')) return
    setClosing(true)
    setError('')
    try {
      const ended = await interviewService.end(id)
      setSession(ended)
      onEnded(ended)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setClosing(false)
    }
  }

  async function exportTranscript(mode: 'copy' | 'download') {
    setExporting(true)
    setError('')
    setNotice('')
    setCopyText('')
    try {
      const text = await interviewService.transcript(id)
      if (mode === 'copy') {
        try {
          await navigator.clipboard.writeText(text)
          setNotice('逐字稿已複製。')
        } catch {
          setCopyText(text)
        }
        return
      }
      const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `interview-${id}.txt`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setExporting(false)
    }
  }

  const blocked = !session || ended || busy || closing || waiting || last?.status === 'failed' || !session.remaining_questions

  return (
    <section className={cn(panel, 'min-w-0 overflow-hidden')}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
        <div>
          <h2 className="text-xl font-semibold text-text">{role.name}{session && ` · ${session.scenario.title}`}</h2>
          {session && <p className="text-sm text-text-muted">{session.scenario.description}</p>}
          {session && <p className="text-sm text-text-muted">
            {ended ? '已結束 · 可回看及匯出' : `進行中 · 剩餘 ${session.remaining_questions} 題`}
          </p>}
        </div>
        <button type="button" className={secondary} aria-label="更新訪談紀錄" onClick={() => {
          setError('')
          setReload(value => value + 1)
        }}>
          <RotateCw size={16} aria-hidden="true" />
        </button>
      </header>
      <div ref={log} role="log" aria-label="訪談逐字稿" className="min-h-56 max-h-[55vh] space-y-5 overflow-y-auto px-4 py-5 sm:px-5">
        {!session && !error && <p className="text-sm text-text-muted">載入對話中…</p>}
        {session?.exchanges.length === 0 && <p className="text-text-muted">
          {ended ? '這場訪談沒有對話。' : '輸入你的第一個問題。'}
        </p>}
        {session?.exchanges.map(item => (
          <div key={item.id} className="space-y-3">
            <div className="ml-auto w-fit max-w-[90%] rounded-xl bg-primary/10 px-4 py-2">
              <p className="mb-1 text-xs text-text-muted">你 · {timeFormat.format(new Date(item.asked_at))}</p>
              <p className="whitespace-pre-wrap break-words text-text">{item.question}</p>
            </div>
            {item.answer !== null ? (
              <div className="w-fit max-w-[90%] rounded-xl border border-border bg-bg px-4 py-2">
                <p className="mb-1 text-xs text-text-muted">{role.name}{item.answered_at && ` · ${timeFormat.format(new Date(item.answered_at))}`}</p>
                <p className="whitespace-pre-wrap break-words text-text">{item.answer}</p>
              </div>
            ) : (
              <div className="space-y-2 text-sm text-text-muted">
                <p>{item.status === 'waiting' ? '等候受訪者回答…' : item.status === 'skipped' ? '未取得回答' : item.error}</p>
                {!ended && item.status === 'failed' && (
                  <div className="flex flex-wrap gap-2">
                    {item.retryable && <button type="button" className={secondary} disabled={busy || closing || Boolean(item.retry_after_seconds)} onClick={() => void resolve(item.sequence, 'retry')}>
                      {item.retry_after_seconds ? `約 ${item.retry_after_seconds} 秒後可重試` : '重試回答'}
                    </button>}
                    <button type="button" className={secondary} disabled={busy || closing} onClick={() => void resolve(item.sequence, 'skip')}>略過問題</button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="space-y-3 border-t border-border p-4">
        {error && <p role="alert" className="text-sm text-error">{error}</p>}
        {session && !ended && (
          <form className="flex flex-wrap items-end gap-2" onSubmit={event => void send(event)}>
            <label className="min-w-[12rem] flex-1 space-y-1 text-sm font-medium text-text">
              <span>訪談問題</span>
              <textarea
                className={input} rows={2} maxLength={limit * 2} value={draft} disabled={blocked}
                placeholder="Enter 送出，Shift + Enter 換行"
                onChange={event => { if ([...event.target.value].length <= limit) setDraft(event.target.value) }}
                onKeyDown={event => {
                  if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
                  event.preventDefault()
                  void send()
                }}
              />
            </label>
            <button type="submit" className={primary} disabled={blocked || !draft.trim()}>
              <Send size={16} aria-hidden="true" />{busy ? '處理中…' : '送出'}
            </button>
          </form>
        )}
        {session && <div className="flex flex-wrap gap-2">
          {!ended && <button type="button" className={secondary} disabled={closing} onClick={() => void finish()}>結束訪談</button>}
          <button type="button" className={secondary} disabled={exporting} onClick={() => void exportTranscript('copy')}><Copy size={16} aria-hidden="true" />複製逐字稿</button>
          <button type="button" className={secondary} disabled={exporting} onClick={() => void exportTranscript('download')}><Download size={16} aria-hidden="true" />下載 TXT</button>
        </div>}
        {notice && <p role="status" className="text-sm text-text-muted">{notice}</p>}
        {copyText && <label className="block text-sm text-text">請從下方選取並複製逐字稿<textarea className={input} rows={5} value={copyText} readOnly onFocus={event => event.target.select()} /></label>}
      </div>
    </section>
  )
}
