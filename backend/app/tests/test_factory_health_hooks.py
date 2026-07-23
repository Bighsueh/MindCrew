"""factory.chat_completion_stream 的 health_monitor 接點測試（Phase 42 D5 / G14）。

回歸守衛（code-review 2026-06-14 抓到）：串流路徑原本漏接 health_monitor →
reactive 計數無法經串流成功歸零、串流耗盡不計失敗。本測試鎖定：
  * 串流成功 → record_success（spec 20 §13.2「任一次成功歸零」）
  * 串流失敗（單 provider、無 mid-stream fallback＝終局）→ record_exhaustion
  * 無可用 provider（primary_for_streaming None）→ record_exhaustion ＋ RuntimeError
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.llm import factory as factory_mod
from app.llm.factory import LLMService


@pytest.fixture
def _hooks(monkeypatch):
    success = AsyncMock()
    exhaustion = AsyncMock()
    monkeypatch.setattr(factory_mod.health_monitor, "record_success", success)
    monkeypatch.setattr(factory_mod.health_monitor, "record_exhaustion", exhaustion)
    # 隔離 DB / cooldown 副作用
    monkeypatch.setattr(factory_mod.log_service, "record", MagicMock())
    monkeypatch.setattr(factory_mod.ProviderRouter, "mark_success", MagicMock())
    monkeypatch.setattr(factory_mod.ProviderRouter, "mark_failure", MagicMock())
    return SimpleNamespace(success=success, exhaustion=exhaustion)


def _fake_entry(*, raises: bool = False):
    async def _stream(messages, temperature=0.7, max_tokens=1024):
        if raises:
            raise RuntimeError("stream boom")
        for ch in ["a", "b", "c"]:
            yield ch

    inst = SimpleNamespace(chat_completion_stream=_stream)
    row = SimpleNamespace(id=uuid4(), name="p1", tier=1)
    return SimpleNamespace(row=row, instance=inst)


def _patch_primary(monkeypatch, entry):
    async def _primary(_cls):
        return entry

    monkeypatch.setattr(factory_mod.ProviderRouter, "primary_for_streaming", _primary)


async def test_stream_success_records_success(monkeypatch, _hooks):
    _patch_primary(monkeypatch, _fake_entry(raises=False))
    svc = LLMService()
    chunks = [
        c
        async for c in svc.chat_completion_stream(
            [{"role": "user", "content": "hi"}], owning_user_id=uuid4()
        )
    ]
    assert chunks == ["a", "b", "c"]
    _hooks.success.assert_awaited_once()
    _hooks.exhaustion.assert_not_awaited()


async def test_stream_failure_records_exhaustion(monkeypatch, _hooks):
    _patch_primary(monkeypatch, _fake_entry(raises=True))
    svc = LLMService()
    with pytest.raises(RuntimeError):
        async for _ in svc.chat_completion_stream(
            [{"role": "user", "content": "hi"}], owning_user_id=uuid4()
        ):
            pass
    _hooks.exhaustion.assert_awaited_once()
    _hooks.success.assert_not_awaited()


async def test_stream_no_provider_records_exhaustion(monkeypatch, _hooks):
    _patch_primary(monkeypatch, None)
    svc = LLMService()
    with pytest.raises(RuntimeError):
        async for _ in svc.chat_completion_stream(
            [{"role": "user", "content": "hi"}], owning_user_id=uuid4()
        ):
            pass
    _hooks.exhaustion.assert_awaited_once()
    _hooks.success.assert_not_awaited()
