from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Persona schemas (Phase 19)
# ---------------------------------------------------------------------------


class LensAffinitiesPayload(BaseModel):
    empathy: float = 0.5
    structure: float = 0.5
    creativity: float = 0.5
    feasibility: float = 0.5

    @field_validator("empathy", "structure", "creativity", "feasibility")
    @classmethod
    def _clamp(cls, value: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5


class PersonaPayload(BaseModel):
    """Per-project AI persona snapshot.

    Mirrors :class:`app.agents.personas.models.Persona` for transport.
    """

    name: str = Field(..., min_length=1, max_length=64)
    role: str = Field(..., min_length=1, max_length=128)
    expertise: str = Field("", max_length=256)
    personality_axis: str = Field("balanced")
    personality_desc: str = Field("", max_length=256)
    backstory: str = Field("", max_length=256)
    lens_affinities: LensAffinitiesPayload = Field(
        default_factory=LensAffinitiesPayload
    )

    @field_validator("personality_axis")
    @classmethod
    def _validate_axis(cls, value: str) -> str:
        allowed = {"contrarian", "balanced", "supportive"}
        cleaned = (value or "").strip().lower()
        return cleaned if cleaned in allowed else "balanced"


class CrewPersonaAssignment(BaseModel):
    """Mapping of one crew seat_role to a Persona for project creation."""

    seat_role: str = Field(..., pattern=r"^crew_[1-4]$")
    persona: PersonaPayload


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    constraints: str | None = None
    ai_contribution: str = "medium"
    personas: list[CrewPersonaAssignment] | None = None


class SeatResponse(BaseModel):
    seat_role: str
    occupant_type: str
    user_id: UUID | None = None
    agent_id: str | None = None
    display_name: str | None = None
    persona: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    constraints: str | None = None
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
    constraints: str | None = None
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


# ---------------------------------------------------------------------------
# Persona API schemas (Phase 19)
# ---------------------------------------------------------------------------


class PersonaGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    constraints: str | None = Field(default=None, max_length=2048)
    num_personas: int = Field(default=4, ge=1, le=8)


class PersonaGenerateResponse(BaseModel):
    personas: list[PersonaPayload]


class SeatPersonaUpdateRequest(BaseModel):
    persona: PersonaPayload
