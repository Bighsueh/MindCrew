import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Pencil, Trash2, Activity, Power, PowerOff } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { Loading } from '../../../components/common/Loading'
import {
  createProvider,
  deleteProvider,
  healthCheckProvider,
  listProviders,
  updateProvider,
  type AdminProvider,
  type AdminProviderCreate,
  type AdminProviderUpdate,
  type HealthCheckResult,
} from '../../../services/adminService'
import { AdminNav } from '../AdminNav'
import { ProviderForm } from './ProviderForm'

const TIER_LABELS: Record<number, string> = {
  1: 'Tier 1 — 主層級（round-robin）',
  2: 'Tier 2 — 第一備援',
  3: 'Tier 3 — 第二備援',
  4: 'Tier 4 — 第三備援',
  5: 'Tier 5 — 最終備援',
}

export function AdminProvidersPage() {
  const [providers, setProviders] = useState<AdminProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AdminProvider | null>(null)
  const [healthFor, setHealthFor] = useState<Record<string, HealthCheckResult | 'pending'>>({})

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await listProviders()
      setProviders(rows)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh().catch(() => {/* refresh already records its own error */})
  }, [refresh])

  const grouped = useMemo(() => {
    const out = new Map<number, AdminProvider[]>()
    providers.forEach((p) => {
      const arr = out.get(p.tier) ?? []
      arr.push(p)
      out.set(p.tier, arr)
    })
    return out
  }, [providers])

  const onCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }

  const onEdit = (p: AdminProvider) => {
    setEditing(p)
    setFormOpen(true)
  }

  const submit = async (payload: AdminProviderCreate | AdminProviderUpdate) => {
    if (editing) {
      await updateProvider(editing.id, payload as AdminProviderUpdate)
    } else {
      await createProvider(payload as AdminProviderCreate)
    }
    await refresh()
  }

  const toggleEnabled = async (p: AdminProvider) => {
    await updateProvider(p.id, { enabled: !p.enabled })
    await refresh()
  }

  const onDelete = async (p: AdminProvider) => {
    if (!confirm(`確定要刪除 ${p.name}？`)) return
    await deleteProvider(p.id)
    await refresh()
  }

  const onHealth = async (p: AdminProvider) => {
    setHealthFor((s) => ({ ...s, [p.id]: 'pending' }))
    try {
      const res = await healthCheckProvider(p.id)
      setHealthFor((s) => ({ ...s, [p.id]: res }))
    } catch (e: unknown) {
      setHealthFor((s) => ({
        ...s,
        [p.id]: {
          ok: false,
          provider_id: p.id,
          name: p.name,
          latency_ms: 0,
          error: e instanceof Error ? e.message : String(e),
        },
      }))
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text">LLM Providers</h1>
          <p className="text-sm text-text-muted">
            主層級 round-robin；該 tier 全部失敗才 cascade 至下一層
          </p>
        </div>
        <Button onClick={onCreate} data-testid="add-provider">
          <Plus className="mr-1 h-4 w-4" /> 新增 Provider
        </Button>
      </header>

      <AdminNav />

      {error && (
        <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">{error}</div>
      )}

      {loading ? (
        <Loading text="載入 Providers…" />
      ) : (
        <div className="space-y-6">
          {[1, 2, 3, 4, 5].map((tier) => {
            const rows = grouped.get(tier) ?? []
            if (rows.length === 0 && tier > 1) return null
            return (
              <section key={tier} className="rounded-lg border border-border bg-surface p-4" data-testid={`tier-${tier}`}>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                  {TIER_LABELS[tier]}
                </h2>
                {rows.length === 0 ? (
                  <p className="mt-3 text-sm text-text-muted">（尚無 provider）</p>
                ) : (
                  <table className="mt-3 w-full text-sm">
                    <thead className="text-left text-text-muted">
                      <tr>
                        <th className="py-2">名稱 / Kind</th>
                        <th>Base URL</th>
                        <th>Model</th>
                        <th>API Key</th>
                        <th>狀態</th>
                        <th className="text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((p) => {
                        const h = healthFor[p.id]
                        return (
                          <tr key={p.id} className="border-t border-border" data-testid={`row-${p.name}`}>
                            <td className="py-2 pr-3">
                              <div className="font-medium text-text">{p.name}</div>
                              <div className="text-xs text-text-muted">{p.kind}</div>
                            </td>
                            <td className="pr-3 font-mono text-xs">{p.base_url}</td>
                            <td className="pr-3 font-mono text-xs">{p.model}</td>
                            <td className="pr-3 font-mono text-xs">{p.api_key_masked || '—'}</td>
                            <td className="pr-3">
                              <span
                                className={
                                  p.enabled
                                    ? 'rounded-full bg-success-bg px-2 py-0.5 text-xs text-success'
                                    : 'rounded-full bg-surface-hover px-2 py-0.5 text-xs text-text-muted'
                                }
                              >
                                {p.enabled ? 'enabled' : 'disabled'}
                              </span>
                              {h && h !== 'pending' && (
                                <div className="mt-1 text-xs">
                                  {h.ok ? (
                                    <span className="text-success">healthy · {h.latency_ms}ms</span>
                                  ) : (
                                    <span className="text-error">unhealthy: {h.error ?? 'fail'}</span>
                                  )}
                                </div>
                              )}
                              {h === 'pending' && <div className="mt-1 text-xs text-text-muted">測試中…</div>}
                            </td>
                            <td className="py-2 text-right">
                              <div className="inline-flex items-center gap-1">
                                <Button variant="ghost" size="sm" onClick={() => onHealth(p)} title="健康測試">
                                  <Activity className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => toggleEnabled(p)}
                                  title={p.enabled ? '停用' : '啟用'}
                                >
                                  {p.enabled ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => onEdit(p)} title="編輯">
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => onDelete(p)}
                                  title="刪除"
                                  data-testid={`delete-${p.name}`}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </section>
            )
          })}
        </div>
      )}

      <ProviderForm
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        initial={editing}
        onSubmit={submit}
      />
    </div>
  )
}
