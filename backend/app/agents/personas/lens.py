"""Cognitive Lens taxonomy.

Each micro-phase declares a ``needed_lens`` (or ``None``). At runtime the
resolver picks the seat whose persona has the highest affinity for that
lens. This decouples Design Thinking phase strategy from the legacy
``crew_1=empathy`` hardcoding while keeping the 4-lens vocabulary stable
for phase strategy authoring.
"""
from __future__ import annotations

from enum import Enum


class CognitiveLens(str, Enum):
    """Four cognitive lenses used by phase strategy."""

    EMPATHY = "empathy"
    STRUCTURE = "structure"
    CREATIVITY = "creativity"
    FEASIBILITY = "feasibility"


LENS_VALUES: tuple[str, ...] = tuple(lens.value for lens in CognitiveLens)


def coerce_lens(value: str | CognitiveLens | None) -> CognitiveLens | None:
    """Coerce a string/enum to ``CognitiveLens`` or return None.

    Returns None for unknown / empty values so callers can branch on it
    without raising.
    """
    if value is None:
        return None
    if isinstance(value, CognitiveLens):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    try:
        return CognitiveLens(normalized)
    except ValueError:
        return None
