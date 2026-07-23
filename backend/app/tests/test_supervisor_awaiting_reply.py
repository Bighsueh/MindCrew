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
def test_detect_mention_skips_supervisor() -> None:
    # supervisor 不該被當成 awaited（避免自我點名死循環）
    assert detect_crew_mention("AI 引導者開場", _SEATS) is None


@pytest.mark.unit
def test_detect_mention_hits_human_seat_by_user_name() -> None:
    # Phase 28：人類席位也應該被命中（用 user_name fallback）
    assert detect_crew_mention("Alice 你覺得呢？", _SEATS) == ("crew_3", "Alice")


@pytest.mark.unit
def test_detect_mention_prefers_display_name_over_user_name() -> None:
    # 當 human seat 同時有 display_name 與 user_name 時，優先使用 display_name
    seats = [
        {
            "role": "crew_1",
            "type": "human",
            "display_name": "小明",
            "user_name": "ming123",
        },
    ]
    assert detect_crew_mention("小明，輪到你了", seats) == ("crew_1", "小明")
    # user_name 不應命中（因為 display_name 是優先選擇）
    assert detect_crew_mention("ming123，輪到你了", seats) is None


@pytest.mark.unit
def test_detect_mention_falls_back_to_agent_id() -> None:
    # 罕見場景：seat 既沒 display_name 也沒 user_name，fallback 到 agent_id
    seats = [
        {"role": "crew_2", "type": "ai", "agent_id": "agent_crew_2"},
    ]
    assert detect_crew_mention("agent_crew_2 請接話", seats) == (
        "crew_2",
        "agent_crew_2",
    )


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_awaiting_if_seat_matches_only_awaited() -> None:
    """主動清鎖：只有「等的對象」發話才清，等別人時不清（修暖場連環催）。"""
    from app.agents.supervisor.awaiting_reply import clear_awaiting_if_seat

    project_id = uuid4()
    await set_awaiting_reply(project_id, "crew_1", "tt")

    # 別的席位發話 → 不清
    assert await clear_awaiting_if_seat(project_id, "crew_2") is False
    assert (await check_awaiting_reply(project_id, recent_chat=[])) is not None

    # 等的對象（crew_1 / 人類 tt）發話 → 清掉
    assert await clear_awaiting_if_seat(project_id, "crew_1") is True
    assert (await check_awaiting_reply(project_id, recent_chat=[])) is None

    # 沒鎖時呼叫 → False（不炸）
    assert await clear_awaiting_if_seat(project_id, "crew_1") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_awaiting_any_clears_regardless_of_seat() -> None:
    """A1（連發死房修）：clear_awaiting_any 不論鎖在誰身上都清。

    場景：組長 @ 點名 crew_1 設鎖 → 人類（非 crew_1）在群組發話 → 應清掉 crew 鎖，
    讓組長下個 tick 接話（clear_awaiting_if_seat 因 seat 不符不會清 → 死房根因）。
    """
    from app.agents.supervisor.awaiting_reply import clear_awaiting_any

    project_id = uuid4()
    await set_awaiting_reply(project_id, "crew_1", "陳建宏")
    assert (await check_awaiting_reply(project_id, recent_chat=[])) is not None

    # clear_awaiting_if_seat 對「不是被等對象」的人類席位不清（對照）
    from app.agents.supervisor.awaiting_reply import clear_awaiting_if_seat
    assert await clear_awaiting_if_seat(project_id, "human_creator") is False
    assert (await check_awaiting_reply(project_id, recent_chat=[])) is not None

    # clear_awaiting_any 無條件清
    assert await clear_awaiting_any(project_id) is True
    assert (await check_awaiting_reply(project_id, recent_chat=[])) is None
    # 沒鎖時回 False（不炸）
    assert await clear_awaiting_any(project_id) is False
