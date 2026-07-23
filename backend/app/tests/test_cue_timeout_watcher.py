"""Tests for Phase 28 cue_timeout_watcher — retry / abandon state machine.

Strategy:
- Use very short timeout (0.2s) to keep tests fast.
- Patch event_bus.publish with a recorder list to assert events.
- Clean Redis state between tests via fixture.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import CoordinationDirective
from app.agents.cue_timeout_watcher import (
    _cue_cooldown_key,
    cancel_cue_timeout_watcher,
    has_active_watcher,
    start_cue_timeout_watcher,
)
from app.agents.turn_controller import _cue_retry_key
from app.config import settings


PROJECT_ID = uuid4()
TARGET_SEAT = "crew_3"
FROM_SEAT = "supervisor"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _get_redis() -> Any:
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@pytest.fixture()
async def clean_state():
    """Wipe blackboard + cue keys for PROJECT_ID before/after each test."""
    r = await _get_redis()
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    yield
    # cancel any leftover watcher (test 失敗時防 leak)
    cancel_cue_timeout_watcher(PROJECT_ID, TARGET_SEAT)
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    await r.aclose()


@pytest.fixture()
def event_recorder():
    """Patch event_bus.publish to collect events instead of dispatching."""
    events: list[Any] = []

    async def _record(event: Any) -> None:
        events.append(event)

    with patch(
        "app.events.bus.event_bus.publish",
        new=AsyncMock(side_effect=_record),
    ):
        yield events


async def _seed_invited_speaker(seat: str = TARGET_SEAT) -> None:
    bb = BlackboardManager(
        project_id=PROJECT_ID,
        agent_id=f"agent_{FROM_SEAT}",
        seat_role=FROM_SEAT,
    )
    await bb.write_coordination_directive(
        CoordinationDirective(
            round_type="respond_to",
            invited_speaker=seat,
            instruction="輪到你發言",
        )
    )


async def _read_invited_speaker() -> str | None:
    bb = BlackboardManager(
        project_id=PROJECT_ID,
        agent_id=f"agent_{FROM_SEAT}",
        seat_role=FROM_SEAT,
    )
    directive = await bb.read_coordination_directive()
    return directive.invited_speaker if directive else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_watcher_fires_timeout_event_when_retry_below_max(
    clean_state, event_recorder
) -> None:
    """retry_count < max_retries → CueTimeoutEvent(will_retry=True) + 增加 counter。"""
    await _seed_invited_speaker()

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,  # min watcher TTL is 60s, but sleep itself is 1s
        max_retries=2,
    )
    # Wait long enough for the watcher's asyncio.sleep to fire.
    await asyncio.sleep(1.3)

    # CueTimeoutEvent fired with will_retry=True
    timeout_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueTimeoutEvent"
    ]
    assert len(timeout_events) == 1
    assert timeout_events[0].will_retry is True
    assert timeout_events[0].retry_count == 0
    assert timeout_events[0].max_retries == 2

    # No abandon event yet
    abandoned = [
        e for e in event_recorder if e.__class__.__name__ == "CueAbandonedEvent"
    ]
    assert abandoned == []

    # Retry counter incremented to 1
    r = await _get_redis()
    retry = await r.get(_cue_retry_key(PROJECT_ID, TARGET_SEAT))
    assert retry == "1"
    await r.aclose()

    # invited_speaker NOT cleared (waiting for supervisor reminder, B7)
    assert await _read_invited_speaker() == TARGET_SEAT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_watcher_fires_abandoned_event_at_max_retries(
    clean_state, event_recorder
) -> None:
    """retry_count == max_retries → CueAbandonedEvent + 清 invited + 設 cooldown。"""
    await _seed_invited_speaker()
    # Pre-set retry counter at max
    r = await _get_redis()
    await r.set(_cue_retry_key(PROJECT_ID, TARGET_SEAT), "2", ex=600)
    await r.aclose()

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=2,
    )
    await asyncio.sleep(1.3)

    # CueTimeoutEvent(will_retry=False) AND CueAbandonedEvent
    timeout_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueTimeoutEvent"
    ]
    abandoned_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueAbandonedEvent"
    ]
    assert len(timeout_events) == 1
    assert timeout_events[0].will_retry is False
    assert len(abandoned_events) == 1
    assert abandoned_events[0].total_attempts == 3  # max_retries + 1
    assert abandoned_events[0].cooldown_seconds == 300

    # invited_speaker cleared
    assert await _read_invited_speaker() is None

    # cooldown key set with TTL ~ 300
    r = await _get_redis()
    cooldown_ttl = await r.ttl(_cue_cooldown_key(PROJECT_ID, TARGET_SEAT))
    assert 290 < cooldown_ttl <= 300

    # retry counter reset
    assert await r.get(_cue_retry_key(PROJECT_ID, TARGET_SEAT)) is None
    await r.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_prevents_event_fire(clean_state, event_recorder) -> None:
    """cancel 後不該有任何 event。"""
    await _seed_invited_speaker()

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=2,
    )
    assert has_active_watcher(PROJECT_ID, TARGET_SEAT)
    cancelled = cancel_cue_timeout_watcher(PROJECT_ID, TARGET_SEAT)
    assert cancelled is True
    assert not has_active_watcher(PROJECT_ID, TARGET_SEAT)

    # Wait past timeout
    await asyncio.sleep(1.3)

    # No events fired
    assert event_recorder == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_is_idempotent(clean_state, event_recorder) -> None:
    """重複 start 應 cancel 舊 task、只 fire 一次 event。"""
    await _seed_invited_speaker()

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=5,
    )
    # 立刻 start 第二次（取代第一個）
    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=5,
    )
    await asyncio.sleep(1.3)

    timeout_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueTimeoutEvent"
    ]
    # 只有一個 event（第二次 start 取代了第一個 task）
    assert len(timeout_events) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_retries_zero_immediately_abandons(
    clean_state, event_recorder
) -> None:
    """max_retries=0 → 第一次 timeout 直接 abandoned（無 retry）。"""
    await _seed_invited_speaker()

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=0,
    )
    await asyncio.sleep(1.3)

    timeout_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueTimeoutEvent"
    ]
    abandoned_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueAbandonedEvent"
    ]
    assert len(timeout_events) == 1
    assert timeout_events[0].will_retry is False
    assert len(abandoned_events) == 1
    assert abandoned_events[0].total_attempts == 1  # 0 + 1
    assert await _read_invited_speaker() is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_retry_cycle(clean_state, event_recorder) -> None:
    """連續跑 3 個 watcher cycle 模擬 supervisor reminder：retry 從 0 → 1 → 2 → abandoned。

    Cycle 1: retry=0 → will_retry=True, counter=1
    Cycle 2: retry=1 → will_retry=True, counter=2
    Cycle 3: retry=2 (= max_retries) → will_retry=False + Abandoned
    """
    await _seed_invited_speaker()
    max_retries = 2

    # Cycle 1
    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=max_retries,
    )
    await asyncio.sleep(1.3)

    # Cycle 2 (simulating supervisor re-cue)
    await _seed_invited_speaker()
    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=max_retries,
    )
    await asyncio.sleep(1.3)

    # Cycle 3 (final, should abandon)
    await _seed_invited_speaker()
    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=max_retries,
    )
    await asyncio.sleep(1.3)

    timeout_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueTimeoutEvent"
    ]
    abandoned_events = [
        e for e in event_recorder if e.__class__.__name__ == "CueAbandonedEvent"
    ]
    assert len(timeout_events) == 3
    # First two cycles: will_retry=True; third: will_retry=False
    assert [e.will_retry for e in timeout_events] == [True, True, False]
    assert [e.retry_count for e in timeout_events] == [0, 1, 2]
    assert len(abandoned_events) == 1
    assert abandoned_events[0].total_attempts == max_retries + 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_human_seat_timeout_holds_and_suspends(
    clean_state, event_recorder, monkeypatch
) -> None:
    """Phase 43：人類席 cue 逾時 → 貼 hold 訊息 + suspend_room，保留 invited_speaker，
    不放棄（無 CueAbandonedEvent）、不重啟倒數。"""
    from app.db.models.seat import SEAT_ROLE_HUMAN_CREATOR

    suspend = AsyncMock()
    hold = AsyncMock()
    monkeypatch.setattr("app.agents.room_hibernation.suspend_room", suspend)
    monkeypatch.setattr(
        "app.agents.cue_chat_messages.publish_awaiting_hold_chat", hold
    )

    await _seed_invited_speaker(SEAT_ROLE_HUMAN_CREATOR)
    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=SEAT_ROLE_HUMAN_CREATOR,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=5,
    )
    await asyncio.sleep(1.3)

    # hold 訊息 + 全房休眠各一次（不論 max_retries，第一次逾時即等待）
    hold.assert_awaited_once()
    suspend.assert_awaited_once_with(PROJECT_ID)

    # invited_speaker 保留（仍在等這位真人）
    assert await _read_invited_speaker() == SEAT_ROLE_HUMAN_CREATOR

    # 無放棄：沒有 CueAbandonedEvent
    abandoned = [
        e for e in event_recorder if e.__class__.__name__ == "CueAbandonedEvent"
    ]
    assert abandoned == []
