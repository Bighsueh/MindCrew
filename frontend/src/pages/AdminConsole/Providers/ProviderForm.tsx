import { useEffect, useState, type FormEvent } from 'react'
import { Button } from '../../../components/common/Button'
import { Input } from '../../../components/common/Input'
import { Modal } from '../../../components/common/Modal'
import type {
  AdminProvider,
  AdminProviderCreate,
  AdminProviderUpdate,
  CapabilityClass,
  ProviderKind,
} from '../../../services/adminService'

interface ProviderFormProps {
  isOpen: boolean
  onClose: () => void
  initial?: AdminProvider | null
  onSubmit: (payload: AdminProviderCreate | AdminProviderUpdate) => Promise<void>
}

interface FormState {
  name: string
  kind: ProviderKind
  tier: number
  capability_class: CapabilityClass
  weight: number
  base_url: string
  model: string
  api_key: string
  azure_api_version: string
  azure_deployment: string
  enabled: boolean
  max_retries: number
  timeout_seconds: number
}

const EMPTY: FormState = {
  name: '',
  kind: 'vllm',
  tier: 1,
  capability_class: 'standard',
  weight: 1,
  base_url: '',
  model: '',
  api_key: '',
  azure_api_version: '',
  azure_deployment: '',
  enabled: true,
  max_retries: 2,
  timeout_seconds: 30,
}

function fromProvider(p: AdminProvider): FormState {
  return {
    name: p.name,
    kind: p.kind,
    tier: p.tier,
    capability_class: p.capability_class,
    weight: p.weight,
    base_url: p.base_url,
    model: p.model,
    api_key: '', // never round-trip the (masked) secret
    azure_api_version: p.azure_api_version ?? '',
    azure_deployment: p.azure_deployment ?? '',
    enabled: p.enabled,
    max_retries: p.max_retries,
    timeout_seconds: p.timeout_seconds,
  }
}

export function ProviderForm({ isOpen, onClose, initial, onSubmit }: ProviderFormProps) {
  const isEdit = Boolean(initial)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setForm(initial ? fromProvider(initial) : EMPTY)
    setError('')
  }, [isOpen, initial])

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((s) => ({ ...s, [key]: value }))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const payload: AdminProviderCreate | AdminProviderUpdate = {
        name: form.name,
        kind: form.kind,
        tier: form.tier,
        capability_class: form.capability_class,
        weight: form.weight,
        base_url: form.base_url,
        model: form.model,
        enabled: form.enabled,
        max_retries: form.max_retries,
        timeout_seconds: form.timeout_seconds,
        azure_api_version: form.kind === 'azure_openai' ? form.azure_api_version || null : null,
        azure_deployment: form.kind === 'azure_openai' ? form.azure_deployment || null : null,
      }
      if (form.api_key) {
        payload.api_key = form.api_key
      } else if (!isEdit) {
        payload.api_key = ''
      }
      await onSubmit(payload)
      onClose()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg || '儲存失敗')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? '編輯 Provider' : '新增 Provider'}
      maxWidth="2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-md bg-error-bg px-4 py-2 text-sm text-error">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="名稱"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="vllm-east / azure-japan"
            required
            data-testid="provider-name"
          />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-text">類型</label>
            <select
              value={form.kind}
              onChange={(e) => update('kind', e.target.value as ProviderKind)}
              className="rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text"
              data-testid="provider-kind"
            >
              <option value="vllm">vLLM</option>
              <option value="azure_openai">Azure OpenAI</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-text">Tier（1=主層級）</label>
            <select
              value={form.tier}
              onChange={(e) => update('tier', Number(e.target.value))}
              className="rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text"
              data-testid="provider-tier"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  Tier {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-text">品質池（capability_class）</label>
            <select
              value={form.capability_class}
              onChange={(e) => update('capability_class', e.target.value as CapabilityClass)}
              className="rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text"
              data-testid="provider-capability-class"
            >
              <option value="standard">standard（快速預設）</option>
              <option value="quality">quality（高品質）</option>
            </select>
          </div>
          <Input
            label="Weight (預留)"
            type="number"
            min={1}
            max={100}
            value={form.weight}
            onChange={(e) => update('weight', Number(e.target.value) || 1)}
          />
          <Input
            label="Timeout (秒)"
            type="number"
            min={1}
            max={300}
            value={form.timeout_seconds}
            onChange={(e) => update('timeout_seconds', Number(e.target.value) || 30)}
          />
        </div>

        <Input
          label="Base URL"
          value={form.base_url}
          onChange={(e) => update('base_url', e.target.value)}
          placeholder="https://vllm.example.com/v1"
          required
        />

        <Input
          label="Model"
          value={form.model}
          onChange={(e) => update('model', e.target.value)}
          placeholder="/models/gemma-4-26B-A4B-it"
          required
        />

        <Input
          label={
            isEdit
              ? 'API Key（留空 = 維持原值）'
              : 'API Key'
          }
          type="password"
          value={form.api_key}
          onChange={(e) => update('api_key', e.target.value)}
          placeholder={isEdit ? '••••••••' : 'sk-... 或 dummy'}
        />

        {form.kind === 'azure_openai' && (
          <div className="grid grid-cols-2 gap-4 rounded-md border border-border bg-surface-hover p-4">
            <Input
              label="Azure Deployment"
              value={form.azure_deployment}
              onChange={(e) => update('azure_deployment', e.target.value)}
              placeholder="gpt-4o-deployment-name"
            />
            <Input
              label="Azure API Version"
              value={form.azure_api_version}
              onChange={(e) => update('azure_api_version', e.target.value)}
              placeholder="2024-02-15-preview"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Max Retries (per provider)"
            type="number"
            min={0}
            max={5}
            value={form.max_retries}
            onChange={(e) => update('max_retries', Number(e.target.value) || 0)}
          />
          <div className="flex items-end gap-2 pb-1">
            <input
              id="provider-enabled"
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => update('enabled', e.target.checked)}
              className="h-4 w-4"
            />
            <label htmlFor="provider-enabled" className="text-sm text-text">
              啟用（enabled）
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button type="submit" isLoading={submitting} data-testid="provider-submit">
            {isEdit ? '儲存變更' : '建立'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
