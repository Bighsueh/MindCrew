"""staggered_update_coordinates 的 stagger 下限測試（Phase 42 D1b / spec 12 §3.3 v4.1）。

下限 400ms（舊預設 150 廢除——低於使用者跟不上「動哪幾張」）；<400 一律夾到 400。
mock HTTP client 捕捉送往 sidecar 的 payload。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.bridge import canvas_ops as cops


@pytest.fixture
def captured(monkeypatch):
    posted: dict = {}

    async def _post(url, json=None):
        posted["url"] = url
        posted["json"] = json
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(cops, "_get_client", lambda: SimpleNamespace(post=_post))
    return posted


_UPD = [{"id": "n1", "x": 0, "y": 0}]


async def test_stagger_default_is_400(captured):
    await cops.canvas_ops.staggered_update_coordinates(uuid4(), _UPD)
    assert captured["json"]["stagger_ms"] == 400


async def test_stagger_below_floor_clamped(captured):
    await cops.canvas_ops.staggered_update_coordinates(uuid4(), _UPD, stagger_ms=150)
    assert captured["json"]["stagger_ms"] == 400


async def test_stagger_above_floor_preserved(captured):
    await cops.canvas_ops.staggered_update_coordinates(uuid4(), _UPD, stagger_ms=600)
    assert captured["json"]["stagger_ms"] == 600
