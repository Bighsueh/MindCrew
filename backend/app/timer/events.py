"""Timer event types — Spec 15 §5.

WS broadcast：timer:state（每秒前端自算）/ timer:warning / timer:timeout
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TimerStateEvent:
    project_id: UUID
    current_sub_phase: str | None
    budget_seconds: int
    used_seconds: int
    paused: bool
    used_pct: float


@dataclass(frozen=True)
class TimerWarningEvent:
    project_id: UUID
    threshold_pct: int
    current_sub_phase: str
    used_seconds: int
    budget_seconds: int


@dataclass(frozen=True)
class TimerTimeoutEvent:
    """Used by crew advance vote trigger (Stream D)."""

    project_id: UUID
    current_sub_phase: str
