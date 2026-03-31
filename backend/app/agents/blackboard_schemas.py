"""Pydantic schemas for the Blackboard coordination layer.

See docs/blackboard-design.md §3 for data format specifications.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class AgentIntention(BaseModel):
    """A single agent's reasoning summary and declared intent (§3.1)."""

    agent_id: str
    seat_role: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reasoning_summary: str
    next_intent: str
    focus_topic: str | None = None
    viewpoint: str | None = None
    confidence: float = 0.5
    stage: str = "discover"
    inactive: bool = False


class TopicEntry(BaseModel):
    """A single topic within the saturation report (§3.2)."""

    name: str
    note_count: int = 0
    contributors: list[str] = Field(default_factory=list)
    viewpoint_diversity: Literal["low", "medium", "high"] = "low"
    existing_angles: list[str] = Field(default_factory=list)
    missing_angles: list[str] = Field(default_factory=list)
    saturation: Literal["low", "medium", "high"] = "low"


class TopicSaturation(BaseModel):
    """Global topic saturation state, written by Supervisor (§3.2)."""

    stage: str
    topics: list[TopicEntry] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Coordination(BaseModel):
    """Current round coordination state (§3.3)."""

    round: int = 0
    claimed_topics: dict[str, str] = Field(default_factory=dict)
    recently_covered: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CoordinationDirective(BaseModel):
    """Supervisor's directive written to Blackboard for Crew coordination.

    This is the Supervisor's 'command channel' — Crew agents MUST check
    this before deciding what to do.  (論文 §3.1.2, §4.2.3)

    Note: PhaseStrategy 定義「遊戲規則」（溝通策略、目標、模式），
    CoordinationDirective 是「遊戲中的即時指令」（點名發言、聚焦話題）。
    兩者互補，非替代關係。
    """

    round_type: Literal[
        "open_diverge", "focused_discuss", "respond_to", "summarize", "vote"
    ] = "open_diverge"
    focus_topic: str | None = None
    invited_speaker: str | None = None
    instruction: str = ""
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: float = 60.0
