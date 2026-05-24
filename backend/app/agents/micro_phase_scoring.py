"""Micro Phase quantitative scoring functions (v2.0).

Each micro phase has its own scoring function with metrics derived from
the delivery criteria in DT-Phase-Facilitation-Guide.md and spec §5.2.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.llm_context import LLMCallContext

logger = logging.getLogger(__name__)

_EMOTION_KEYWORDS = [
    "焦慮", "挫折", "開心", "擔心", "困惑", "生氣", "無奈",
    "滿足", "害怕", "期待", "失望", "煩躁", "壓力", "安心", "緊張",
]
_CONSENSUS_KEYWORDS = ["同意", "共識", "就這個", "好的", "確定", "決定", "就這樣"]
# Prefixes that identify non-persona groups (used to filter in _score_1_3)
_NON_PERSONA_PREFIXES = ("旅程", "洞察", "HMW", "原型", "測試", "★")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _linear_score(value: float, target: float) -> float:
    """Linear 0-100 score. Returns 100 when value >= target."""
    if target <= 0:
        return 100.0
    return min(100.0, (value / target) * 100.0)


def _range_score(value: int, min_val: int, max_val: int) -> float:
    """100 if min_val <= value <= max_val, else linear decrease."""
    if value < min_val:
        return _linear_score(value, min_val)
    if value > max_val:
        return max(0.0, 100.0 - ((value - max_val) / max_val) * 100.0)
    return 100.0


def _count_unique_authors(notes: list[dict]) -> int:
    """Count unique author values in notes list."""
    return len({n.get("author", "") for n in notes if n.get("author")})


def _count_notes_with_keywords(notes: list[dict], keywords: list[str]) -> int:
    """Count notes whose content contains any of the keywords."""
    return sum(1 for n in notes if any(kw in n.get("content", "") for kw in keywords))


def _chat_contains_keywords(chat: list[dict], keywords: list[str]) -> int:
    """Count distinct keywords found across all chat messages."""
    found: set[str] = set()
    for msg in chat:
        content = msg.get("content", "")
        for kw in keywords:
            if kw in content:
                found.add(kw)
    return len(found)


def _count_groups_matching(groups: list[dict], prefix: str) -> int:
    """Count groups whose name starts with prefix."""
    return sum(1 for g in groups if g.get("name", "").startswith(prefix))


def _participation_score(notes: list[dict], seats: list[dict]) -> float:
    """Score based on how many seated members contributed notes."""
    if not seats:
        return 100.0
    seat_ids = {s.get("agent_id", s.get("user_name", s.get("role", ""))) for s in seats}
    if not seat_ids:
        return 100.0
    authors = {n.get("author", "").split("(")[0].strip() for n in notes}
    covered = sum(1 for sid in seat_ids if any(sid in a for a in authors))
    return _linear_score(covered, len(seat_ids))


def _notes_in_group(canvas: dict, group_name_prefix: str) -> list[dict]:
    """Return notes belonging to the first group matching the prefix."""
    notes_map: dict[str, dict] = {n["id"]: n for n in canvas.get("notes", []) if "id" in n}
    for g in canvas.get("groups", []):
        if g.get("name", "").startswith(group_name_prefix):
            return [notes_map[nid] for nid in g.get("notes", []) if nid in notes_map]
    return []


def _chat_has_keywords(chat: list[dict], keywords: list[str]) -> bool:
    """Return True if any chat message contains any of the keywords."""
    return any(any(kw in msg.get("content", "") for kw in keywords) for msg in chat)


# ---------------------------------------------------------------------------
# Phase 1 — Discover
# ---------------------------------------------------------------------------

def _score_1_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """暖場與經驗分享 — warm-up and experience sharing."""
    notes: list[dict] = canvas.get("notes", [])
    # participation: target = 60% of members
    target_members = max(1, len(seats)) * 0.6
    authors = {n.get("author", "").split("(")[0].strip() for n in notes}
    covered = sum(
        1 for s in seats
        if any(s.get("agent_id", s.get("user_name", s.get("role", ""))) in a for a in authors)
    )
    # TODO: LLM-assisted (emotion keywords used as heuristic)
    return (
        _linear_score(len(notes), 5) * 0.30
        + _linear_score(covered, target_members) * 0.30
        + _linear_score(_count_notes_with_keywords(notes, _EMOTION_KEYWORDS), 2) * 0.20
        + _linear_score(len(chat), 5) * 0.20
    )


def _score_1_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """視角擴展 — perspective broadening."""
    notes: list[dict] = canvas.get("notes", [])
    # TODO: LLM-assisted (author count used as viewpoint diversity heuristic)
    orange_count = sum(1 for n in notes if n.get("color", "") == "orange")
    shift_keywords = ["轉變", "改變想法", "沒想到", "原來"]
    from app.agents.evaluator_scoring import _compute_slowdown_score  # type: ignore[import]
    return (
        _linear_score(len(notes), 15) * 0.20
        + _linear_score(_count_unique_authors(notes), 3) * 0.30
        + (100.0 if orange_count >= 1 else 0.0) * 0.20
        + (100.0 if _chat_has_keywords(chat, shift_keywords) else 0.0) * 0.15
        + _compute_slowdown_score(canvas) * 0.15
    )


def _score_1_3(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """Persona 建立 — persona creation."""
    groups: list[dict] = canvas.get("groups", [])
    notes_map: dict[str, dict] = {n["id"]: n for n in canvas.get("notes", []) if "id" in n}
    persona_groups = [
        g for g in groups
        if not any(g.get("name", "").startswith(p) for p in _NON_PERSONA_PREFIXES)
    ]
    completeness_keywords = ["需求", "痛點", "語錄"]
    if persona_groups:
        complete_count = sum(
            1 for g in persona_groups
            if _count_notes_with_keywords(
                [notes_map[nid] for nid in g.get("notes", []) if nid in notes_map],
                completeness_keywords,
            ) >= 1
        )
        evidence_count = sum(1 for g in persona_groups if len(g.get("notes", [])) >= 3)
        completeness_score = _linear_score(complete_count, len(persona_groups))
        evidence_score = _linear_score(evidence_count, len(persona_groups))
    else:
        completeness_score = evidence_score = 0.0
    return (
        _range_score(len(persona_groups), 2, 4) * 0.30
        + completeness_score * 0.30
        + evidence_score * 0.20
        + (100.0 if _count_groups_matching(groups, "★") >= 1 else 0.0) * 0.20
    )


# ---------------------------------------------------------------------------
# Phase 2 — Define
# ---------------------------------------------------------------------------

def _score_2_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """旅程追蹤 — journey mapping."""
    groups: list[dict] = canvas.get("groups", [])
    journey_exists = any(g.get("name", "").startswith("旅程") for g in groups)
    journey_notes = _notes_in_group(canvas, "旅程") if journey_exists else []
    colors = {n.get("color", "") for n in journey_notes}
    mixed_score = 100.0 if colors >= {"green", "yellow", "red"} else _linear_score(
        len(colors & {"green", "yellow", "red"}), 3
    )
    pain_score = 100.0 if any(n.get("color", "") == "red" for n in journey_notes) else 0.0
    return (
        (100.0 if journey_exists else 0.0) * 0.25
        + _linear_score(len(journey_notes), 5) * 0.25
        + mixed_score * 0.25
        + pain_score * 0.25
    )


def _score_2_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """洞察萃取 — insight extraction."""
    notes: list[dict] = canvas.get("notes", [])
    blue_count = sum(1 for n in notes if n.get("color", "") == "blue")
    insight_group_count = len(_notes_in_group(canvas, "洞察"))
    # TODO: LLM-assisted (keyword heuristics for format, contradiction, depth)
    return (
        _linear_score(max(blue_count, insight_group_count), 2) * 0.25
        + _linear_score(_count_notes_with_keywords(notes, ["需要", "因為", "但"]), 1) * 0.25
        + (100.0 if _chat_has_keywords(chat, ["矛盾", "衝突", "張力", "但是", "卻"]) else 0.0) * 0.25
        + (100.0 if _chat_has_keywords(chat, ["為什麼", "根本原因", "深層"]) else 0.0) * 0.25
    )


def _score_2_3(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """HMW — How Might We framing."""
    notes: list[dict] = canvas.get("notes", [])
    groups: list[dict] = canvas.get("groups", [])
    hmw_group_notes = _notes_in_group(canvas, "HMW")
    hmw_inline = [n for n in notes if "我們如何能" in n.get("content", "")]
    target_notes = hmw_group_notes or hmw_inline
    hmw_total = max(len(hmw_group_notes), len(hmw_inline))
    star_hmw = [g for g in groups if g.get("name", "").startswith("★") and "HMW" in g.get("name", "")]
    if target_notes:
        in_range = sum(1 for n in target_notes if 10 <= len(n.get("content", "")) <= 40)
        granularity_score = _linear_score(in_range, len(target_notes))
    else:
        granularity_score = 0.0
    return (
        _linear_score(hmw_total, 3) * 0.20
        + (100.0 if star_hmw else 0.0) * 0.25
        + granularity_score * 0.25
        + (100.0 if any(g.get("name", "").startswith("洞察") for g in groups) else 0.0) * 0.15
        + (100.0 if _chat_has_keywords(chat, _CONSENSUS_KEYWORDS) else 0.0) * 0.15
    )


# ---------------------------------------------------------------------------
# Phase 3 — Develop
# ---------------------------------------------------------------------------

def _score_3_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """大量發散 — divergent ideation."""
    notes: list[dict] = canvas.get("notes", [])
    ungrouped: list[str] = canvas.get("ungrouped", [])
    blocking_keywords = ["做不到", "不可能", "成本太高", "太貴", "不行"]
    # TODO: LLM-assisted (strategy keyword heuristic)
    return (
        _linear_score(len(ungrouped), 15) * 0.25
        + _linear_score(_chat_contains_keywords(chat, ["類比", "反過來", "極端", "如果", "隨機", "組合"]), 3) * 0.25
        + (0.0 if _chat_has_keywords(chat, blocking_keywords) else 100.0) * 0.25
        + _participation_score(notes, seats) * 0.25
    )


def _score_3_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """概念分群 — concept clustering."""
    groups: list[dict] = canvas.get("groups", [])
    regular_groups = [g for g in groups if not g.get("name", "").startswith("★")]
    default_names = {"未命名", "新群組", "", "Group"}
    if regular_groups:
        adequate = sum(1 for g in regular_groups if len(g.get("notes", [])) >= 2)
        named = sum(1 for g in regular_groups if g.get("name", "").strip() not in default_names)
        min_per_group_score = _linear_score(adequate, len(regular_groups))
        direction_score = _linear_score(named, len(regular_groups))
    else:
        min_per_group_score = direction_score = 0.0
    return (
        _range_score(len(regular_groups), 3, 6) * 0.30
        + min_per_group_score * 0.25
        + direction_score * 0.25
        + (100.0 if _chat_has_keywords(chat, _CONSENSUS_KEYWORDS) else 0.0) * 0.20
    )


def _score_3_3(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """評估收斂 — evaluation and convergence."""
    groups: list[dict] = canvas.get("groups", [])
    notes_map: dict[str, dict] = {n["id"]: n for n in canvas.get("notes", []) if "id" in n}
    star_groups = [g for g in groups if g.get("name", "").startswith("★")]
    if star_groups:
        has_purple = sum(
            1 for g in star_groups
            if any(
                notes_map.get(nid, {}).get("color", "") == "purple"
                for nid in g.get("notes", [])
            )
        )
        summary_score = _linear_score(has_purple, len(star_groups))
    else:
        summary_score = 0.0
    purple_notes = [n for n in notes_map.values() if n.get("color", "") == "purple"]
    # TODO: LLM-assisted (assumption keyword heuristic)
    assumption_score = (
        _linear_score(_count_notes_with_keywords(purple_notes, ["假設", "關鍵"]), len(purple_notes))
        if purple_notes else 0.0
    )
    return (
        _range_score(len(star_groups), 2, 3) * 0.25
        + summary_score * 0.30
        + assumption_score * 0.25
        + (100.0 if _chat_has_keywords(chat, _CONSENSUS_KEYWORDS) else 0.0) * 0.20
    )


# ---------------------------------------------------------------------------
# Phase 4 — Deliver
# ---------------------------------------------------------------------------

def _score_4_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """原型規劃 — prototype planning."""
    notes: list[dict] = canvas.get("notes", [])
    prototype_notes = _notes_in_group(canvas, "原型")
    red_count = sum(1 for n in notes if n.get("color", "") == "red")
    return (
        (100.0 if prototype_notes else 0.0) * 0.30
        + _linear_score(len(prototype_notes), 3) * 0.30
        + (100.0 if red_count >= 1 else 0.0) * 0.25
        + 100.0 * 0.15  # time_control: always 100 — cannot measure from canvas
    )


def _score_4_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """測試設計 — test design."""
    groups: list[dict] = canvas.get("groups", [])
    notes: list[dict] = canvas.get("notes", [])
    plan_exists = any(g.get("name", "").startswith("測試計畫") for g in groups)
    # TODO: LLM-assisted (keyword heuristics for criteria, failure, assumption)
    return (
        (100.0 if plan_exists else 0.0) * 0.30
        + _linear_score(_count_notes_with_keywords(notes, ["成功", "看到", "失敗", "代表"]), 2) * 0.35
        + _linear_score(_count_notes_with_keywords(notes, ["失敗", "應對", "代表"]), 1) * 0.20
        + _linear_score(_count_notes_with_keywords(notes, ["假設", "致命", "最重要"]), 1) * 0.15
    )


def _score_4_3(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """模擬測試 — simulated testing."""
    groups: list[dict] = canvas.get("groups", [])
    notes: list[dict] = canvas.get("notes", [])
    exec_count = _count_notes_with_keywords(notes, ["通過", "失敗"])
    result_exists = any(n.get("color", "") in ("green", "red") for n in notes)
    rec_exists = any(g.get("name", "").startswith("★ 推薦方案") for g in groups)
    # TODO: LLM-assisted (learning keywords)
    return (
        (100.0 if exec_count >= 1 else 0.0) * 0.20
        + (100.0 if result_exists else 0.0) * 0.20
        + _linear_score(_count_notes_with_keywords(notes, ["學到", "學習", "發現"]), 1) * 0.20
        + (100.0 if _chat_has_keywords(chat, ["決定", "推薦", "最終", "下一步"]) else 0.0) * 0.20
        + (100.0 if rec_exists else 0.0) * 0.20
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_SCORERS: dict[str, object] = {
    "1_1": _score_1_1, "1_2": _score_1_2, "1_3": _score_1_3,
    "2_1": _score_2_1, "2_2": _score_2_2, "2_3": _score_2_3,
    "3_1": _score_3_1, "3_2": _score_3_2, "3_3": _score_3_3,
    "4_1": _score_4_1, "4_2": _score_4_2, "4_3": _score_4_3,
}


# Hard minimums: if these are not met, score is capped at 30 (cannot pass threshold)
_HARD_MINIMUMS: dict[str, dict[str, int]] = {
    "1.1": {"notes": 5},
    "1.2": {"notes": 12},
    "1.3": {"persona_groups": 2},
    "2.1": {"journey_groups": 1},
    "3.1": {"notes": 10},
}


def _check_hard_minimums(micro_phase: str, canvas: dict) -> bool:
    """Return True if hard minimums are met, False otherwise."""
    mins = _HARD_MINIMUMS.get(micro_phase, {})
    if "notes" in mins:
        if canvas.get("total_notes", 0) < mins["notes"]:
            return False
    if "persona_groups" in mins:
        groups = canvas.get("groups", [])
        persona_count = sum(
            1 for g in groups
            if not any(g.get("name", "").startswith(p) for p in ("旅程", "洞察", "HMW", "原型", "測試", "★ 推薦"))
        )
        if persona_count < mins["persona_groups"]:
            return False
    if "journey_groups" in mins:
        groups = canvas.get("groups", [])
        journey_count = sum(1 for g in groups if g.get("name", "").startswith("旅程"))
        if journey_count < mins["journey_groups"]:
            return False
    return True


async def compute_micro_phase_quantitative(
    micro_phase: str,
    canvas: dict,
    chat: list[dict],
    seats: list[dict],
    *,
    llm_service: Any = None,
    llm_ctx: "LLMCallContext | None" = None,
) -> float:
    """Dispatch to per-micro-phase scoring with optional LLM calibration.

    # 先用 LLM 處理，未來依實測調整權重或移除 LLM

    Hard minimums: if note count or group requirements are not met,
    score is capped at 30.0 regardless of other metrics.
    """
    key = micro_phase.replace(".", "_")
    scorer = _SCORERS.get(key)
    if scorer is None:
        return 50.0  # fallback
    score = scorer(canvas, chat, seats)  # type: ignore[operator]
    is_all_ai = all(s.get("type") == "ai" for s in seats)

    # All-AI fallback: when no tldraw groups exist (AI agents never create them),
    # group-dependent scoring produces 0. Use note+chat activity as floor.
    if is_all_ai and score < 10.0:
        total_notes = canvas.get("total_notes", 0)
        chat_count = len(chat)
        fallback = (
            min(100.0, total_notes / 20 * 100) * 0.40
            + min(100.0, chat_count / 15 * 100) * 0.40
            + (100.0 if total_notes > 0 and chat_count > 0 else 0.0) * 0.20
        )
        score = max(score, fallback)

    # Apply hard minimum cap (skip in all-AI mode)
    if not is_all_ai and not _check_hard_minimums(micro_phase, canvas):
        score = min(score, 30.0)

    rule_score = score

    if llm_service is None or llm_ctx is None:
        return rule_score

    try:
        response = await llm_service.chat_completion(
            messages=[
                {"role": "system", "content": "你是 Design Thinking 工作坊評估專家。"},
                {"role": "user", "content": (
                    f"根據以下工作坊狀態，你認為微階段 {micro_phase} 的完成度是 0-100？只回答數字。\n\n"
                    f"便利貼數量：{canvas.get('total_notes', 0)}\n"
                    f"群組數量：{len(canvas.get('groups', []))}\n"
                    f"聊天訊息數：{len(chat)}\n"
                    f"規則引擎分數：{rule_score:.0f}"
                )},
            ],
            temperature=0.0,
            max_tokens=10,
            caller="micro_phase_scoring",
            owning_user_id=llm_ctx.owning_user_id,
            project_id=llm_ctx.project_id,
        )
        llm_score = float(response.content.strip())
        llm_score = max(0.0, min(100.0, llm_score))
        return rule_score * 0.4 + llm_score * 0.6
    except Exception:
        logger.debug("compute_micro_phase_quantitative LLM calibration failed")
        return rule_score
