"""Phase 35: B3* trigger 同 phase 只 fire 一次 (spec/16 §6.5.5)."""

from __future__ import annotations

import pytest

from app.agents.supervisor.triggers_b import detect_b_triggers


def _ctx(
    *,
    used_pct: float,
    phase_intent: str = "divergent",
    fired: set[str] | None = None,
) -> dict:
    return {
        "current_sub_phase": "1.1a",
        "time_budget_used_pct": used_pct,
        "phase_intent": phase_intent,
        "_deliverable_done": False,
        "recent_chat": [],
        "_supervisor_fired_triggers": fired or set(),
    }


def _ids(fired_list) -> set[str]:
    return {tid for tid, _ in fired_list}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b3a_dedup_when_already_fired() -> None:
    # 第一次 ctx 無已 fire 紀錄 → 觸發
    first = await detect_b_triggers(_ctx(used_pct=55.0))
    assert "B3a_halfway_pivot" in _ids(first)
    # 第二次 ctx 含已 fire 紀錄 → 不觸發
    second = await detect_b_triggers(
        _ctx(used_pct=55.0, fired={"B3a_halfway_pivot"})
    )
    assert "B3a_halfway_pivot" not in _ids(second)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b3b_dedup() -> None:
    second = await detect_b_triggers(
        _ctx(used_pct=70.0, fired={"B3b_two_thirds_focus"})
    )
    assert "B3b_two_thirds_focus" not in _ids(second)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b3c_dedup() -> None:
    second = await detect_b_triggers(
        _ctx(used_pct=80.0, fired={"B3c_close_diverge"})
    )
    assert "B3c_close_diverge" not in _ids(second)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b3_critical_dedup() -> None:
    second = await detect_b_triggers(
        _ctx(used_pct=95.0, fired={"B3_critical_rescope"})
    )
    assert "B3_critical_rescope" not in _ids(second)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dedup_only_affects_listed_triggers() -> None:
    # 即使 B3a 已 fire，B3b（不同 trigger）可以 fire
    fired = await detect_b_triggers(
        _ctx(used_pct=70.0, fired={"B3a_halfway_pivot"})
    )
    assert "B3b_two_thirds_focus" in _ids(fired)
