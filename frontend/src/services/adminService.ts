/**
 * Phase 25 — typed wrapper around /api/admin/* endpoints.
 */
import api from './api'

export type ProviderKind = 'vllm' | 'azure_openai'
export type CapabilityClass = 'quality' | 'standard'

export interface AdminProvider {
  id: string
  name: string
  kind: ProviderKind
  tier: number
  capability_class: CapabilityClass
  weight: number
  base_url: string
  model: string
  api_key_masked: string
  azure_api_version: string | null
  azure_deployment: string | null
  enabled: boolean
  max_retries: number
  timeout_seconds: number
  created_at: string
  updated_at: string
}

export interface AdminProviderCreate {
  name: string
  kind: ProviderKind
  tier: number
  capability_class?: CapabilityClass
  base_url: string
  model: string
  api_key?: string
  weight?: number
  azure_api_version?: string | null
  azure_deployment?: string | null
  enabled?: boolean
  max_retries?: number
  timeout_seconds?: number
}

export type AdminProviderUpdate = Partial<AdminProviderCreate>

export interface HealthCheckResult {
  ok: boolean
  provider_id: string
  name: string
  latency_ms: number
  error: string | null
}

export interface AdminLogEntry {
  id: number
  created_at: string
  provider_id: string
  provider_name: string | null
  model: string | null
  owning_user_id: string
  owning_user_display_name: string | null
  triggered_by_user_id: string | null
  triggered_by_display_name: string | null
  project_id: string | null
  project_name: string | null
  tier_used: number
  cascade_from_tier: number | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  success: boolean
  error_class: string | null
  error_message: string | null
  caller: string
}

export interface AdminLogMessage {
  role: string
  content: string
  truncated_chars: number | null
}

export interface AdminLogDetail extends AdminLogEntry {
  messages: AdminLogMessage[]
  response_content: string | null
  response_finish_reason: string | null
  messages_bytes: number
}

export interface CallerStatRow {
  caller: string
  request_count: number
  total_tokens: number
}

export interface TopUserStatRow {
  /** Phase 26: this is `COALESCE(triggered_by_user_id, owning_user_id)`, i.e.
   * the human who actually triggered the call (with project-owner fallback
   * for autonomous agent ticks). Field name kept for API back-compat. */
  owning_user_id: string
  display_name: string | null
  role: string | null
  request_count: number
  total_tokens: number
}

export interface HourlyBucket {
  hour: number
  request_count: number
  total_tokens: number
}

export interface LatencyBucket {
  label: string
  upper_ms: number
  request_count: number
}

export interface SuccessRateTrendPoint {
  bucket_ts: string  // ISO 8601 UTC
  request_count: number
  success_count: number
  rate: number | null  // null when bucket has no requests
}

export interface SuccessRateTrend {
  granularity: Granularity
  points: SuccessRateTrendPoint[]
}

export interface OverviewStats {
  days: number
  callers: CallerStatRow[]
  top_users: TopUserStatRow[]
  hourly: HourlyBucket[]
  latency_buckets: LatencyBucket[]
}

export interface AdminLogList {
  total: number
  limit: number
  offset: number
  items: AdminLogEntry[]
}

export type Granularity = '30min' | 'hour' | 'day'

export interface ProviderRef {
  id: string
  name: string
}

export interface TimeseriesPoint {
  bucket_ts: string
  provider_id: string | null
  request_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface TokenTimeseries {
  granularity: Granularity
  providers: ProviderRef[]
  points: TimeseriesPoint[]
}

export async function listProviders(): Promise<AdminProvider[]> {
  const res = await api.get<AdminProvider[]>('/admin/providers')
  return res.data
}

export async function createProvider(
  payload: AdminProviderCreate,
): Promise<AdminProvider> {
  const res = await api.post<AdminProvider>('/admin/providers', payload)
  return res.data
}

export async function updateProvider(
  id: string,
  payload: AdminProviderUpdate,
): Promise<AdminProvider> {
  const res = await api.patch<AdminProvider>(`/admin/providers/${id}`, payload)
  return res.data
}

export async function deleteProvider(id: string): Promise<void> {
  await api.delete(`/admin/providers/${id}`)
}

export async function healthCheckProvider(id: string): Promise<HealthCheckResult> {
  const res = await api.post<HealthCheckResult>(
    `/admin/providers/${id}/health-check`,
  )
  return res.data
}

export interface LogQuery {
  provider_id?: string
  user_id?: string
  project_id?: string
  success?: boolean
  caller?: string
  model?: string
  triggered_by_user_id?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export async function listLogs(query: LogQuery = {}): Promise<AdminLogList> {
  const res = await api.get<AdminLogList>('/admin/logs', { params: query })
  return res.data
}

export async function getLogDetail(id: number): Promise<AdminLogDetail> {
  const res = await api.get<AdminLogDetail>(`/admin/logs/${id}`)
  return res.data
}

export async function fetchOverviewStats(days = 7): Promise<OverviewStats> {
  const res = await api.get<OverviewStats>('/admin/stats/overview', {
    params: { days },
  })
  return res.data
}

export interface TimeseriesQuery {
  since: string  // ISO 8601 UTC
  until: string  // ISO 8601 UTC
  user_id?: string
  provider_ids?: string[]
  granularity?: 'auto' | Granularity
}

export async function fetchTokenTimeseries(
  query: TimeseriesQuery,
): Promise<TokenTimeseries> {
  const res = await api.get<TokenTimeseries>('/admin/stats/timeseries', {
    params: query,
    // Axios default `repeat` style produces `?provider_ids=a&provider_ids=b`
    // which matches FastAPI's `list[UUID]` query binding.
    paramsSerializer: { indexes: null },
  })
  return res.data
}

export interface SuccessRateQuery {
  since: string
  until: string
  granularity?: 'auto' | Granularity
}

export async function fetchSuccessRateTrend(
  query: SuccessRateQuery,
): Promise<SuccessRateTrend> {
  const res = await api.get<SuccessRateTrend>('/admin/stats/success-rate', {
    params: query,
  })
  return res.data
}

export interface LatencyPercentileRow {
  provider_id: string | null
  provider_name: string | null
  request_count: number
  p50_ms: number | null
  p95_ms: number | null
  p99_ms: number | null
  max_ms: number | null
  avg_ms: number | null
}

export interface LatencyTrendPoint {
  bucket_ts: string
  request_count: number
  avg_ms: number | null
  p95_ms: number | null
}

export interface LatencyStats {
  granularity: Granularity
  rows: LatencyPercentileRow[]
  trend: LatencyTrendPoint[]
}

export interface LatencyQuery {
  since: string
  until: string
  provider_ids?: string[]
  granularity?: 'auto' | Granularity
}

export async function fetchLatencyStats(
  query: LatencyQuery,
): Promise<LatencyStats> {
  const res = await api.get<LatencyStats>('/admin/stats/latency', {
    params: query,
    paramsSerializer: { indexes: null },
  })
  return res.data
}

// ── LLM fail-stop health (Phase 42 D5 / G14, spec 20 §13.6) ───────────────

export type LLMOverallStatus = 'up' | 'degraded' | 'down'

export interface ProviderHealthDetail {
  provider_id: string
  provider_name: string
  healthy: boolean
  consecutive_failures: number
  last_failure_at: string | null
  last_failure_reason: string | null
  last_check_at: string | null
  cooldown_remaining_seconds: number | null
}

export interface AffectedRoomEntry {
  project_id: string
  project_name: string | null
  pause_reason: string | null
  paused_at: string | null
}

export interface LLMHealth {
  overall_status: LLMOverallStatus
  reactive_consecutive_failures: number
  reactive_threshold: number
  proactive_unhealthy_streak: number
  proactive_threshold: number
  last_status_change: string | null
  providers: ProviderHealthDetail[]
  affected_rooms: AffectedRoomEntry[]
}

export async function fetchLLMHealth(): Promise<LLMHealth> {
  const res = await api.get<LLMHealth>('/admin/llm-health')
  return res.data
}
