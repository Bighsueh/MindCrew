"""Timer schemas — Spec 15."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class TimerConfig(BaseModel):
    """老師在建專案時設定的 timer 配置。"""

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    total_session_minutes: int = Field(default=120, ge=30, le=720)
    macro_budgets: dict[str, int] = Field(
        default_factory=lambda: {
            "discover": 45, "define": 30, "develop": 25, "deliver": 20,
        }
    )
    sub_phase_overrides: dict[str, int] = Field(default_factory=dict)
    warning_thresholds_pct: list[int] = Field(default_factory=lambda: [75, 90, 100])
    auto_advance_on_timeout: bool = False
    allow_overrun: bool = True
    preset_id: str = "timer_preset_2hr"


class TimerState(BaseModel):
    """Runtime 狀態，存在 project.timer_state JSONB。"""

    model_config = ConfigDict(extra="ignore")

    current_sub_phase: str | None = None
    phase_started_at: str | None = None  # ISO format
    paused_at: str | None = None
    total_paused_seconds: int = 0
    warnings_fired: list[int] = Field(default_factory=list)

    def is_paused(self) -> bool:
        return self.paused_at is not None

    def parse_started_at(self) -> datetime | None:
        if not self.phase_started_at:
            return None
        try:
            return datetime.fromisoformat(self.phase_started_at)
        except ValueError:
            return None

    def parse_paused_at(self) -> datetime | None:
        if not self.paused_at:
            return None
        try:
            return datetime.fromisoformat(self.paused_at)
        except ValueError:
            return None


class TimerStateUpdate(BaseModel):
    """WS broadcast 用。"""

    project_id: str
    current_sub_phase: str | None
    budget_seconds: int
    used_seconds: int
    paused: bool
    used_pct: float
    warning_thresholds_pct: list[int]


class TimerWarningPayload(BaseModel):
    project_id: str
    threshold_pct: int
    current_sub_phase: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
