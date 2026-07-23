"""Unit tests for app.agents.micro_phase_scoring（spec 04-05 v4.26，Phase 42 C1）.

新 6 桶（0.0 不計分／1.1／1.2／2.1／2.2／2.3）的規則評分 proxy 測試。
"""
from __future__ import annotations

import pytest

from app.agents.micro_phase_scoring import compute_micro_phase_quantitative

# ---------------------------------------------------------------------------
# Shared fixtures / factories
# ---------------------------------------------------------------------------

# Phase 42 C1：可計分桶（0.0 暖場不經本模組；舊 1.3 隨 Persona 刪除）。
ALL_PHASES = ["1.1", "1.2", "2.1", "2.2", "2.3"]


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
# 1. All scoring buckets return 0-100 with empty data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id", ALL_PHASES)
@pytest.mark.asyncio
async def test_empty_data_returns_valid_range(phase_id: str) -> None:
    """All phases must return a float in [0, 100] even with empty inputs."""
    score = await compute_micro_phase_quantitative(phase_id, _empty_canvas(), [], [])
    assert 0.0 <= score <= 100.0


@pytest.mark.asyncio
async def test_removed_1_3_falls_back_to_50() -> None:
    """舊 1.3（Persona）scorer 已刪除——未知桶走 50.0 fallback。"""
    score = await compute_micro_phase_quantitative("1.3", _empty_canvas(), [], [])
    assert score == 50.0


# ---------------------------------------------------------------------------
# 2. _score_1_1：利害關係人牆＋群數＋高/中/低標記
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_1_1_high_score() -> None:
    """8 張便條、3 群、每群高/中/低標記、席位覆蓋＋聊天 → 高分。"""
    seats = [_make_seat("alice"), _make_seat("bob"), _make_seat("charlie")]
    notes = [
        _make_note(f"n{i}", content=name, author=author)
        for i, (name, author) in enumerate([
            ("超市收銀員", "alice"), ("店長", "bob"), ("常客", "charlie"),
            ("補貨人員", "alice"), ("外送員", "bob"), ("清潔人員", "charlie"),
            ("學生客人", "alice"), ("家長", "bob"),
        ])
    ]
    notes += [
        _make_note("l1", content="高", author="alice"),
        _make_note("l2", content="中", author="bob"),
        _make_note("l3", content="低", author="charlie"),
    ]
    groups = [
        _make_group("店內人員", ["n0", "n1", "n3"]),
        _make_group("客人", ["n2", "n6", "n7"]),
        _make_group("外部", ["n4", "n5"]),
    ]
    canvas = {"notes": notes, "groups": groups, "ungrouped": [], "total_notes": 11}
    chat = _make_chat(["大家好", "我先列", "收銀員一定有關", "同意", "繼續"])
    score = await compute_micro_phase_quantitative("1.1", canvas, chat, seats)
    assert score >= 70.0


@pytest.mark.asyncio
async def test_score_1_1_low_score_no_notes() -> None:
    """No notes, no chat → low score."""
    score = await compute_micro_phase_quantitative("1.1", _empty_canvas(), [], [])
    assert score < 40.0


# ---------------------------------------------------------------------------
# 3. _score_1_2：痛點張數（長文字 proxy）＋群覆蓋
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_1_2_high_score() -> None:
    seats = [_make_seat("alice"), _make_seat("bob")]
    notes = [
        _make_note(f"p{i}", content=f"結帳那一刻才想起袋子放在家裡，第 {i} 種情況", author="alice")
        for i in range(6)
    ]
    groups = [
        _make_group("客人", ["p0", "p1", "p2"]),
        _make_group("店員", ["p3", "p4", "p5"]),
    ]
    canvas = {"notes": notes, "groups": groups, "ungrouped": [], "total_notes": 6}
    chat = _make_chat([f"訊息{i}" for i in range(8)])
    score = await compute_micro_phase_quantitative("1.2", canvas, chat, seats)
    assert score >= 60.0


@pytest.mark.asyncio
async def test_score_1_2_short_notes_dont_count_as_pain() -> None:
    """短文字（名字/標籤）不算痛點 proxy。"""
    notes = [_make_note(f"s{i}", content="店員") for i in range(6)]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 6}
    score = await compute_micro_phase_quantitative("1.2", canvas, [], [])
    # 痛點 35% 與群覆蓋 25% 都 0 → 低分（hard minimum 也壓 30）
    assert score <= 30.0


# ---------------------------------------------------------------------------
# 4. _score_2_1：主題群 ≥3＋每群掛載＋拖＋說
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_2_1_high_score() -> None:
    notes = [_make_note(f"t{i}", content=f"痛點 {i}") for i in range(6)]
    groups = [
        _make_group("出門前就忘了帶", ["t0", "t1"]),
        _make_group("結帳當下才想到", ["t2", "t3"]),
        _make_group("袋子不好帶在身上", ["t4", "t5"]),
    ]
    canvas = {"notes": notes, "groups": groups, "ungrouped": [], "total_notes": 6}
    chat = _make_chat(["這兩張同一件事", "我搬這張", "因為都在講時機"])
    score = await compute_micro_phase_quantitative("2.1", canvas, chat, [])
    assert score >= 75.0


@pytest.mark.asyncio
async def test_score_2_1_no_groups_low() -> None:
    score = await compute_micro_phase_quantitative("2.1", _empty_canvas(), [], [])
    assert score == 0.0


# ---------------------------------------------------------------------------
# 5. _score_2_2：問題定義句型＋追問/盤點訊號
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_2_2_high_score() -> None:
    seats = [_make_seat("alice")]
    ps = (
        "對於通勤族而言，在結帳時，他常遇到想不起袋子的情況，"
        "因為腦子還掛在工作上，因此需要更顯眼的提醒。"
    )
    notes = [_make_note(f"ps{i}", content=ps, author="alice") for i in range(3)]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 3}
    chat = _make_chat(["為什麼會這樣？", "市面上已經有人做提醒了", "根本原因是時機"])
    score = await compute_micro_phase_quantitative("2.2", canvas, chat, seats)
    assert score >= 80.0


@pytest.mark.asyncio
async def test_score_2_2_no_statements_low() -> None:
    canvas = {"notes": [_make_note("x", content="雜訊")], "groups": [],
              "ungrouped": [], "total_notes": 1}
    score = await compute_micro_phase_quantitative("2.2", canvas, [], [])
    assert score < 30.0


# ---------------------------------------------------------------------------
# 6. _score_2_3：準則＋設計題目＋收斂/共識訊號
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_2_3_high_score() -> None:
    notes = [
        _make_note("c1", content="準則：影響範圍｜衡量方式：每天有多少人遇到"),
        _make_note("c2", content="準則：容易開始｜衡量方式：第一步要花多少力氣"),
        _make_note("q1", content="我們可以怎麼讓袋子在出門那一刻自己出現在手邊？"),
    ]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 3}
    chat = _make_chat(["我選這張", "搬進選定區", "同意，就這個"])
    score = await compute_micro_phase_quantitative("2.3", canvas, chat, [])
    assert score >= 85.0


@pytest.mark.asyncio
async def test_score_2_3_empty_low() -> None:
    score = await compute_micro_phase_quantitative("2.3", _empty_canvas(), [], [])
    assert score == 0.0


# ---------------------------------------------------------------------------
# 7. Hard minimums／all-AI fallback／unknown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hard_minimum_caps_human_room() -> None:
    """真人房：1.1 便條數低於地板（3）→ 分數壓 30。"""
    seats = [{"agent_id": "alice", "type": "human"}]
    notes = [_make_note("n1", content="超市收銀員", author="alice")]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 1}
    chat = _make_chat([f"訊息{i}" for i in range(10)])
    score = await compute_micro_phase_quantitative("1.1", canvas, chat, seats)
    assert score <= 30.0


@pytest.mark.asyncio
async def test_all_ai_fallback_floor() -> None:
    """全 AI 房無 tldraw groups → note+chat 活動量地板，不會卡 0。"""
    seats = [{"agent_id": "crew_1", "type": "ai"}]
    notes = [_make_note(f"n{i}", content=f"具體的卡住情況描述 {i}", author="crew_1")
             for i in range(10)]
    canvas = {"notes": notes, "groups": [], "ungrouped": [], "total_notes": 10}
    chat = _make_chat([f"訊息{i}" for i in range(10)], author="crew_1")
    score = await compute_micro_phase_quantitative("1.1", canvas, chat, seats)
    assert score >= 30.0


@pytest.mark.asyncio
async def test_unknown_phase_returns_50() -> None:
    score = await compute_micro_phase_quantitative("9.9", _empty_canvas(), [], [])
    assert score == 50.0
