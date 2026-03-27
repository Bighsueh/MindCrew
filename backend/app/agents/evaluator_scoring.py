"""Quantitative scoring functions for stage evaluation (spec §4.4).

Extracted from evaluator.py to keep each file under 500 lines.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone


def participant_coverage(canvas: dict, seats: list[dict]) -> float:
    """Percentage of seats with at least one contribution on canvas (0-100)."""
    if not seats:
        return 100.0
    notes: list[dict] = canvas.get("notes", [])
    authors = {n.get("author", "").split("(")[0].strip() for n in notes}
    seat_names: set[str] = set()
    for s in seats:
        seat_names.add(s.get("agent_id", s.get("user_name", s.get("role", ""))))
    if not seat_names:
        return 100.0
    covered = sum(1 for n in seat_names if any(n in a for a in authors))
    return min(100.0, covered / len(seat_names) * 100)


def _compute_slowdown_score(
    canvas: dict, window_seconds: float = 180.0,
) -> float:
    """Score 0-100 based on how much note creation has slowed down.

    Combines two signals:
    1. Time silence (60%): compare recent vs previous window note counts
    2. Content repetition (40%): CJK character overlap between note pairs
    """
    notes: list[dict] = canvas.get("notes", [])
    if not notes:
        return 0.0

    now = time.time()

    # --- Time-based component (60%) ---
    recent_count = 0
    prev_count = 0
    for n in notes:
        created = n.get("created_at")
        if created is None:
            continue
        # Support both float timestamps and ISO strings
        if isinstance(created, str):
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                created = dt.timestamp()
            except ValueError:
                continue
        age = now - created
        if age <= window_seconds:
            recent_count += 1
        elif age <= window_seconds * 2:
            prev_count += 1

    if prev_count == 0 and recent_count == 0:
        time_score = 0.0  # No data — not saturated
    elif prev_count == 0:
        time_score = 0.0  # Only recent notes — still active
    else:
        ratio = recent_count / prev_count
        time_score = max(0.0, min(100.0, (1 - ratio) * 100))

    # --- Content repetition component (40%) ---
    contents = [n.get("content", "") for n in notes if n.get("content")]
    rep_score = 0.0
    if len(contents) >= 2:
        # Extract CJK character sets per note
        char_sets = [
            set(c for c in text if "\u4e00" <= c <= "\u9fff")
            for text in contents
        ]
        pair_count = 0
        overlap_count = 0
        for i in range(len(char_sets)):
            if len(char_sets[i]) < 2:
                continue
            for j in range(i + 1, len(char_sets)):
                if len(char_sets[j]) < 2:
                    continue
                pair_count += 1
                overlap = len(char_sets[i] & char_sets[j])
                smaller = min(len(char_sets[i]), len(char_sets[j]))
                if smaller > 0 and overlap / smaller >= 0.5:
                    overlap_count += 1
        if pair_count > 0:
            rep_score = min(100.0, overlap_count / pair_count * 100)

    return time_score * 0.6 + rep_score * 0.4


def score_discover(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    total_notes = canvas.get("total_notes", 0)

    # Note count (30%): >= 25 = 100
    note_score = min(100.0, total_notes / 25 * 100)

    # Slowdown (20%): dynamic — time silence + content repetition
    slowdown_score = _compute_slowdown_score(canvas)

    # Participant coverage (25%)
    coverage_score = participant_coverage(canvas, seats)

    # Chat activity (15%): >= 20 = 100
    chat_score = min(100.0, len(chat) / 20 * 100)

    # Operation diversity (10%): notes > 0 and chat > 0 = 100
    diversity_score = 100.0 if total_notes > 0 and len(chat) > 0 else 0.0

    return (
        note_score * 0.30
        + slowdown_score * 0.20
        + coverage_score * 0.25
        + chat_score * 0.15
        + diversity_score * 0.10
    )


def score_define(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    total_notes = canvas.get("total_notes", 0)
    ungrouped = len(canvas.get("ungrouped", []))
    groups = canvas.get("groups", [])

    # Grouping completion (35%): ungrouped <= 20% = 100
    if total_notes > 0:
        ungrouped_ratio = ungrouped / total_notes
        group_complete_score = max(0.0, (1 - ungrouped_ratio / 0.2) * 100)
    else:
        group_complete_score = 0.0

    # Group count (20%): >= 3 = 100
    group_count_score = min(100.0, len(groups) / 3 * 100)

    # Move/group ops vs add ops (20%): use group count as proxy
    move_ratio_score = 100.0 if len(groups) >= 2 else len(groups) / 2 * 100

    # HMW discussion (15%)
    hmw_score = 100.0 if any(
        "hmw" in m.get("content", "").lower()
        or "我們如何" in m.get("content", "")
        or "怎麼樣才能" in m.get("content", "")
        for m in chat
    ) else 0.0

    # Participant coverage (10%)
    coverage_score = participant_coverage(canvas, seats)

    return (
        group_complete_score * 0.35
        + group_count_score * 0.20
        + move_ratio_score * 0.20
        + hmw_score * 0.15
        + coverage_score * 0.10
    )


def score_develop(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    total_notes = canvas.get("total_notes", 0)
    groups = canvas.get("groups", [])

    # New note count (30%): >= 20 = 100
    note_score = min(100.0, total_notes / 20 * 100)

    # Slowdown (20%): conservative 0
    slowdown_score = 0.0

    # Idea diversity (25%): >= 3 groups = 100
    diversity_score = min(100.0, len(groups) / 3 * 100)

    # Extension behaviour (15%): proxy — group count > 0
    extension_score = 100.0 if len(groups) > 0 else 0.0

    # Participant coverage (10%)
    coverage_score = participant_coverage(canvas, seats)

    return (
        note_score * 0.30
        + slowdown_score * 0.20
        + diversity_score * 0.25
        + extension_score * 0.15
        + coverage_score * 0.10
    )


def score_deliver(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    groups = canvas.get("groups", [])
    total_notes = canvas.get("total_notes", 0)

    # Priority sorting (30%)
    priority_score = 0.0
    sort_keywords = ["優先", "排序", "先做", "重要", "priority"]
    if len(groups) >= 1 and any(
        any(kw in m.get("content", "").lower() for kw in sort_keywords)
        for m in chat
    ):
        priority_score = 100.0
    elif len(groups) >= 1:
        priority_score = 50.0

    # Implementation steps (25%)
    step_keywords = ["步驟", "第一步", "step", "實施", "計畫", "action"]
    notes: list[dict] = canvas.get("notes", [])
    has_steps = any(
        any(kw in n.get("content", "").lower() for kw in step_keywords)
        for n in notes
    )
    steps_score = 100.0 if has_steps else 0.0

    # Evaluation discussion depth (25%): >= 10 evaluation-related messages
    eval_keywords = ["可行", "評估", "風險", "成本", "效益", "impact"]
    eval_msgs = sum(
        1 for m in chat
        if any(kw in m.get("content", "").lower() for kw in eval_keywords)
    )
    eval_score = min(100.0, eval_msgs / 10 * 100)

    # Team activity (10%)
    activity_score = min(100.0, len(chat) / 15 * 100)

    # Consensus expression (10%)
    consensus_keywords = ["同意", "決定", "確定", "共識", "就這樣", "agree"]
    consensus_score = 100.0 if any(
        any(kw in m.get("content", "").lower() for kw in consensus_keywords)
        for m in chat
    ) else 0.0

    return (
        priority_score * 0.30
        + steps_score * 0.25
        + eval_score * 0.25
        + activity_score * 0.10
        + consensus_score * 0.10
    )


def compute_quantitative(
    stage: str,
    canvas: dict,
    recent_chat: list[dict],
    seats: list[dict],
) -> float:
    """Dispatch quantitative scoring to the appropriate stage function."""
    fn = {
        "discover": score_discover,
        "define": score_define,
        "develop": score_develop,
        "deliver": score_deliver,
    }.get(stage, score_discover)
    return fn(canvas, recent_chat, seats)
