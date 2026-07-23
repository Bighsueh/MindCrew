"""Pydantic schemas for the admin console (Phase 25 + extension).

Splits incoming (create / update) and outgoing (response) shapes so that the
``api_key`` field can be masked in responses without ever shipping the plain
secret to the browser after the initial admin entry.

Phase 25.J extension: log responses now carry owning / triggered user names
and project name (denormalized at query time). A separate ``LogDetailResponse``
includes the full message payload and triggers an audit row on access.

Phase 25.K extension: ``OverviewStatsResponse`` bundles five aggregates so
the Stats page only needs one HTTP call.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


ProviderKind = Literal["vllm", "azure_openai"]
CapabilityClass = Literal["quality", "standard"]  # Phase 37: quality pool axis


# ── provider CRUD (unchanged from Phase 25 core) ────────────────────────


class ProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: ProviderKind
    tier: int = Field(ge=1, le=5)
    capability_class: CapabilityClass = "standard"
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1, max_length=128)
    api_key: str = Field(default="", max_length=2048)
    weight: int = Field(default=1, ge=1, le=100)
    azure_api_version: str | None = Field(default=None, max_length=32)
    azure_deployment: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("name")
    @classmethod
    def _name_trim(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class ProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    tier: int | None = Field(default=None, ge=1, le=5)
    capability_class: CapabilityClass | None = None
    base_url: str | None = None
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=2048)
    weight: int | None = Field(default=None, ge=1, le=100)
    azure_api_version: str | None = Field(default=None, max_length=32)
    azure_deployment: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    max_retries: int | None = Field(default=None, ge=0, le=5)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)


class ProviderResponse(BaseModel):
    id: UUID
    name: str
    kind: ProviderKind
    tier: int
    capability_class: CapabilityClass
    weight: int
    base_url: str
    model: str
    api_key_masked: str
    azure_api_version: str | None
    azure_deployment: str | None
    enabled: bool
    max_retries: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": False}


class HealthCheckResponse(BaseModel):
    ok: bool
    provider_id: UUID
    name: str
    latency_ms: int
    error: str | None = None


# ── LLM fail-stop health (Phase 42 D5 / G14, spec 20 §13.6) ──────────────


class ProviderHealthDetail(BaseModel):
    """單一 provider 的健康快照（背景健檢迴圈維護）。"""

    provider_id: str
    provider_name: str
    healthy: bool
    consecutive_failures: int
    last_failure_at: str | None = None
    last_failure_reason: str | None = None
    last_check_at: str | None = None
    cooldown_remaining_seconds: float | None = None


class AffectedRoomEntry(BaseModel):
    """因 LLM fail-stop 被暫停的房間（暫停時間軸）。"""

    project_id: UUID
    project_name: str | None
    pause_reason: str | None
    paused_at: str | None


class LLMHealthResponse(BaseModel):
    """整體 LLM 健康判定 + per-provider 詳情 + 受影響房（spec 20 §13.6）。"""

    overall_status: Literal["up", "degraded", "down"]
    reactive_consecutive_failures: int
    reactive_threshold: int
    proactive_unhealthy_streak: int
    proactive_threshold: int
    last_status_change: str | None
    providers: list[ProviderHealthDetail]
    affected_rooms: list[AffectedRoomEntry]


# ── log list + detail (Phase 25.J) ──────────────────────────────────────


class LogEntryResponse(BaseModel):
    id: int
    created_at: datetime
    provider_id: UUID
    provider_name: str | None
    model: str | None = None
    owning_user_id: UUID
    owning_user_display_name: str | None
    triggered_by_user_id: UUID | None
    triggered_by_display_name: str | None
    project_id: UUID | None
    project_name: str | None
    tier_used: int
    cascade_from_tier: int | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    success: bool
    error_class: str | None
    error_message: str | None
    caller: str


class LogListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LogEntryResponse]


class LogMessage(BaseModel):
    role: str
    content: str
    truncated_chars: int | None = None


class LogDetailResponse(LogEntryResponse):
    messages: list[LogMessage]
    response_content: str | None
    response_finish_reason: str | None
    messages_bytes: int


# ── audit ──────────────────────────────────────────────────────────────


class PayloadAccessEntry(BaseModel):
    id: int
    created_at: datetime
    admin_user_id: UUID
    admin_display_name: str | None
    request_log_id: int


class PayloadAccessListResponse(BaseModel):
    total: int
    items: list[PayloadAccessEntry]


# ── stats: overview (Phase 25.K) ───────────────────────────────────────


class CallerStatRow(BaseModel):
    caller: str
    request_count: int
    total_tokens: int


class TopUserStatRow(BaseModel):
    owning_user_id: UUID
    display_name: str | None
    role: str | None
    request_count: int
    total_tokens: int


class HourlyBucket(BaseModel):
    hour: int  # 0..23 (UTC)
    request_count: int
    total_tokens: int


class LatencyBucket(BaseModel):
    label: str  # e.g. "<500ms"
    upper_ms: int  # inclusive upper bound; 0 means open-ended
    request_count: int


class OverviewStatsResponse(BaseModel):
    days: int
    callers: list[CallerStatRow]
    top_users: list[TopUserStatRow]
    hourly: list[HourlyBucket]
    latency_buckets: list[LatencyBucket]


# ── timeseries (Phase 25.L + Phase 26 provider 拆分 / 30min 粒度) ───────


Granularity = Literal["30min", "hour", "day"]


class ProviderRef(BaseModel):
    """Minimal provider identifier for chart legends."""

    id: UUID
    name: str


class TimeseriesPoint(BaseModel):
    """One (bucket_ts, provider) row on the token-usage line chart.

    Phase 26: rows are now ``bucket_ts × provider_id`` so the frontend can
    pivot into stacked series. ``provider_id`` is NULL only when the chart
    is requested without per-provider grouping (legacy aggregate mode).
    """

    bucket_ts: datetime  # bucket start, UTC
    provider_id: UUID | None
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TimeseriesResponse(BaseModel):
    granularity: Granularity
    providers: list[ProviderRef]
    points: list[TimeseriesPoint]


class SuccessRateTrendPoint(BaseModel):
    bucket_ts: datetime  # bucket start, UTC
    request_count: int
    success_count: int
    rate: float | None  # null when request_count == 0


class SuccessRateTrendResponse(BaseModel):
    granularity: Granularity
    points: list[SuccessRateTrendPoint]


# ── latency analytics (percentiles + trend) ────────────────────────────


class LatencyPercentileRow(BaseModel):
    """Per-provider latency summary. ``provider_id`` is None for the overall
    aggregate row across all providers."""

    provider_id: UUID | None
    provider_name: str | None
    request_count: int
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: int | None
    avg_ms: float | None


class LatencyTrendPoint(BaseModel):
    bucket_ts: datetime  # bucket start, UTC
    request_count: int
    avg_ms: float | None  # null when request_count == 0
    p95_ms: float | None  # null when request_count == 0


class LatencyStatsResponse(BaseModel):
    granularity: Granularity
    rows: list[LatencyPercentileRow]  # overall first, then per provider
    trend: list[LatencyTrendPoint]


def mask_api_key(api_key: str) -> str:
    """Show only the last 4 chars, prefixed with the leading 'sk-' if present."""
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "***"
    last4 = api_key[-4:]
    if api_key.lower().startswith("sk-"):
        return f"sk-***{last4}"
    return f"***{last4}"
