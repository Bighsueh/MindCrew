"""Tests for supervisor awaiting-reply lock (Fix #1)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.agents.supervisor.awaiting_reply import (
    check_awaiting_reply,
    detect_crew_mention,
    set_awaiting_reply,
)


_SEATS = [
    {"role": "supervisor", "type": "ai", "display_name": "AI 引導者"},
    {"role": "crew_1", "type": "ai", "display_name": "陳建宏"},
    {"role": "crew_2", "type": "ai", "display_name": "林雅婷"},
    {"role": "crew_3", "type": "human", "user_name": "Alice"},
]


@pytest.mark.unit
def test_detect_mention_by_display_name() -> None:
    assert detect_crew_mention("陳建宏，換你分享", _SEATS) == ("crew_1", "陳建宏")


@pytest.mark.unit
def test_detect_mention_skips_supervisor_and_human() -> None:
    # supervisor 不該被當成 awaited
    assert detect_crew_mention("AI 引導者開場", _SEATS) is None
    # human 不在 seats[type=ai] → 不被偵測
    assert detect_crew_mention("Alice 你覺得呢？", _SEATS) is None


@pytest.mark.unit
def test_detect_mention_no_match() -> None:
    assert detect_crew_mention("大家覺得呢？", _SEATS) is None
    assert detect_crew_mention("", _SEATS) is None
    assert detect_crew_mention("陳建宏", []) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_blocks_until_crew_replies() -> None:
    """設鎖後，recent_chat 沒有 crew 訊息 → 仍 awaiting；有則自動清鎖。"""
    project_id = uuid4()

    await set_awaiting_reply(project_id, "crew_1", "陳建宏")

    # crew 還沒回覆 → 鎖仍在
    awaited = await check_awaiting_reply(project_id, recent_chat=[])
    assert awaited is not None
    assert awaited.seat_role == "crew_1"
    assert awaited.display_name == "陳建宏"

    # crew 回覆後 → 鎖被清除
    chat = [
        {"sender_id": "agent_crew_1", "sender": "陳建宏(ai)", "content": "好的"},
    ]
    awaited = await check_awaiting_reply(project_id, recent_chat=chat)
    assert awaited is None

    # 再查一次：鎖已清，確實 None
    awaited = await check_awaiting_reply(project_id, recent_chat=[])
    assert awaited is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_clears_by_display_name_match() -> None:
    """sender_id 不含 seat_role 時，靠 sender 顯示名稱也能清鎖。"""
    project_id = uuid4()
    await set_awaiting_reply(project_id, "crew_2", "林雅婷")

    chat = [
        {"sender_id": "agent_xyz", "sender": "林雅婷(ai)", "content": "我覺得..."},
    ]
    awaited = await check_awaiting_reply(project_id, recent_chat=chat)
    assert awaited is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_ignores_other_crew_messages() -> None:
    """其他 crew 講話不會清掉 awaited crew_1 的鎖。"""
    project_id = uuid4()
    await set_awaiting_reply(project_id, "crew_1", "陳建宏")

    chat = [
        {"sender_id": "agent_crew_2", "sender": "林雅婷(ai)", "content": "我先說"},
    ]
    awaited = await check_awaiting_reply(project_id, recent_chat=chat)
    assert awaited is not None
    assert awaited.seat_role == "crew_1"
