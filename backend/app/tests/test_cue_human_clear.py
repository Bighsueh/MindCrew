"""Tests for Phase 28 cue-human clear hook (notify_human_speak_in_group).

涵蓋場景：
- 人類被 cue → 在群組發話 → invited_speaker 被清空
- 人類未被 cue → notify 為 no-op，不影響任何 state
- retry counter Redis key 被刪除（B4 watcher 用）
- blackboard 異常時 best-effort 不 raise
- reset_cue_retry 純函數行為
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import CoordinationDirective
from app.agents.turn_controller import (
    _cue_retry_key,
    notify_human_speak_in_group,
    reset_cue_retry,
)
from app.config import settings


PROJECT_ID = uuid4()
HUMAN_SEAT = "crew_3"
AI_SEAT = "crew_1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _get_redis():
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@pytest.fixture()
async def clean_state():
    """Wipe all blackboard / cue keys for PROJECT_ID before & after each test."""
    r = await _get_redis()
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    yield
    for prefix in (f"blackboard:{PROJECT_ID}:", f"project:{PROJECT_ID}:"):
        keys = await r.keys(f"{prefix}*")
        if keys:
            await r.delete(*keys)
    await r.aclose()


async def _cue_human(seat_role: str = HUMAN_SEAT) -> None:
    """Helper：由 supervisor 視角寫一個 invited_speaker=human 的 directive。"""
    bb = BlackboardManager(
        project_id=PROJECT_ID,
        agent_id="agent_supervisor",
        seat_role="supervisor",
    )
    await bb.write_coordination_directive(
        CoordinationDirective(
            round_type="respond_to",
            invited_speaker=seat_role,
            instruction="想聽聽你的想法",
        )
    )


async def _read_invited_speaker() -> str | None:
    bb = BlackboardManager(
        project_id=PROJECT_ID,
        agent_id="agent_supervisor",
        seat_role="supervisor",
    )
    directive = await bb.read_coordination_directive()
    return directive.invited_speaker if directive else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notify_clears_invited_speaker_when_human_seat_matches(
    clean_state,
) -> None:
    """人類被 cue → 在群組發話 → invited_speaker 被清空。"""
    await _cue_human(HUMAN_SEAT)
    assert await _read_invited_speaker() == HUMAN_SEAT

    await notify_human_speak_in_group(PROJECT_ID, HUMAN_SEAT, "cued")

    assert await _read_invited_speaker() is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notify_noop_when_not_invited(clean_state) -> None:
    """沒被 cue 的人類發話 → blackboard 不變、Redis 不變。"""
    # 沒寫任何 directive
    assert await _read_invited_speaker() is None

    await notify_human_speak_in_group(PROJECT_ID, HUMAN_SEAT, "cued")

    # 仍然沒有 directive、沒有 retry key
    assert await _read_invited_speaker() is None
    r = await _get_redis()
    assert await r.get(_cue_retry_key(PROJECT_ID, HUMAN_SEAT)) is None
    await r.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notify_noop_when_invited_is_another_seat(clean_state) -> None:
    """invited_speaker 指向其他席位 → 該人類發話不該清掉別人的 cue。"""
    await _cue_human(AI_SEAT)  # 點的是 AI，不是這個 human

    await notify_human_speak_in_group(PROJECT_ID, HUMAN_SEAT, "cued")

    # AI 的 cue 維持不變
    assert await _read_invited_speaker() == AI_SEAT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notify_resets_retry_counter(clean_state) -> None:
    """notify 後 retry counter Redis key 被刪除（B4 watcher 共用）。"""
    await _cue_human(HUMAN_SEAT)
    r = await _get_redis()
    retry_key = _cue_retry_key(PROJECT_ID, HUMAN_SEAT)
    await r.set(retry_key, "2", ex=600)
    assert await r.get(retry_key) == "2"

    await notify_human_speak_in_group(PROJECT_ID, HUMAN_SEAT, "cued")

    assert await r.get(retry_key) is None
    await r.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notify_handles_empty_seat_role_gracefully(clean_state) -> None:
    """seat_role 為空字串 → 早期 return，不 raise、不影響 state。"""
    await _cue_human(HUMAN_SEAT)

    # 不應該 raise
    await notify_human_speak_in_group(PROJECT_ID, "", "cued")

    # 原本的 cue 維持
    assert await _read_invited_speaker() == HUMAN_SEAT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_cue_retry_deletes_key(clean_state) -> None:
    """reset_cue_retry helper 直接 DEL Redis key。"""
    r = await _get_redis()
    key = _cue_retry_key(PROJECT_ID, HUMAN_SEAT)
    await r.set(key, "3", ex=600)
    assert await r.get(key) == "3"

    await reset_cue_retry(PROJECT_ID, HUMAN_SEAT)

    assert await r.get(key) is None
    await r.aclose()
