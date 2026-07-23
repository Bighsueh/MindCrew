"""使用者導向訊號 action（Phase 42 A3，WP7）。

set_user_task / note_highlight handlers＋user_task_state＋confirm 白名單轉正。
Redis 路徑用真 Redis（settings.REDIS_URL，唯一 project_id 隔離）；事件 publish
monkeypatch 捕捉。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from unittest.mock import AsyncMock

from app.agents import act_signals, user_task_state
from app.agents.act import ActEngine
from app.agents.human_input_check import confirm_context_active
from app.events.types import AgentTypingEvent, NoteHighlightEvent, UserTaskEvent

# ---------------------------------------------------------------------------
# 事件 payload（spec 06 §3.1）
# ---------------------------------------------------------------------------


def test_user_task_event_payload():
    e = UserTaskEvent(
        project_id=uuid4(),
        task_text="貼一張只寫名字的利害關係人便條",
        sub_phase="1.1b",
        action_kind="note",
        anchor_note_ids=["shape:note_1_2"],
    )
    d = e.to_dict()
    assert d["type"] == "user_task"
    p = d["payload"]
    assert p["task_text"].startswith("貼一張") and p["sub_phase"] == "1.1b"
    assert p["action_kind"] == "note" and p["anchor_note_ids"] == ["shape:note_1_2"]
    assert "chat_id" not in p  # 廣播全房


def test_user_task_event_null_clears():
    e = UserTaskEvent(
        project_id=uuid4(), task_text=None, sub_phase="1.1b", action_kind="chat"
    )
    assert e.to_dict()["payload"]["task_text"] is None


def test_note_highlight_event_payload():
    e = NoteHighlightEvent(
        project_id=uuid4(), note_ids=["a", "b"], by_seat="supervisor", ttl=12
    )
    d = e.to_dict()
    assert d["type"] == "note_highlight"
    assert d["payload"]["note_ids"] == ["a", "b"]
    assert d["payload"]["by_seat"] == "supervisor" and d["payload"]["ttl"] == 12


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------


@pytest.fixture
def published(monkeypatch):
    events: list = []

    async def fake_publish(event):
        events.append(event.to_dict())

    from app.events import bus as bus_module

    monkeypatch.setattr(bus_module.event_bus, "publish", fake_publish)
    return events


@pytest.mark.asyncio
async def test_set_user_task_publishes_and_stores(published):
    pid = uuid4()
    await act_signals.execute_set_user_task(
        project_id=pid,
        action={"type": "set_user_task", "task_text": "回「可以」兩個字",
                "action_kind": "confirm"},
        sub_phase="2.7",
    )
    assert [e["type"] for e in published] == ["user_task"]
    assert published[0]["payload"]["action_kind"] == "confirm"
    stored = await user_task_state.get_current(pid)
    assert stored == {
        "task_text": "回「可以」兩個字", "sub_phase": "2.7", "action_kind": "confirm",
    }
    await user_task_state.set_current(pid, task_text=None, sub_phase="2.7", action_kind="chat")


@pytest.mark.asyncio
async def test_set_user_task_null_clears_state(published):
    pid = uuid4()
    await act_signals.execute_set_user_task(
        project_id=pid,
        action={"task_text": "貼一張便條", "action_kind": "note"},
        sub_phase="1.1b",
    )
    assert await user_task_state.get_current(pid) is not None
    await act_signals.execute_set_user_task(
        project_id=pid, action={"task_text": None}, sub_phase="1.1b"
    )
    assert await user_task_state.get_current(pid) is None
    assert published[-1]["payload"]["task_text"] is None  # 清除事件照發（前端收掉 banner）


@pytest.mark.asyncio
async def test_set_user_task_invalid_kind_falls_back_to_chat(published):
    pid = uuid4()
    await act_signals.execute_set_user_task(
        project_id=pid,
        action={"task_text": "說一個想法", "action_kind": "weird"},
        sub_phase="1.1a",
    )
    assert published[0]["payload"]["action_kind"] == "chat"
    await user_task_state.set_current(pid, task_text=None, sub_phase="1.1a", action_kind="chat")


@pytest.mark.asyncio
async def test_note_highlight_publishes_with_ttl(published):
    await act_signals.execute_note_highlight(
        project_id=uuid4(),
        action={"note_ids": ["shape:note_1", " shape:note_2 ", ""]},
        seat_role="supervisor",
    )
    assert [e["type"] for e in published] == ["note_highlight"]
    p = published[0]["payload"]
    assert p["note_ids"] == ["shape:note_1", "shape:note_2"]  # 去空白、濾空值
    assert p["ttl"] == act_signals.NOTE_HIGHLIGHT_TTL_SECONDS
    assert p["by_seat"] == "supervisor"


@pytest.mark.asyncio
async def test_note_highlight_empty_or_invalid_noop(published):
    await act_signals.execute_note_highlight(
        project_id=uuid4(), action={"note_ids": []}, seat_role="supervisor"
    )
    await act_signals.execute_note_highlight(
        project_id=uuid4(), action={"note_ids": "not-a-list"}, seat_role="supervisor"
    )
    assert published == []


@pytest.mark.asyncio
async def test_note_highlight_caps_id_count(published):
    await act_signals.execute_note_highlight(
        project_id=uuid4(),
        action={"note_ids": [f"n{i}" for i in range(20)]},
        seat_role="supervisor",
    )
    assert len(published[0]["payload"]["note_ids"]) == act_signals._MAX_HIGHLIGHT_IDS


# ---------------------------------------------------------------------------
# confirm 白名單轉正（spec 20 §12.4；A2 佔位結束）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_context_live_same_sub_phase(published):
    pid = uuid4()
    try:
        await act_signals.execute_set_user_task(
            project_id=pid,
            action={"task_text": "可以就回「可以」", "action_kind": "confirm"},
            sub_phase="2.7",
        )
        assert await confirm_context_active(pid, "2.7") is True
        # 換關即失效（Flow 12 生命週期）
        assert await confirm_context_active(pid, "1.1a") is False
    finally:
        await user_task_state.set_current(pid, task_text=None, sub_phase="2.7", action_kind="chat")


@pytest.mark.asyncio
async def test_confirm_context_inactive_for_non_confirm_task(published):
    pid = uuid4()
    try:
        await act_signals.execute_set_user_task(
            project_id=pid,
            action={"task_text": "貼一張便條", "action_kind": "note"},
            sub_phase="1.1b",
        )
        assert await confirm_context_active(pid, "1.1b") is False
    finally:
        await user_task_state.set_current(pid, task_text=None, sub_phase="1.1b", action_kind="chat")


@pytest.mark.asyncio
async def test_confirm_context_inactive_without_task():
    assert await confirm_context_active(uuid4(), "2.7") is False


# ---------------------------------------------------------------------------
# Phase 42 D2（WP9 #9）：agent_typing 事件＋act 發 start/stop
# ---------------------------------------------------------------------------


def test_agent_typing_event_payload():
    e = AgentTypingEvent(
        project_id=uuid4(), seat_id="crew_1", display_name="小明",
        kind="chat", state="start",
    )
    d = e.to_dict()
    assert d["type"] == "agent_typing"
    p = d["payload"]
    assert p["seat_id"] == "crew_1" and p["display_name"] == "小明"
    assert p["kind"] == "chat" and p["state"] == "start"
    assert "chat_id" not in p  # 群組廣播（個人 channel 不發）


@pytest.mark.asyncio
async def test_emit_agent_typing_publishes(published):
    pid = uuid4()
    await act_signals.emit_agent_typing(
        project_id=pid, seat_id="crew_2", display_name="小華",
        kind="canvas", state="start",
    )
    assert [e["type"] for e in published] == ["agent_typing"]
    p = published[0]["payload"]
    assert p["kind"] == "canvas" and p["state"] == "start" and p["seat_id"] == "crew_2"


@pytest.mark.asyncio
async def test_emit_agent_typing_best_effort_swallows(monkeypatch):
    """publish 拋錯時 emit_agent_typing 不可炸開（best-effort）。"""
    from app.events import bus as bus_module

    async def boom(_event):
        raise RuntimeError("redis down")

    monkeypatch.setattr(bus_module.event_bus, "publish", boom)
    # 不應拋出
    await act_signals.emit_agent_typing(
        project_id=uuid4(), seat_id="crew_1", display_name="小明",
        kind="chat", state="stop",
    )


def _engine(seat_role: str = "crew_1", name: str = "小明") -> ActEngine:
    return ActEngine(
        project_id=uuid4(), agent_id="agent_crew_1", seat_role=seat_role,
        agent_name=name, is_supervisor=False,
    )


@pytest.mark.asyncio
async def test_execute_single_chat_emits_typing_start_then_stop(published, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(engine, "_execute_chat_message", AsyncMock())

    await engine._execute_single({"type": "chat_message", "content": "嗨大家"}, "discover")

    typing = [e["payload"] for e in published if e["type"] == "agent_typing"]
    assert [(t["kind"], t["state"]) for t in typing] == [("chat", "start"), ("chat", "stop")]
    assert all(t["seat_id"] == "crew_1" and t["display_name"] == "小明" for t in typing)


@pytest.mark.asyncio
async def test_execute_single_chat_emits_stop_even_on_exception(published, monkeypatch):
    """_execute_chat_message 拋錯時 stop 仍由 try/finally 發出（前端不卡 typing 列）。"""
    engine = _engine()
    monkeypatch.setattr(
        engine, "_execute_chat_message", AsyncMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        await engine._execute_single({"type": "chat_message", "content": "x"}, "discover")

    states = [e["payload"]["state"] for e in published if e["type"] == "agent_typing"]
    assert states == ["start", "stop"]


@pytest.mark.asyncio
async def test_execute_single_canvas_emits_typing(published, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(
        "app.agents.act_canvas.execute_canvas_tool", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(engine, "_explain_canvas_rejection", AsyncMock())

    await engine._execute_single(
        {"type": "create_note", "content": "一張便條"}, "discover", sub_phase="1.1a"
    )

    typing = [e["payload"] for e in published if e["type"] == "agent_typing"]
    assert [(t["kind"], t["state"]) for t in typing] == [("canvas", "start"), ("canvas", "stop")]


@pytest.mark.asyncio
async def test_confirm_unlocks_round_end_to_end(published, monkeypatch):
    """confirm 任務 live 後，「可以」過白名單並以 chat 型解鎖（chat/confirm 互通）。"""
    from app.agents import human_input_check as hic
    from app.agents import round_lock

    pid = uuid4()
    registered: list = []

    async def fake_register(p, sub, t):
        registered.append((sub, t))
        return True

    monkeypatch.setattr(round_lock, "register_human_input", fake_register)
    try:
        await act_signals.execute_set_user_task(
            project_id=pid,
            action={"task_text": "可以就回「可以」", "action_kind": "confirm"},
            sub_phase="2.7",
        )
        completed = await hic.process_group_input(pid, uuid4(), "可以", "chat", sub_phase="2.7")
        assert completed is True
        assert registered == [("2.7", "chat")]
    finally:
        await user_task_state.set_current(pid, task_text=None, sub_phase="2.7", action_kind="chat")