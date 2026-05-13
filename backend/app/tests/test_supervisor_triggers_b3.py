"""Unit tests for Supervisor B3 系列遞進 trigger (specs/16-timer-system.md §6.5.5)."""

from __future__ import annotations

import pytest

from app.agents.supervisor.triggers_b import detect_b_triggers


def _ctx(*, used_pct: float, phase_intent: str = "divergent", deliverable_done: bool = False) -> dict:
    return {
        "current_sub_phase": "1.1a",
        "time_budget_used_pct": used_pct,
        "phase_intent": phase_intent,
        "_deliverable_done": deliverable_done,
        "recent_chat": [],  # 空 chat 避免 B1/B2 觸發 LLM judge
    }


def _fired_ids(fired: list[tuple[str, dict]]) -> set[str]:
    return {tid for tid, _ in fired}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calm_below_50_fires_nothing_b3() -> None:
    fired = await detect_b_triggers(_ctx(used_pct=49.0))
    ids = _fired_ids(fired)
    assert not any(name.startswith("B3") for name in ids)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_halfway_divergent_fires_b3a() -> None:
    fired = await detect_b_triggers(_ctx(used_pct=55.0, phase_intent="divergent"))
    assert "B3a_halfway_pivot" in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_halfway_convergent_does_not_fire_b3a() -> None:
    # 50-67% 且收斂階段：不該觸發 b3a（halfway pivot 是給發散階段的）
    fired = await detect_b_triggers(_ctx(used_pct=55.0, phase_intent="convergent"))
    ids = _fired_ids(fired)
    assert "B3a_halfway_pivot" not in ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_thirds_any_intent_fires_b3b() -> None:
    for intent in ("divergent", "convergent", "transitional"):
        fired = await detect_b_triggers(_ctx(used_pct=70.0, phase_intent=intent))
        assert "B3b_two_thirds_focus" in _fired_ids(fired), f"intent={intent}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tight_divergent_fires_b3c() -> None:
    fired = await detect_b_triggers(_ctx(used_pct=80.0, phase_intent="divergent"))
    assert "B3c_close_diverge" in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tight_convergent_does_not_fire_b3c() -> None:
    # 75-90% 收斂階段不需強制結束發散
    fired = await detect_b_triggers(_ctx(used_pct=80.0, phase_intent="convergent"))
    assert "B3c_close_diverge" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critical_fires_only_when_deliverable_not_done() -> None:
    not_done = await detect_b_triggers(_ctx(used_pct=95.0, deliverable_done=False))
    assert "B3_critical_rescope" in _fired_ids(not_done)

    done = await detect_b_triggers(_ctx(used_pct=95.0, deliverable_done=True))
    assert "B3_critical_rescope" not in _fired_ids(done)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b3_tiers_are_exclusive() -> None:
    # 同一 used_pct 不該同時觸發多個 B3 tier（elif 鏈）
    fired = await detect_b_triggers(_ctx(used_pct=80.0, phase_intent="divergent"))
    b3_ids = [tid for tid in _fired_ids(fired) if tid.startswith("B3")]
    assert len(b3_ids) == 1, f"expected exactly one B3 tier, got {b3_ids}"
