"""Timer event types — Spec 16 §3.2 / §6.5.3。

WS broadcast：timer_state（每 10 秒）/ timer_warning（threshold 跨越）/ timer_timeout（100%）。

每個 event 都實作 ``type`` property + ``to_dict()`` / ``to_json()``，符合
``app.events.bus.event_bus.publish()`` 對 AnyEvent 的 duck-type 要求。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID


def _sub_phase_label(sub_phase_id: str | None) -> str | None:
    """內部 sub_phase 代號 → 學生友善階段名（去掉「講義第N步」等內部註記）。

    lazy import 避免 timer ↔ stages 的 import 順序耦合；查無對應時退回原代號。
    """
    if not sub_phase_id:
        return sub_phase_id
    try:
        from app.stages.labels import student_facing_label
        from app.stages.sub_phases import SUB_PHASES

        sp = SUB_PHASES.get(sub_phase_id)
        return student_facing_label(sp.name_zh) if sp is not None else sub_phase_id
    except Exception:
        return sub_phase_id


@dataclass(frozen=True)
class TimerStateEvent:
    project_id: UUID
    current_sub_phase: str | None
    budget_seconds: int
    used_seconds: int
    paused: bool
    used_pct: float
    # Spec 16 v2.0 §4.5（Phase 42 WP1）：本關上限/已用——與 budget_seconds/used_seconds
    # 同值的明確化別名（既有欄位本來就是 per-sub-phase 口徑，additive、不改舊欄位）。
    sub_phase_budget_seconds: int = 0
    sub_phase_used_seconds: int = 0
    # 暖場（macro stage = warmup）期間 = max(8, round(20 × intensity))；非暖場為 None。
    warmup_goal: int | None = None
    # 暖場軟目標秒數（固定 180／3 分，spec 28 §3.1）；非暖場為 None。前端用以在倒數上
    # 標示「3 分軟目標」、過軟目標後切換副標（spec 05 §5、spec 16 §4.5）。
    warmup_soft_seconds: int | None = None

    @property
    def type(self) -> str:
        return "timer_state"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "current_sub_phase": self.current_sub_phase,
                # 學生友善 label（計時器徽章顯示用）：避免把「1.1b」這種內部代號丟給學生看
                # （盲測 2026-06-08）。內部代號仍保留於 current_sub_phase 供前端邏輯使用。
                "current_sub_phase_label": _sub_phase_label(self.current_sub_phase),
                "budget_seconds": self.budget_seconds,
                "used_seconds": self.used_seconds,
                "paused": self.paused,
                "used_pct": self.used_pct,
                "sub_phase_budget_seconds": self.sub_phase_budget_seconds,
                "sub_phase_used_seconds": self.sub_phase_used_seconds,
                "warmup_goal": self.warmup_goal,
                "warmup_soft_seconds": self.warmup_soft_seconds,
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
