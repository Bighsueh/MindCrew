"""canvas_ops 寫入後失效空間 full-state 快取（Phase 42 D1d Bug①）。

根因：analyzer.get_full_state 有 3s Redis 快取；canvas_ops 直接寫 sidecar 的呼叫端
（force_close 搬便條、動畫 stagger…）繞過 act_canvas 的失效點 → 下一次感知/閘檢查讀到
搬移前舊快照（live 2026-06-15：force_close 搬 PS 後 2.7 配對閘看不到→永遠 thrash）。
修法：所有 mutating writer 成功後 lazy-invalidate full-state 快取。

mock sidecar HTTP client（沿用 test_stagger_floor.py 風格）＋spy invalidate。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.bridge import canvas_ops as cops


def _resp(payload=None, status=200):
    return SimpleNamespace(
        status_code=status,
        raise_for_status=lambda: None,
        json=lambda: (payload if payload is not None else {"id": "note_new"}),
    )


@pytest.fixture
def sidecar_ok(monkeypatch):
    """所有 verb（post/patch/delete）回 200 成功。"""
    async def _post(url, json=None):
        return _resp()

    async def _patch(url, json=None):
        return _resp()

    async def _delete(url):
        return _resp()

    monkeypatch.setattr(
        cops, "_get_client",
        lambda: SimpleNamespace(post=_post, patch=_patch, delete=_delete),
    )


@pytest.fixture
def spy_invalidate(monkeypatch):
    """capture invalidate_full_state_cache；patch lazy-import 來源 analyzer 模組。"""
    inv = AsyncMock()
    analyzer = SimpleNamespace(invalidate_full_state_cache=inv)
    monkeypatch.setattr(
        "app.canvas.analyzer.get_spatial_analyzer", lambda: analyzer
    )
    return inv


_UPD = [{"id": "n1", "x": 10.0, "y": 20.0}]


# ── 核心三 writer（Bug① 直接相關：force_close 用 batch_update＋add_note；動畫用 stagger）──


async def test_batch_update_coordinates_invalidates(sidecar_ok, spy_invalidate):
    pid = uuid4()
    ok = await cops.canvas_ops.batch_update_coordinates(
        pid, _UPD, moved_by="agent_supervisor"
    )
    assert ok is True
    spy_invalidate.assert_awaited_once_with(pid)


async def test_add_note_invalidates(sidecar_ok, spy_invalidate):
    pid = uuid4()
    nid = await cops.canvas_ops.add_note(pid, content="一則便條")
    assert nid == "note_new"
    spy_invalidate.assert_awaited_once_with(pid)


async def test_staggered_update_coordinates_invalidates(sidecar_ok, spy_invalidate):
    pid = uuid4()
    ok = await cops.canvas_ops.staggered_update_coordinates(pid, _UPD)
    assert ok is True
    spy_invalidate.assert_awaited_once_with(pid)


# ── 代表性 patch/delete writer（涵蓋 success-after-404-guard 放置點正確）──


async def test_move_note_invalidates(sidecar_ok, spy_invalidate):
    pid = uuid4()
    ok = await cops.canvas_ops.move_note(pid, "n1", target_group="g1")
    assert ok is True
    spy_invalidate.assert_awaited_once_with(pid)


async def test_delete_note_invalidates(sidecar_ok, spy_invalidate):
    pid = uuid4()
    ok = await cops.canvas_ops.delete_note(pid, "n1")
    assert ok is True
    spy_invalidate.assert_awaited_once_with(pid)


# ── 邊界：空批早退不失效、404/失敗不失效（語意：只有真的改了才 bust）──


async def test_empty_batch_does_not_invalidate(sidecar_ok, spy_invalidate):
    pid = uuid4()
    await cops.canvas_ops.batch_update_coordinates(pid, [])
    spy_invalidate.assert_not_awaited()


async def test_failed_write_does_not_invalidate(monkeypatch, spy_invalidate):
    """sidecar 寫入丟例外 → 回 False、不失效（沒改成功就不必 bust）。"""
    async def _boom(url, json=None):
        raise RuntimeError("sidecar down")

    monkeypatch.setattr(cops, "_get_client", lambda: SimpleNamespace(post=_boom))
    pid = uuid4()
    ok = await cops.canvas_ops.batch_update_coordinates(pid, _UPD)
    assert ok is False
    spy_invalidate.assert_not_awaited()


async def test_move_note_404_does_not_invalidate(monkeypatch, spy_invalidate):
    """note 不存在（404）→ 沒搬動任何東西，不失效。"""
    async def _post(url, json=None):
        return _resp(status=404)

    monkeypatch.setattr(cops, "_get_client", lambda: SimpleNamespace(post=_post))
    pid = uuid4()
    ok = await cops.canvas_ops.move_note(pid, "missing", target_group="g1")
    assert ok is False
    spy_invalidate.assert_not_awaited()
