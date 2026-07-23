"""Tests for zone auto-seed on sub_phase entry."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.canvas import zone_seed

pytestmark = pytest.mark.asyncio


async def test_seed_draws_declared_zone(monkeypatch):
    drawn: list[str] = []

    async def _not_registered(*args, **kwargs):
        return False

    async def _fake_draw(project_id, zone_id, **kwargs):
        drawn.append(zone_id)
        return {"success": True}

    async def _empty_board(project_id):
        return 0.0

    monkeypatch.setattr(zone_seed, "is_zone_registered", _not_registered)
    monkeypatch.setattr(zone_seed, "tool_draw_zone", _fake_draw)
    monkeypatch.setattr(zone_seed, "compute_content_bottom", _empty_board)

    n = await zone_seed.seed_zones_for_sub_phase(uuid4(), "1.1a")
    assert n == 1
    assert drawn == ["icebreaker_zone"]


async def test_seed_idempotent_when_already_registered(monkeypatch):
    drawn: list[str] = []

    async def _registered(*args, **kwargs):
        return True

    async def _fake_draw(project_id, zone_id, **kwargs):
        drawn.append(zone_id)
        return {"success": True}

    monkeypatch.setattr(zone_seed, "is_zone_registered", _registered)
    monkeypatch.setattr(zone_seed, "tool_draw_zone", _fake_draw)

    n = await zone_seed.seed_zones_for_sub_phase(uuid4(), "1.1a")
    assert n == 0
    assert drawn == []


async def test_seed_zoneless_sub_phase_draws_nothing(monkeypatch):
    drawn: list[str] = []

    async def _not_registered(*args, **kwargs):
        return False

    async def _fake_draw(project_id, zone_id, **kwargs):
        drawn.append(zone_id)
        return {"success": True}

    monkeypatch.setattr(zone_seed, "is_zone_registered", _not_registered)
    monkeypatch.setattr(zone_seed, "tool_draw_zone", _fake_draw)

    # "1.4" is offline with zones=()
    n = await zone_seed.seed_zones_for_sub_phase(uuid4(), "1.4")
    assert n == 0
    assert drawn == []


async def test_seed_unknown_sub_phase_is_safe(monkeypatch):
    async def _fake_draw(project_id, zone_id, **kwargs):
        raise AssertionError("should not draw for unknown sub_phase")

    monkeypatch.setattr(zone_seed, "tool_draw_zone", _fake_draw)
    n = await zone_seed.seed_zones_for_sub_phase(uuid4(), "9.9")
    assert n == 0
