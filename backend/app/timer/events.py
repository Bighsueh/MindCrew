"""Timer event types — Spec 16 §3.2 / §6.5.3。

WS broadcast：timer_state（每 10 秒）/ timer_warning（threshold 跨越）/ timer_timeout（100%）。

每個 event 都實作 ``type`` property + ``to_dict()`` / ``to_json()``，符合
``app.events.bus.event_bus.publish()`` 對 AnyEvent 的 duck-type 要求。
"""

from __future__ import annotations

import json
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

    @property
    def type(self) -> str:
        return "timer_state"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "current_sub_phase": self.current_sub_phase,
                "budget_seconds": self.budget_seconds,
                "used_seconds": self.used_seconds,
                "paused": self.paused,
                "used_pct": self.used_pct,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass(frozen=True)
class TimerWarningEvent:
    project_id: UUID
    threshold_pct: int
    current_sub_phase: str
    used_seconds: int
    budget_seconds: int

    @property
    def type(self) -> str:
        return "timer_warning"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "threshold_pct": self.threshold_pct,
                "current_sub_phase": self.current_sub_phase,
                "used_seconds": self.used_seconds,
                "budget_seconds": self.budget_seconds,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass(frozen=True)
class TimerTimeoutEvent:
    """Used by crew advance vote trigger (Stream D)."""

    project_id: UUID
    current_sub_phase: str

    @property
    def type(self) -> str:
        return "timer_timeout"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "current_sub_phase": self.current_sub_phase,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
