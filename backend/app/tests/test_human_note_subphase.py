"""真人便條 sub_phase 衍生（timer 未啟用時前端送空 sub_phase → 後端用 project 權威值補上）。

修復：HumanNoteCreateSync 在 timer 未啟用時 timer 快照 current_sub_phase=null，便條送空
sub_phase；human_create_note 以 project.current_sub_phase 衍生，否則 agent 看不到真人便條。
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.projects.router import _resolve_project_sub_phase


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        res = MagicMock()
        res.first = MagicMock(return_value=self._row)
        return res


def _patch(monkeypatch, row):
    monkeypatch.setattr(
        "app.db.session.async_session_factory", lambda: _FakeSession(row)
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prefers_current_sub_phase(monkeypatch):
    _patch(monkeypatch, ("0.0a", "warmup"))
    assert await _resolve_project_sub_phase(uuid4()) == "0.0a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_falls_back_to_stage(monkeypatch):
    _patch(monkeypatch, (None, "warmup"))
    assert await _resolve_project_sub_phase(uuid4()) == "warmup"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strips_whitespace(monkeypatch):
    _patch(monkeypatch, ("  1.1a  ", None))
    assert await _resolve_project_sub_phase(uuid4()) == "1.1a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_row_returns_empty(monkeypatch):
    _patch(monkeypatch, None)
    assert await _resolve_project_sub_phase(uuid4()) == ""
