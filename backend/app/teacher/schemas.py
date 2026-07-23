"""Pydantic schemas for the Teacher Dashboard endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SeatSummary(BaseModel):
    human: int
    ai: int


class TeacherProjectListItem(BaseModel):
    id: UUID
    name: str
    current_stage: str
    status: str
    seat_summary: SeatSummary
    note_count: int
    last_activity: datetime | None

    model_config = {"from_attributes": True}


class LLMUsageSummary(BaseModel):
    total_tokens: int
    total_calls: int
    total_cost_estimate: float


class StageRecordEntry(BaseModel):
    stage: str
    duration_seconds: int | None
    canvas_snapshot: dict | None
    started_at: datetime


class ProjectRecordResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    current_stage: str
    ai_contribution: str
    status: str
    created_at: datetime
    stages: list[StageRecordEntry]
    total_messages: int
    total_notes: int
    llm_usage: LLMUsageSummary

    model_config = {"from_attributes": True}


class AgentTraceResponse(BaseModel):
    id: UUID
    project_id: UUID
    agent_id: str
    stage: str
    assess_result: str
    assess_rule: str | None
    assess_details: dict | None
    prompt_text: str | None
    llm_response: str | None
    llm_model: str | None
    llm_tokens_in: int | None
    llm_tokens_out: int | None
    llm_latency_ms: int | None
    action_type: str | None
    action_details: dict | None
    action_result: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentTraceListResponse(BaseModel):
    traces: list[AgentTraceResponse]
    next_cursor: str | None
    has_more: bool


# ---------------------------------------------------------------------------
# Teacher Dashboard Monitoring ()
# ---------------------------------------------------------------------------


class EvaluationScoreSummary(BaseModel):
    latest_total: float | None
    threshold: float | None
    consecutive_passes: int
    trend: str  # "improving" | "stagnant" | "declining"


class ParticipationSummary(BaseModel):
    human_messages: int
    ai_messages: int
    active_members: int
    total_members: int


class AIActivitySummary(BaseModel):
    total_interventions: int
    recent_interventions: int
    action_distribution: dict[str, int]


class AlertItem(BaseModel):
    level: str  # "error" | "warning" | "info"
    type: str  # "stage_stagnation" | "low_participation" | "ai_dominant"
    message: str


class ProjectMonitorItem(BaseModel):
    id: UUID
    name: str
    current_stage: str
    status: str
    seat_summary: SeatSummary
    note_count: int
    last_activity: datetime | None
    created_at: datetime
    ai_contribution: str
    stage_duration_seconds: int
    stage_started_at: datetime | None
    evaluation_score: EvaluationScoreSummary
    participation: ParticipationSummary
    ai_activity: AIActivitySummary
    alerts: list[AlertItem]
    # Phase 28：當前 turn-taking 規則，前端 TurnPolicySwitcher 用這個欄位顯示正確初值。
    turn_policy: str = "cued"

    model_config = {"from_attributes": True}


class StageDistribution(BaseModel):
    # Phase 29 (spec/04-06 §4.10): develop / deliver removed.
    # Frontend StageDistributionBar should treat absent keys as 0.
    discover: int = 0
    define: int = 0
    completed: int = 0


class ProjectOverviewResponse(BaseModel):
    projects: list[ProjectMonitorItem]
    stage_distribution: StageDistribution


class SendHintRequest(BaseModel):
    content: str


class SendHintResponse(BaseModel):
    message_id: UUID
    sent_at: datetime
