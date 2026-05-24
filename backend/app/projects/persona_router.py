"""Persona endpoints (Phase 19).

Two responsibilities:
1. ``POST /api/personas/generate`` — stateless LLM persona generation
   used by the project creation wizard (preview before committing).
2. ``PATCH /api/projects/{id}/seats/{seat_role}/persona`` — update the
   persona of an existing AI seat after the project is created.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.personas.generator import (
    PersonaGenerationError,
    PersonaGenerator,
)
from app.agents.personas.models import (
    StakeholderSuggestion,
    persona_to_dict,
)
from app.auth.jwt import get_current_user
from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.user import User
from app.db.session import get_db_session
from app.projects.schemas import (
    PersonaGenerateRequest,
    PersonaGenerateResponse,
    PersonaPayload,
    SeatPersonaUpdateRequest,
    SeatResponse,
    StakeholderSelectionPayload,
)
from app.projects.service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["personas"])


def _convert_stakeholder_selections(
    payloads: list["StakeholderSelectionPayload"] | None,
) -> list[StakeholderSuggestion] | None:
    """Phase 27：把 Pydantic StakeholderSelectionPayload → dataclass。

    Returns ``None`` when caller did not pick any (legacy v1.x path);
    returns a list of dataclasses when caller picked ≥1 (Phase 27 path).
    """
    if not payloads:
        return None
    return [
        StakeholderSuggestion(
            id=item.id or "",
            name=item.name,
            role=item.role,
            relevance=item.relevance or "",
        )
        for item in payloads
    ]


@router.post(
    "/api/personas/generate",
    response_model=PersonaGenerateResponse,
)
async def generate_personas(
    request: PersonaGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> PersonaGenerateResponse:
    """Generate AI personas from project title/description/constraints.

    This is a stateless preview endpoint — nothing is persisted. The
    frontend wizard collects, edits, and finally submits these personas
    with ``POST /api/projects``.
    """
    generator = PersonaGenerator()
    stakeholders_dataclasses = _convert_stakeholder_selections(request.stakeholders)
    try:
        personas = await generator.generate(
            title=request.title,
            description=request.description,
            constraints=request.constraints,
            num_personas=request.num_personas,
            owning_user_id=current_user.id,
            stakeholders=stakeholders_dataclasses,
        )
    except PersonaGenerationError as exc:
        logger.warning("Persona generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 人設生成失敗，請稍後再試或手動建立人設。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    payloads = [
        PersonaPayload(**persona_to_dict(persona)) for persona in personas
    ]
    return PersonaGenerateResponse(personas=payloads)


@router.post("/api/personas/generate/stream")
async def generate_personas_stream(
    request: PersonaGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream persona generation events as SSE (see spec §17.3.1.2).

    The response stays open until either ``done`` or ``error`` is emitted.
    Errors during generation are reported as ``event: error`` frames with
    HTTP status 200 — the client decides whether to fall back to the sync
    endpoint or display the message.
    """
    generator = PersonaGenerator()
    stakeholders_dataclasses = _convert_stakeholder_selections(request.stakeholders)

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for event in generator.generate_stream(
                title=request.title,
                description=request.description,
                constraints=request.constraints,
                num_personas=request.num_personas,
                owning_user_id=current_user.id,
                stakeholders=stakeholders_dataclasses,
            ):
                event_name = str(event.get("type") or "message")
                payload = {k: v for k, v in event.items() if k != "type"}
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {data}\n\n".encode("utf-8")
        except Exception as exc:  # noqa: BLE001 — translate to SSE error frame
            logger.exception("Persona SSE stream crashed")
            data = json.dumps({"detail": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n".encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx/proxy buffering
        },
    )


@router.patch(
    "/api/projects/{project_id}/seats/{seat_role}/persona",
    response_model=SeatResponse,
)
async def update_seat_persona(
    project_id: UUID,
    seat_role: str,
    request: SeatPersonaUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SeatResponse:
    """Update the persona of an existing AI seat."""
    project_result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if project.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator may modify personas",
        )

    if not seat_role.startswith("crew_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only crew seats accept personas",
        )

    seat_result = await session.execute(
        select(Seat).where(
            Seat.project_id == project_id, Seat.seat_role == seat_role
        )
    )
    seat = seat_result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found"
        )
    if seat.occupant_type != "ai":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot assign a persona to a human-occupied seat",
        )

    persona_dict = request.persona.model_dump()
    # Pydantic emits nested LensAffinitiesPayload as dict already.
    if hasattr(request.persona.lens_affinities, "model_dump"):
        persona_dict["lens_affinities"] = request.persona.lens_affinities.model_dump()
    seat.persona = persona_dict
    await session.flush()
    await session.commit()

    # Restart the agent so it picks up the new persona prompt.
    from app.seats.manager import seat_manager
    try:
        await seat_manager.restart_agent(project_id, seat_role)
    except Exception as exc:
        logger.warning(
            "Failed to restart agent %s/%s after persona update: %s",
            project_id, seat_role, exc,
        )

    return ProjectService._seat_to_response(seat)
