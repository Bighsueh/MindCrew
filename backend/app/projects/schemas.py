from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    ai_contribution: str = "medium"


class SeatResponse(BaseModel):
    seat_role: str
    occupant_type: str
    user_id: UUID | None = None
    agent_id: str | None = None
    display_name: str | None = None

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    current_stage: str
    ai_contribution: str
    status: str
    creator_id: UUID
    seats: list[SeatResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    current_stage: str
    status: str
    creator_id: UUID
    seat_summary: dict[str, int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    ai_contribution: str | None = None


class JoinRequest(BaseModel):
    seat_role: str


class JoinResponse(BaseModel):
    seat: SeatResponse
    workspace_url: str


class CanvasNoteResponse(BaseModel):
    id: str
    content: str
    color: str
    author: str = ""
    group_name: str | None = None


class CanvasGroupResponse(BaseModel):
    name: str
    notes: list[str]


class CanvasStateResponse(BaseModel):
    total_notes: int
    groups: list[CanvasGroupResponse]
    ungrouped: list[str]
    notes: list[CanvasNoteResponse]


class ProjectSummaryResponse(BaseModel):
    summary: str
    topics: list[str]
    current_focus: str
    blind_spots: list[str]
    generated_at: datetime
