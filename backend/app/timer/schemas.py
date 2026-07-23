"""Timer schemas — Spec 15."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class TimerConfig(BaseModel):
    """老師在建專案時設定的 timer 配置。"""

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    # Phase 40 (spec/16 §2.1 v1.2): 預設改 90 分（2hr/4hr preset 已移除）。
    total_session_minutes: int = Field(default=90, ge=30, le=720)
    # Phase 39 (spec/16-timer-system §2.4): 強度縮放係數。讓便條張數門檻 /
    # 整理格靜止秒 / 量爆軟上限隨總時長等比變輕（地板保證每步仍有意義產出）。
    # 預設 1.0 → 舊專案/舊 JSON 零影響（向下相容）。deliverables_required 不縮放。
    intensity: float = Field(default=1.0, ge=0.2, le=1.0)
    # Phase 42 B1 (spec/16 §2.1 v2.0)：暖場固定硬上限 5 分（所有 preset 含 custom 相同），
    # initialize_project 會強制覆寫 warmup/0.0a，不吃呼叫端值。
    macro_budgets: dict[str, int] = Field(
        default_factory=lambda: {
            "warmup": 5, "discover": 51, "define": 34,
        }
    )
    sub_phase_overrides: dict[str, int] = Field(default_factory=dict)
    warning_thresholds_pct: list[int] = Field(default_factory=lambda: [75, 90, 100])
    auto_advance_on_timeout: bool = False
    allow_overrun: bool = True
    preset_id: str = "timer_preset_90min"


class TimerState(BaseModel):
    """Runtime 狀態，存在 project.timer_state JSONB。"""

    model_config = ConfigDict(extra="ignore")

    current_sub_phase: str | None = None
    phase_started_at: str | None = None  # ISO format
    paused_at: str | None = None
    total_paused_seconds: int = 0
    warnings_fired: list[int] = Field(default_factory=list)
    # Phase 42 D5 (G14 / #35, spec 20 §13.3)：區分暫停來源——
    # "teacher"＝老師手動暫停、"llm_down"＝LLM 服務中斷 fail-stop、
    # "awaiting_human"＝人類離席/被點名未應答的全房休眠（Phase 43, spec 20 §3/§11.7）。
    # None＝未暫停。JSONB 欄位、extra="ignore"＝舊資料零 migration（缺欄自動 None）。
    # 優先序：teacher / llm_down 不被 awaiting_human 覆蓋或自動續跑（見 room_hibernation）。
    pause_reason: str | None = None

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
