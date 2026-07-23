"""Phase 37: capability_class-aware provider routing.

Covers the gap noted during planning — no prior tests exercised ProviderRouter
selection. Uses fake ProviderEntry rows (no DB) and monkeypatches
``ProviderRegistry.get_entries`` so the router logic is tested in isolation.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.registry import ProviderEntry, ProviderRegistry
from app.llm.router import ProviderRouter
from app.llm.routing_policy import resolve_class


def _entry(name: str, capability_class: str, tier: int = 1) -> ProviderEntry:
    """Build a fake entry; router only reads row.{id,name,tier,capability_class}."""
    row = SimpleNamespace(
        id=name, name=name, tier=tier, capability_class=capability_class
    )
    return ProviderEntry(row=row, instance=object())  # type: ignore[arg-type]


@pytest.fixture
def fake_entries(monkeypatch):
    entries: list[ProviderEntry] = []

    async def _get_entries(*_a, **_k):
        return entries

    monkeypatch.setattr(ProviderRegistry, "get_entries", _get_entries)
    ProviderRouter.reset()
    yield entries
    ProviderRouter.reset()


async def _collect(required_class: str) -> list[str]:
    return [e.row.name async for e in ProviderRouter.iter_candidates(required_class)]


# ── resolve_class (pure) ────────────────────────────────────────────────


def test_resolve_class_quality_callers() -> None:
    assert resolve_class("persona_generation") == "quality"
    assert resolve_class("evaluator_qualitative") == "quality"
    assert resolve_class("first_diamond_closing") == "quality"


def test_resolve_class_defaults_to_standard() -> None:
    assert resolve_class("agent_think") == "standard"
    assert resolve_class("totally_unknown_caller") == "standard"
    assert resolve_class(None) == "standard"


# ── class-scoped selection ──────────────────────────────────────────────


async def test_quality_request_prefers_quality_then_degrades(fake_entries) -> None:
    fake_entries.extend([_entry("gpt", "standard"), _entry("gemma", "quality")])
    got = await _collect("quality")
    # quality served first; standard included only as cross-class degrade tail
    assert got[0] == "gemma"
    assert got == ["gemma", "gpt"]


async def test_standard_request_prefers_standard(fake_entries) -> None:
    fake_entries.extend([_entry("gpt", "standard"), _entry("gemma", "quality")])
    got = await _collect("standard")
    assert got[0] == "gpt"


# ── round-robin within a (class, tier) bucket ───────────────────────────


async def test_round_robin_within_pool(fake_entries) -> None:
    fake_entries.extend([_entry("q1", "quality"), _entry("q2", "quality")])
    first = await _collect("quality")
    second = await _collect("quality")
    assert first[0] != second[0]  # rotation advanced
    assert {first[0], second[0]} == {"q1", "q2"}


# ── cross-class degrade ─────────────────────────────────────────────────


async def test_degrade_when_required_class_absent(fake_entries) -> None:
    fake_entries.append(_entry("gpt", "standard"))
    assert await _collect("quality") == ["gpt"]


async def test_degrade_when_required_class_all_cooled_down(fake_entries) -> None:
    gpt = _entry("gpt", "standard")
    gemma = _entry("gemma", "quality")
    fake_entries.extend([gpt, gemma])
    ProviderRouter.mark_failure(gemma)  # quality pool cools down
    assert await _collect("quality") == ["gpt"]


# ── tier cascade stays within a class ───────────────────────────────────


async def test_tier_cascade_within_class(fake_entries) -> None:
    fake_entries.extend(
        [_entry("q1", "quality", tier=1), _entry("q2", "quality", tier=2)]
    )
    assert await _collect("quality") == ["q1", "q2"]


# ── streaming primary ───────────────────────────────────────────────────


async def test_primary_for_streaming_respects_class(fake_entries) -> None:
    fake_entries.extend([_entry("gpt", "standard"), _entry("gemma", "quality")])
    q = await ProviderRouter.primary_for_streaming("quality")
    s = await ProviderRouter.primary_for_streaming("standard")
    assert q is not None and q.row.name == "gemma"
    assert s is not None and s.row.name == "gpt"


async def test_primary_for_streaming_none_when_empty(fake_entries) -> None:
    assert await ProviderRouter.primary_for_streaming("quality") is None
