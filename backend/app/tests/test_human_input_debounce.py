"""B1（多訊息連發）：_round_lock_human_input 的 latest-wins debounce。

連發 3 則 → 只有最後一則（human_last_msg_ts == 自己 arrival_ts）跑 process_group_input；
被取代的中間則（latest > arrival）跳過。mock redis + process_group_input，debounce 窗歸零。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.ws import chat_ws


class _FakeRedis:
    def __init__(self, latest: str | None, burst: list[str] | None = None):
        self._latest = latest
        self._burst = burst or []

    async def get(self, key):
        return self._latest

    async def lrange(self, key, start, end):
        return list(self._burst)

    async def delete(self, key):
        self._burst = []

    async def aclose(self):
        pass


def _patch(monkeypatch, latest: str | None, burst: list[str] | None = None):
    monkeypatch.setattr(chat_ws, "_HUMAN_INPUT_DEBOUNCE_SECONDS", 0.0)
    monkeypatch.setattr(
        chat_ws.aioredis, "from_url", lambda *a, **k: _FakeRedis(latest, burst)
    )
    called: list = []

    async def _fake_pgi(project_id, user_id, text, input_type, sub_phase):
        called.append(text)  # 紀錄送去檢核的內容
        return True

    monkeypatch.setattr(
        "app.agents.human_input_check.process_group_input", _fake_pgi
    )
    return called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_debounce_skips_superseded_message(monkeypatch) -> None:
    arrival = 100.0
    called = _patch(monkeypatch, str(arrival + 5.0))  # 有更新訊息 → 取代
    await chat_ws._round_lock_human_input(uuid4(), uuid4(), "濾往", "0.0a", arrival)
    assert called == []  # 被取代 → 不處理


@pytest.mark.unit
@pytest.mark.asyncio
async def test_latest_coalesces_whole_burst(monkeypatch) -> None:
    """最後一則 → 把整波連發的內容合併送檢核（一段話拆 3 句也驗得過）。"""
    arrival = 100.0
    called = _patch(
        monkeypatch,
        str(arrival),  # latest == 自己 → 我是最後一則
        burst=["我覺得", "可以做一個", "防水的手機殼"],
    )
    await chat_ws._round_lock_human_input(
        uuid4(), uuid4(), "防水的手機殼", "0.0a", arrival
    )
    assert len(called) == 1
    # 送檢核的是合併後的完整內容，不只是最後一截
    assert called[0] == "我覺得 可以做一個 防水的手機殼"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_latest_falls_back_to_own_content_when_burst_empty(monkeypatch) -> None:
    arrival = 100.0
    called = _patch(monkeypatch, str(arrival), burst=[])  # 累積讀不到 → 用本則
    await chat_ws._round_lock_human_input(uuid4(), uuid4(), "濾網", "0.0a", arrival)
    assert called == ["濾網"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_arrival_ts_processes_immediately(monkeypatch) -> None:
    # arrival_ts=None（如 note 端點路徑）→ 不 debounce、不合併、直接用本則。
    called = _patch(monkeypatch, "999999", burst=["不該被讀到"])
    await chat_ws._round_lock_human_input(uuid4(), uuid4(), "x", "0.0a", None)
    assert called == ["x"]
