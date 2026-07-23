"""Phase 42（1.1a 隊友沉默修復）：share_experience 經驗分享參與彙整單元測試。

純函式邏輯（mock round_lock.get_state ＋ 跳過集合），不需 DB / Redis。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.progression import share_experience
from app.progression.share_experience import share_status


def _patch_state(monkeypatch, state: dict) -> None:
    async def _fake_get_state(project_id, sub_phase):
        return state

    monkeypatch.setattr(
        "app.agents.round_lock.get_state", _fake_get_state, raising=True
    )


def _patch_skipped(monkeypatch, skipped: set[str]) -> None:
    async def _fake_skipped(project_id):
        return set(skipped)

    monkeypatch.setattr(share_experience, "_skipped_seats", _fake_skipped)


@pytest.mark.asyncio
async def test_all_ai_room_all_shared(monkeypatch):
    """全 AI 房（has_human False）→ all_shared True、不驅動邀請。"""
    _patch_state(monkeypatch, {"has_human": False, "round": 1})
    _patch_skipped(monkeypatch, set())
    st = await share_status(uuid4())
    assert st.has_human is False
    assert st.all_shared is True
    assert st.missing_crews == () and st.missing_crew_seats == ()


@pytest.mark.asyncio
async def test_partial_participation_computes_missing(monkeypatch):
    """4 crew、2 已分享 → 另 2 列入 missing（raw 席位排序），真人 round≥2 視為已分享。"""
    _patch_state(
        monkeypatch,
        {
            "has_human": True,
            "round": 2,
            "ai_crew": ["crew_1", "crew_2", "crew_3", "crew_4"],
            "participated_crews": ["crew_1", "crew_3"],
            "human_inputs": [],
        },
    )
    _patch_skipped(monkeypatch, set())
    st = await share_status(uuid4())
    assert st.has_human is True
    assert st.human_shared is True  # round >= 2
    assert st.missing_crew_seats == ("crew_2", "crew_4")
    assert len(st.missing_crews) == 2
    assert st.all_shared is False


@pytest.mark.asyncio
async def test_human_not_shared_blocks_all_shared(monkeypatch):
    """全 crew 都分享過，但真人還沒（round 1、無 human_inputs）→ all_shared False。"""
    _patch_state(
        monkeypatch,
        {
            "has_human": True,
            "round": 1,
            "ai_crew": ["crew_1", "crew_2"],
            "participated_crews": ["crew_1", "crew_2"],
            "human_inputs": [],
        },
    )
    _patch_skipped(monkeypatch, set())
    st = await share_status(uuid4())
    assert st.human_shared is False
    assert st.missing_crew_seats == ()
    assert st.all_shared is False


@pytest.mark.asyncio
async def test_human_shared_via_inputs(monkeypatch):
    """真人 round 1 但已有實質輸入（human_inputs 非空）→ human_shared True。"""
    _patch_state(
        monkeypatch,
        {
            "has_human": True,
            "round": 1,
            "ai_crew": ["crew_1"],
            "participated_crews": ["crew_1"],
            "human_inputs": ["chat"],
        },
    )
    _patch_skipped(monkeypatch, set())
    st = await share_status(uuid4())
    assert st.human_shared is True
    assert st.all_shared is True


@pytest.mark.asyncio
async def test_skipped_seat_subtracted_from_missing(monkeypatch):
    """被點名 ≥ cap 次仍沉默的席位（skipped）從 missing 扣除——不卡死迴圈。"""
    _patch_state(
        monkeypatch,
        {
            "has_human": True,
            "round": 2,
            "ai_crew": ["crew_1", "crew_2", "crew_3"],
            "participated_crews": ["crew_1"],
            "human_inputs": ["chat"],
        },
    )
    _patch_skipped(monkeypatch, {"crew_2"})  # crew_2 邀太多次沒回 → 跳過
    st = await share_status(uuid4())
    assert st.missing_crew_seats == ("crew_3",)  # crew_2 被跳過
    assert st.all_shared is False  # crew_3 還沒分享


@pytest.mark.asyncio
async def test_get_state_failure_is_conservative(monkeypatch):
    """round_lock 讀不到 → 保守當全員已分享（不驅動邀請/不開安全網，交時間兜底）。"""

    async def _boom(project_id, sub_phase):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.agents.round_lock.get_state", _boom, raising=True)
    st = await share_status(uuid4())
    assert st.all_shared is True
    assert st.has_human is False
