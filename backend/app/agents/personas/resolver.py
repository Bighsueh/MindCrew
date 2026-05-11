"""Resolve cognitive lenses to concrete seat_ids at runtime.

Phase strategy expresses protagonist/suppressed in lens-space (stable).
This module maps that to the actual seats present in the project
(dynamic, per-project personas).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.agents.personas.lens import CognitiveLens, coerce_lens
from app.agents.personas.models import (
    Persona,
    fallback_persona_for,
    persona_from_dict,
)


def _persona_for_seat(seat: Any) -> Persona | None:
    """Extract a Persona from a seat dict-or-ORM, falling back to legacy."""
    if seat is None:
        return None
    if isinstance(seat, dict):
        seat_role = seat.get("seat_role") or seat.get("role") or ""
        payload = seat.get("persona")
    else:
        seat_role = getattr(seat, "seat_role", "") or ""
        payload = getattr(seat, "persona", None)
    persona = persona_from_dict(payload) if payload else None
    if persona is not None:
        return persona
    if seat_role:
        return fallback_persona_for(seat_role)
    return None


def _seat_role_of(seat: Any) -> str:
    if isinstance(seat, dict):
        return str(seat.get("seat_role") or seat.get("role") or "")
    return str(getattr(seat, "seat_role", "") or "")


def _is_ai_seat(seat: Any) -> bool:
    if isinstance(seat, dict):
        occ = seat.get("occupant_type") or seat.get("type") or ""
    else:
        occ = getattr(seat, "occupant_type", "") or getattr(seat, "type", "") or ""
    return str(occ).lower() == "ai"


def _is_crew_seat(seat: Any) -> bool:
    """Crew seats (not supervisor) are eligible to be protagonist."""
    role = _seat_role_of(seat).lower()
    return role.startswith("crew_") or role.startswith("seat_") or role.startswith("crew")


def dominant_lens(seat: Any) -> CognitiveLens | None:
    """Return the dominant cognitive lens of a seat's persona, or None."""
    persona = _persona_for_seat(seat)
    if persona is None:
        return None
    return persona.dominant_lens()


def resolve_protagonist_seat(
    seats: Iterable[Any],
    needed_lens: CognitiveLens | str | None,
) -> str | None:
    """Pick the seat_role whose persona has the highest affinity for ``lens``.

    Rules:
    - Only AI crew seats are considered (not supervisor, not human).
    - Ties break by stable seat_role ordering.
    - Returns ``None`` if no seat qualifies or no lens is provided.
    """
    lens = coerce_lens(needed_lens)
    if lens is None:
        return None
    candidates: list[tuple[float, str]] = []
    for seat in seats:
        if not _is_ai_seat(seat):
            continue
        if not _is_crew_seat(seat):
            continue
        persona = _persona_for_seat(seat)
        if persona is None:
            continue
        score = persona.lens_affinities.get(lens)
        seat_role = _seat_role_of(seat)
        candidates.append((score, seat_role))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_role = candidates[0]
    # Require at least a faint affinity; otherwise nobody truly fits.
    if best_score <= 0.0:
        return None
    return best_role


def resolve_suppressed_seats(
    seats: Iterable[Any],
    suppressed_lenses: Iterable[CognitiveLens | str] | None,
    *,
    protect_seat: str | None = None,
    threshold: float = 0.7,
) -> list[str]:
    """Return seat_roles whose dominant lens is in the suppressed set.

    Args:
        seats: All seats in the project.
        suppressed_lenses: Lenses that should be muted this micro-phase.
        protect_seat: Never suppress this seat_role (typically the protagonist).
        threshold: Minimum affinity to count as "dominantly that lens".
    """
    if not suppressed_lenses:
        return []
    target_lenses = {coerce_lens(l) for l in suppressed_lenses}
    target_lenses.discard(None)
    if not target_lenses:
        return []
    suppressed: list[str] = []
    for seat in seats:
        if not _is_ai_seat(seat) or not _is_crew_seat(seat):
            continue
        seat_role = _seat_role_of(seat)
        if protect_seat and seat_role == protect_seat:
            continue
        persona = _persona_for_seat(seat)
        if persona is None:
            continue
        for lens in target_lenses:
            if persona.lens_affinities.get(lens) >= threshold:
                suppressed.append(seat_role)
                break
    return suppressed
