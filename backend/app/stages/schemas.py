"""Pydantic schemas for the DT Flow / stage endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StageResponse(BaseModel):
    project_id: UUID
    current_stage: str
    current_micro_phase: str | None = None
    ai_contribution: str
    started_at: datetime | None = None
    duration_seconds: int | None = None

    model_config = {"from_attributes": True}


class AdvanceStageRequest(BaseModel):
    from_stage: str = Field(alias="from")
    to_stage: str = Field(alias="to")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class AdvanceStageResponse(BaseModel):
    current_stage: str
    previous_snapshot_id: UUID | None = None

    model_config = {"from_attributes": True}


class StageHistoryResponse(BaseModel):
    id: UUID
    project_id: UUID
    from_stage: str
    to_stage: str
    triggered_by: str
    canvas_snapshot: dict | None = None
    duration_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdvanceMicroPhaseRequest(BaseModel):
    from_phase: str
    to_phase: str
    reason: str | None = None


class AdvanceMicroPhaseResponse(BaseModel):
    current_micro_phase: str
    is_backtrack: bool

    model_config = {"from_attributes": True}


class MicroPhaseHistoryResponse(BaseModel):
    id: UUID
    project_id: UUID
    from_micro_phase: str
    to_micro_phase: str
    transition_type: str
    triggered_by: str
    reason: str | None = None
    duration_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
