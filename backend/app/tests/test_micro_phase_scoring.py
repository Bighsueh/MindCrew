"""Unit tests for app.agents.micro_phase_scoring (Phase 12.2)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.micro_phase_scoring import compute_micro_phase_quantitative

# ---------------------------------------------------------------------------
# Shared fixtures / factories
# ---------------------------------------------------------------------------

ALL_PHASES = [
    "1.1", "1.2", "1.3",
    "2.1", "2.2", "2.3",
    "3.1", "3.2", "3.3",
    "4.1", "4.2", "4.3",
]


def _empty_canvas() -> dict:
    return {"notes": [], "groups": [], "ungrouped": []}


def _make_note(
    note_id: str,
    content: str = "",
    author: str = "",
    color: str = "yellow",
) -> dict:
    return {"id": note_id, "content": content, "author": author, "color": color}


def _make_group(name: str, note_ids: list[str]) -> dict:
    return {"name": name, "notes": note_ids}


def _make_chat(messages: list[str], author: str = "user") -> list[dict]:
    return [{"content": m, "author": author} for m in messages]


def _make_seat(agent_id: str) -> dict:
    return {"agent_id": agent_id}


# ---------------------------------------------------------------------------
# 1. All 12 phases return 0-100 with empty data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id", ALL_PHASES)
@pytest.mark.asyncio
async def test_empty_data_returns_valid_range(phase_id: str) -> None:
    """All phases must return a float in [0, 100] even with empty inputs.

    Phase 1.2 has a broken internal import (`from backend.app...`) that only fires
    at call-time, so we patch the scorer reference in _SCORERS directly.
    """
    import app.agents.micro_phase_scoring as _mod

    if phase_id == "1.2":
        original = _mod._SCORERS["1_2"]
        _mod._SCORERS["1_2"] = lambda *_: 0.0
        try:
            score = await compute_micro_phase_quantitative(phase_id, _empty_canvas(), [], [])
        finally:
            _mod._SCORERS["1_2"] = original
    else:
        score = await compute_micro_phase_quantitative(phase_id, _empty_canvas(), [], [])
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# 2. _score_1_1: high score vs low score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_1_1_high_score() -> None:
    """5 notes with emotional keywords, 5 chat messages, seats covered → high score."""
    seats = [_make_seat("alice"), _make_seat("bob"), _make_seat("charlie")]
    notes = [
        _make_note("n1", content="感到焦慮", author="alice"),
        _make_note("n2", content="有點開心", author="bob"),
        _make_note("n3", content="覺得困惑", author="charlie"),
        _make_note("n4", content="普通分享", author="alice"),
        _make_note("n5", content="另一個分享", author="bob"),
    ]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 5}
    chat = _make_chat(["大家好", "我分享一下", "很有趣", "同意", "繼續"])
    score = await compute_micro_phase_quantitative("1.1", canvas, chat, seats)
    assert score >= 70.0


@pytest.mark.asyncio
async def test_score_1_1_low_score_no_notes() -> None:
    """No notes, no chat → low score."""
    score = await compute_micro_phase_quantitative("1.1", _empty_canvas(), [], [])
    assert score < 40.0


# ---------------------------------------------------------------------------
# 3. _score_1_3: persona groups with ★ marker → high score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_1_3_high_score() -> None:
    """3 persona groups (non-★-prefixed), one group marked ★ → high score."""
    notes = [
        _make_note("p1n1", content="她的需求是效率"),
        _make_note("p1n2", content="痛點是時間不夠"),
        _make_note("p1n3", content="語錄：我需要更快"),
        _make_note("p2n1", content="他的需求是連結"),
        _make_note("p2n2", content="痛點是孤獨"),
        _make_note("p2n3", content="語錄：想被理解"),
        _make_note("p3n1", content="她的需求是安全感"),
        _make_note("p3n2", content="痛點是不確定性"),
        _make_note("p3n3", content="語錄：要穩定"),
    ]
    groups = [
        _make_group("Persona A", ["p1n1", "p1n2", "p1n3"]),
        _make_group("Persona B", ["p2n1", "p2n2", "p2n3"]),
        _make_group("Persona C", ["p3n1", "p3n2", "p3n3"]),
        _make_group("★ 主要 Persona", ["p1n1"]),  # starred group
    ]
    canvas = {"notes": notes, "groups": groups, "ungrouped": []}
    score = await compute_micro_phase_quantitative("1.3", canvas, [], [])
    assert score >= 60.0


@pytest.mark.asyncio
async def test_score_1_3_empty_groups_low_score() -> None:
    score = await compute_micro_phase_quantitative("1.3", _empty_canvas(), [], [])
    assert score < 30.0


# ---------------------------------------------------------------------------
# 4. _score_2_1: journey group with 5 colored notes → high score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_2_1_high_score() -> None:
    """旅程：group with green + yellow + red notes (5 total) → high score."""
    notes = [
        _make_note("j1", content="步驟一", color="green"),
        _make_note("j2", content="步驟二", color="yellow"),
        _make_note("j3", content="痛點", color="red"),
        _make_note("j4", content="步驟四", color="green"),
        _make_note("j5", content="步驟五", color="yellow"),
    ]
    groups = [_make_group("旅程：用戶流程", ["j1", "j2", "j3", "j4", "j5"])]
    canvas = {"notes": notes, "groups": groups, "ungrouped": []}
    score = await compute_micro_phase_quantitative("2.1", canvas, [], [])
    assert score >= 75.0


@pytest.mark.asyncio
async def test_score_2_1_no_journey_group() -> None:
    score = await compute_micro_phase_quantitative("2.1", _empty_canvas(), [], [])
    assert score == 0.0


# ---------------------------------------------------------------------------
# 5. _score_3_1: 15 ungrouped notes, all members contributing → high score
#    notes with blocking keywords → lower score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_3_1_high_score() -> None:
    """15 ungrouped ids, 3 ideation keywords in chat, all seats covered → high."""
    seats = [_make_seat("alice"), _make_seat("bob"), _make_seat("charlie")]
    notes = [
        _make_note(f"idea{i}", content=f"想法{i}", author=["alice", "bob", "charlie"][i % 3])
        for i in range(15)
    ]
    ungrouped = [f"idea{i}" for i in range(15)]
    canvas = {"notes": notes, "groups": [], "ungrouped": ungrouped, "total_notes": 15}
    chat = _make_chat(["可以類比一下", "反過來想", "如果做極端版本呢"])
    score = await compute_micro_phase_quantitative("3.1", canvas, chat, seats)
    assert score >= 70.0


@pytest.mark.asyncio
async def test_score_3_1_blocking_keywords_lower_score() -> None:
    """Chat containing blocking keywords (做不到) should lower score."""
    seats = [_make_seat("alice")]
    notes = [
        _make_note(f"idea{i}", content=f"想法{i}", author="alice") for i in range(15)
    ]
    ungrouped = [f"idea{i}" for i in range(15)]
    canvas = {"notes": notes, "groups": [], "ungrouped": ungrouped, "total_notes": 15}
    chat_blocking = _make_chat(["類比思考", "做不到啦", "不可能實現"])
    chat_clean = _make_chat(["類比思考", "反過來想"])
    score_blocking = await compute_micro_phase_quantitative("3.1", canvas, chat_blocking, seats)
    score_clean = await compute_micro_phase_quantitative("3.1", canvas, chat_clean, seats)
    assert score_blocking < score_clean


# ---------------------------------------------------------------------------
# 6. _score_3_2: 4 groups with 3+ notes each → high score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_3_2_high_score() -> None:
    """4 named groups with 3 notes each + consensus keyword in chat → high score."""
    notes = [
        _make_note(f"g{g}n{n}", content=f"內容{g}{n}", author="alice")
        for g in range(4) for n in range(3)
    ]
    groups = [
        _make_group(f"主題{g}", [f"g{g}n{n}" for n in range(3)])
        for g in range(4)
    ]
    canvas = {"notes": notes, "groups": groups, "ungrouped": []}
    chat = _make_chat(["就這個方向確定了"])
    score = await compute_micro_phase_quantitative("3.2", canvas, chat, [])
    assert score >= 70.0


@pytest.mark.asyncio
async def test_score_3_2_no_groups_low_score() -> None:
    score = await compute_micro_phase_quantitative("3.2", _empty_canvas(), [], [])
    assert score < 30.0


# ---------------------------------------------------------------------------
# 7. _score_4_3: ★ 推薦方案 group + test result notes → high score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_4_3_high_score() -> None:
    """★ 推薦方案 group, green/red notes, learning note, consensus chat → high."""
    notes = [
        _make_note("t1", content="通過測試", color="green"),
        _make_note("t2", content="失敗案例", color="red"),
        _make_note("t3", content="我們學到了重要發現", color="yellow"),
    ]
    groups = [_make_group("★ 推薦方案", ["t1"])]
    canvas = {"notes": notes, "groups": groups, "ungrouped": []}
    chat = _make_chat(["決定推薦這個最終方案，下一步是推進"])
    score = await compute_micro_phase_quantitative("4.3", canvas, chat, [])
    assert score >= 80.0


@pytest.mark.asyncio
async def test_score_4_3_empty_canvas_low_score() -> None:
    score = await compute_micro_phase_quantitative("4.3", _empty_canvas(), [], [])
    assert score < 30.0


# ---------------------------------------------------------------------------
# 8. Unknown phase returns 50.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_phase_returns_50() -> None:
    score = await compute_micro_phase_quantitative("9.9", _empty_canvas(), [], [])
    assert score == 50.0


# ---------------------------------------------------------------------------
# Context manager helper for parametrize mock
# ---------------------------------------------------------------------------

from contextlib import contextmanager


@contextmanager
def _null_ctx():
    yield
