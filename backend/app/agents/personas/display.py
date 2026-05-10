"""Display-name resolution for AI seats.

Single source of truth for converting (seat_role, persona) → user-visible
name. All UI/chat/prompt code paths should call ``resolve_display_name``
instead of looking up a static mapping.
"""
from __future__ import annotations

from typing import Any


LEGACY_DISPLAY_NAMES: dict[str, str] = {
    "supervisor": "AI 引導者",
    "crew_1": "AI 同理心專家",
    "crew_2": "AI 結構化專家",
    "crew_3": "AI 創意專家",
    "crew_4": "AI 可行性專家",
}


def resolve_display_name(
    seat_role: str | None,
    persona: Any | None = None,
) -> str:
    """Return the AI seat's user-visible name.

    Resolution order:
    1. ``persona["name"]`` when persona is present and has a non-empty name
    2. Legacy capability label keyed by seat_role
    3. ``"AI <seat_role>"`` as last resort
    """
    if isinstance(persona, dict):
        candidate = str(persona.get("name", "")).strip()
        if candidate:
            return candidate
    if not seat_role:
        return "AI"
    legacy = LEGACY_DISPLAY_NAMES.get(seat_role)
    if legacy:
        return legacy
    return f"AI {seat_role}"


__all__ = ["resolve_display_name", "LEGACY_DISPLAY_NAMES"]
