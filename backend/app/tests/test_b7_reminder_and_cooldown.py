"""B7 tests: reminder/pivot chat templates + cooldown guard."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import CoordinationDirective
from app.agents.cue_chat_messages import (
    build_pivot_content,
    build_reminder_content,
)
from app.agents.cue_timeout_watcher import (
    _cue_cooldown_key,
    cancel_cue_timeout_watcher,
    start_cue_timeout_watcher,
)
from app.config import settings


PROJECT_ID = uuid4()
TARGET_SEAT = "crew_3"
FROM_SEAT = "supervisor"


async def _get_redis() -> Any:
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@pytest.fixture()
async def clean_state():
    r = await _get_redis()
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    yield
    cancel_cue_timeout_watcher(PROJECT_ID, TARGET_SEAT)
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    await r.aclose()


@pytest.fixture()
def event_recorder():
    events: list[Any] = []

    async def _record(event: Any) -> None:
        events.append(event)

    with patch(
        "app.events.bus.event_bus.publish",
        new=AsyncMock(side_effect=_record),
    ):
        yield events


# ---------------------------------------------------------------------------
# Reminder template tests（純函數，無 IO）
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reminder_first_retry_uses_encouraging_tone() -> None:
    content = build_reminder_content(
        human_name="小明", retry_count=0, max_retries=5, elapsed_minutes=3
    )
    assert "小明" in content
    assert "慢慢想" in content
    assert "pass" in content


@pytest.mark.unit
def test_reminder_last_retry_gives_face_saving_exit() -> None:
    content = build_reminder_content(
        human_name="Alice", retry_count=4, max_retries=5, elapsed_minutes=15
    )
    assert "Alice" in content
    assert "最後一次" in content
    assert "pass" in content


@pytest.mark.unit
def test_reminder_mid_retry_neutral() -> None:
    content = build_reminder_content(
        human_name="王同學", retry_count=2, max_retries=5, elapsed_minutes=9
    )
    assert "王同學" in content
    # attempt_num = retry_count + 2 = 4；total = max_retries + 1 = 6
    assert "4/6" in content
    assert "你的想法" in content or "邀請" in content


@pytest.mark.unit
def test_pivot_template_mentions_human_name_and_attempts() -> None:
    content = build_pivot_content(human_name="小明", total_attempts=6)
    assert "小明" in content
    assert "6" in content
    assert "繼續" in content


# ---------------------------------------------------------------------------
# Cooldown guard tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cooldown_key_set_after_abandon(clean_state, event_recorder) -> None:
    """達 abandon 後 Redis 應有 cue_cooldown key（300s TTL）。"""
    bb = BlackboardManager(
        project_id=PROJECT_ID, agent_id="agent_supervisor", seat_role=FROM_SEAT
    )
    await bb.write_coordination_directive(
        CoordinationDirective(
            round_type="respond_to",
            invited_speaker=TARGET_SEAT,
            instruction="輪到你",
        )
    )
    # Pre-set retry to max
    r = await _get_redis()
    from app.agents.turn_controller import _cue_retry_key

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

    r = await _get_redis()
    cooldown_ttl = await r.ttl(_cue_cooldown_key(PROJECT_ID, TARGET_SEAT))
    assert 290 < cooldown_ttl <= 300
    await r.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_in_cooldown_helper(clean_state) -> None:
    from app.agents.act import _is_in_cooldown

    assert await _is_in_cooldown(PROJECT_ID, TARGET_SEAT) is False
    r = await _get_redis()
    await r.set(_cue_cooldown_key(PROJECT_ID, TARGET_SEAT), "1", ex=300)
    await r.aclose()
    assert await _is_in_cooldown(PROJECT_ID, TARGET_SEAT) is True


# ---------------------------------------------------------------------------
# Retry cycle integration（reminder 訊息真的被 publish 到 chat）
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_cycle_publishes_reminder_chat_message(
    clean_state, event_recorder
) -> None:
    """watcher 進入 retry 時應 publish 一筆 ChatMessageEvent（reminder）。"""
    bb = BlackboardManager(
        project_id=PROJECT_ID, agent_id="agent_supervisor", seat_role=FROM_SEAT
    )
    await bb.write_coordination_directive(
        CoordinationDirective(
            round_type="respond_to",
            invited_speaker=TARGET_SEAT,
            instruction="輪到你",
        )
    )

    await start_cue_timeout_watcher(
        project_id=PROJECT_ID,
        target_seat_role=TARGET_SEAT,
        from_seat_role=FROM_SEAT,
        timeout_seconds=1,
        max_retries=5,
    )
    await asyncio.sleep(1.3)
    # cancel 接下來自動 retry 的 watcher（rewrite 後 restart 的）
    cancel_cue_timeout_watcher(PROJECT_ID, TARGET_SEAT)

    chat_events = [
        e for e in event_recorder if e.__class__.__name__ == "ChatMessageEvent"
    ]
    assert len(chat_events) >= 1
    reminder = chat_events[0]
    assert reminder.sender_type == "ai"
    assert "pass" in reminder.content
