import { useEffect, useState } from 'react'
import { Loading } from '../../../components/common/Loading'
import { Modal } from '../../../components/common/Modal'
import {
  getLogDetail,
  type AdminLogDetail,
  type AdminLogMessage,
} from '../../../services/adminService'

interface Props {
  logId: number | null
  onClose: () => void
}

/**
 * Phase 25.J detail modal. Opening this modal causes the backend to write
 * an ``admin_payload_access`` audit row — every PII exposure is traceable.
 *
 * Layout: metadata block on top, full messages middle (system/user/assistant
 * colour-coded), assembled response at the bottom.
 */
export function LogDetailModal({ logId, onClose }: Props) {
  const [detail, setDetail] = useState<AdminLogDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (logId === null) {
      setDetail(null)
      setError('')
      return
    }
    setLoading(true)
    setError('')
    setDetail(null)
    getLogDetail(logId)
      .then(setDetail)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [logId])

  return (
    <Modal isOpen={logId !== null} onClose={onClose} title={`LLM Request #${logId ?? ''}`} maxWidth="4xl">
      {loading && <Loading text="載入請求內容…" />}
      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error" data-testid="log-error">
          {error}
        </div>
      )}
      {detail && (
        <div className="space-y-5">
          <MetadataBlock detail={detail} />
          <MessagesBlock messages={detail.messages} bytes={detail.messages_bytes} />
          <ResponseBlock detail={detail} />
        </div>
      )}
    </Modal>
  )
}

function MetadataBlock({ detail }: { detail: AdminLogDetail }) {
  const rows: Array<[string, string]> = [
    ['時間', new Date(detail.created_at).toLocaleString()],
    ['Caller', detail.caller],
    ['Provider', `${detail.provider_name ?? '—'} (T${detail.tier_used}${detail.cascade_from_tier ? ` ← T${detail.cascade_from_tier}` : ''})`],
    ['Owning user', `${detail.owning_user_display_name ?? '—'} (${detail.owning_user_id.slice(0, 8)})`],
    ['Triggered by', detail.triggered_by_display_name ?? '—'],
    ['Project', detail.project_name ?? '（無 project context）'],
    ['Tokens', `prompt=${detail.prompt_tokens} · completion=${detail.completion_tokens} · total=${detail.total_tokens}`],
    ['Latency', `${detail.latency_ms} ms`],
    ['Result', detail.success ? '✅ success' : `❌ ${detail.error_class ?? 'failure'}`],
  ]
  return (
    <section
      className="rounded-md border border-border bg-surface-hover p-3"
      data-testid="log-metadata"
    >
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline gap-2">
            <span className="w-24 text-xs text-text-muted">{k}</span>
            <span className="flex-1 truncate text-text" title={v}>
              {v}
            </span>
          </div>
        ))}
      </div>
      {detail.error_message && (
        <div className="mt-2 rounded-sm bg-error-bg px-2 py-1 font-mono text-xs text-error">
          {detail.error_message}
        </div>
      )}
    </section>
  )
}

const ROLE_STYLES: Record<string, { label: string; cls: string }> = {
  system: { label: 'system', cls: 'border-border bg-surface-hover' },
  user: { label: 'user', cls: 'border-info/40 bg-info-bg' },
  assistant: { label: 'assistant', cls: 'border-success/40 bg-success-bg' },
}

function MessagesBlock({
  messages,
  bytes,
}: {
  messages: AdminLogMessage[]
  bytes: number
}) {
  return (
    <section data-testid="log-messages">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-text">Request messages</h3>
        <span className="font-mono text-xs text-text-muted">{bytes.toLocaleString()} bytes</span>
      </header>
      {messages.length === 0 ? (
        <p className="text-sm text-text-muted">（無 messages 紀錄）</p>
      ) : (
        <div className="space-y-2">
          {messages.map((m, i) => {
            const style = ROLE_STYLES[m.role] ?? {
              label: m.role,
              cls: 'border-border bg-surface',
            }
            return (
              <div key={i} className={`rounded-md border ${style.cls} px-3 py-2`}>
                <div className="mb-1 flex items-baseline justify-between text-xs">
                  <span className="font-medium text-text">{style.label}</span>
                  {m.truncated_chars && (
                    <span className="text-warning">[truncated {m.truncated_chars} chars]</span>
                  )}
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-text">
                  {m.content}
                </pre>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function ResponseBlock({ detail }: { detail: AdminLogDetail }) {
  return (
    <section data-testid="log-response">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-text">LLM response</h3>
        {detail.response_finish_reason && (
          <span className="font-mono text-xs text-text-muted">
            finish: {detail.response_finish_reason}
          </span>
        )}
      </header>
      {detail.response_content ? (
        <pre className="max-h-96 overflow-auto rounded-md border border-border bg-surface-hover p-3 font-mono text-xs text-text">
          {detail.response_content}
        </pre>
      ) : (
        <p className="text-sm text-text-muted">（無 response 內容；失敗或 streaming 未完成）</p>
      )}
    </section>
  )
}
