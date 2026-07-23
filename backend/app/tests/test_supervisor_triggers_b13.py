"""Unit tests for B13_share_invite_next（Phase 42，1.1a 隊友沉默修復；spec 22 1.1a）。

B13：1.1a 引導式逐一邀請——組長把每位還沒分享過自身經驗的隊友一位一位帶出來。
無 dedup（每 tick 重發直到全員分享）；須在 A1 進場宣布後才邀（announce→invite 次序）。
空 recent_chat 隔離掉 B1/B2/B12 等 judge-based trigger，專測 B13。
"""
from __future__ import annotations

import pytest

from app.agents.supervisor.triggers_b import detect_b_triggers
from app.progression.share_experience import ShareStatus


def _ctx(
    *,
    share_status: ShareStatus | None,
    a1_fired: bool = True,
    sub_phase: str = "1.1a",
) -> dict:
    fired_set: set[str] = {"A1_phase_enter_announce"} if a1_fired else set()
    return {
        "current_sub_phase": sub_phase,
        "recent_chat": [],  # 空 → B1/B2/B12 不呼叫 judge
        "time_budget_used_pct": 0.0,
        "phase_intent": "divergent",
        "_deliverable_done": False,
        "_supervisor_fired_triggers": fired_set,
        "_share_status": share_status,
    }


def _fired_ids(fired: list[tuple[str, dict]]) -> set[str]:
    return {tid for tid, _ in fired}


_MISSING = ShareStatus(
    has_human=True,
    human_shared=False,
    missing_crews=("阿明", "小美"),
    missing_crew_seats=("crew_2", "crew_3"),
    all_shared=False,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_fires_when_crew_missing() -> None:
    fired = await detect_b_triggers(_ctx(share_status=_MISSING))
    assert "B13_share_invite_next" in _fired_ids(fired)
    payload = dict(fired)["B13_share_invite_next"]
    assert payload["next_crew_seat"] == "crew_2"   # 最小未分享席位
    assert payload["next_crew_name"] == "阿明"
    assert payload["remaining"] == "2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_fires_even_without_a1_fired() -> None:
    """B13 不依賴 A1 已 fire（live 揪出 B12 每 tick 餓死 A1 → 若 gate 在 A1，B13 連帶餓死）。
    框題由 1.1a 進場腳本承載；只要本關有未分享 crew 即可邀。"""
    fired = await detect_b_triggers(_ctx(share_status=_MISSING, a1_fired=False))
    assert "B13_share_invite_next" in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_not_fire_when_all_shared() -> None:
    done = ShareStatus(
        has_human=True, human_shared=True,
        missing_crews=(), missing_crew_seats=(), all_shared=True,
    )
    fired = await detect_b_triggers(_ctx(share_status=done))
    assert "B13_share_invite_next" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_not_fire_in_all_ai_room() -> None:
    all_ai = ShareStatus(
        has_human=False, human_shared=True,
        missing_crews=(), missing_crew_seats=(), all_shared=True,
    )
    fired = await detect_b_triggers(_ctx(share_status=all_ai))
    assert "B13_share_invite_next" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_not_fire_without_share_status() -> None:
    """非 1.1a（context_buffer 不注入 _share_status）→ 不 fire。"""
    fired = await detect_b_triggers(_ctx(share_status=None, sub_phase="1.2"))
    assert "B13_share_invite_next" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_bumps_invite_for_target_seat(monkeypatch: pytest.MonkeyPatch) -> None:
    """B13 fire 時對目標席位累計一次邀請（防失能 crew 卡死、涵蓋兩執行路徑）。"""
    from uuid import uuid4

    import app.progression.share_experience as se

    calls: list = []

    async def _fake_bump(project_id, seat_role):
        calls.append((project_id, seat_role))

    monkeypatch.setattr(se, "bump_invite", _fake_bump)
    pid = uuid4()
    ctx = _ctx(share_status=_MISSING)
    ctx["_project_id"] = pid
    await detect_b_triggers(ctx)
    assert calls == [(pid, "crew_2")]  # 最小未分享席位被累計一次


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_no_bump_without_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺 _project_id（防呆）→ 不 bump、不報錯。"""
    import app.progression.share_experience as se

    calls: list = []

    async def _fake_bump(project_id, seat_role):
        calls.append((project_id, seat_role))

    monkeypatch.setattr(se, "bump_invite", _fake_bump)
    await detect_b_triggers(_ctx(share_status=_MISSING))  # no _project_id
    assert calls == []


@pytest.mark.unit
def test_b13_not_in_dedup_eligible() -> None:
    """必須每 tick 重發直到全員分享——不可 dedup。"""
    from app.agents.supervisor.router import _DEDUP_ELIGIBLE_TRIGGERS

    assert "B13_share_invite_next" not in _DEDUP_ELIGIBLE_TRIGGERS
