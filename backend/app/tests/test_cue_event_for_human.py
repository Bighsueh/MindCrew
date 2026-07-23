"""B6: 驗證 _emit_cue_event 對人類 invited_speaker 也發送（非 AI-only）。

既有 code 路徑（B2/B4 整合後）已支援人類 cue event 廣播，本檔做 regression
保險 — 確保未來改動不會誤加 AI-only filter。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.act import ActEngine
from app.events.types import CueEvent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_emit_cue_event_publishes_for_human_seat() -> None:
    """invited_speaker 為人類席位時，CueEvent 仍正確發送。"""
    engine = ActEngine(
        project_id=uuid4(),
        agent_id="agent_supervisor",
        seat_role="supervisor",
        agent_name="AI 引導者",
        is_supervisor=True,
    )
    published: list[CueEvent] = []

    async def _record(event: CueEvent) -> None:
        published.append(event)

    with patch(
        "app.agents.act.event_bus.publish",
        new=AsyncMock(side_effect=_record),
    ):
        await engine._emit_cue_event(invited_speaker="crew_3")  # human seat

    assert len(published) == 1
    assert published[0].target_seat_role == "crew_3"
    assert published[0].from_seat_role == "supervisor"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_emit_cue_event_publishes_for_ai_seat() -> None:
    """既有 AI 路徑保持不變（regression）。"""
    engine = ActEngine(
        project_id=uuid4(),
        agent_id="agent_supervisor",
        seat_role="supervisor",
        agent_name="AI 引導者",
        is_supervisor=True,
    )
    published: list[CueEvent] = []

    with patch(
        "app.agents.act.event_bus.publish",
        new=AsyncMock(side_effect=lambda e: published.append(e)),
    ):
        await engine._emit_cue_event(invited_speaker="crew_1")  # AI seat

    assert len(published) == 1
    assert published[0].target_seat_role == "crew_1"
