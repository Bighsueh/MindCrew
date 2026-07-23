"""Micro Phase quantitative scoring functions（spec 04-05 v4.26，Phase 42 C1）.

新 6 桶（0.0 不計分／1.1／1.2／2.1／2.2／2.3）的規則評分。定位＝**邊界訊號／
組長訊號面板的品質參考**（Evaluator 不推進，04-06 v4.25 §5.8）；硬性推進條件
一律由 artifact gate（spec 25 v2.0）與真人 gate（spec 20 v2.0）enforce。

規則指標以 evaluator canvas 摘要的可計數欄位（便條內容／作者／群組／聊天）為限
的 **proxy**——牆面歸屬、kind、群下掛載等高保真判定屬 artifact gate 層，
此處以內容長度／模板句型／群組覆蓋近似（04-05 v4.26 §5.2 明文）。
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.llm_context import LLMCallContext

logger = logging.getLogger(__name__)

# 規則層關鍵詞表（04-05 v4.26：情緒偵測不再單列 LLM 能力；表保留供未來使用）。
_EMOTION_KEYWORDS = [
    "焦慮", "挫折", "開心", "擔心", "困惑", "生氣", "無奈",
    "滿足", "害怕", "期待", "失望", "煩躁", "壓力", "安心", "緊張",
]
_CONSENSUS_KEYWORDS = ["同意", "共識", "就這個", "好的", "確定", "決定", "就這樣"]
# 2.2 桶：追問根源（2.3 走透）與現有解法盤點（2.4）的聊天訊號詞。
_ROOT_CAUSE_KEYWORDS = ["為什麼", "根源", "根本原因", "原因"]
_EXISTING_SOLUTION_KEYWORDS = ["已經有", "市面上", "現有", "別人做過", "既有"]
# 2.3 桶：無投票收斂訊號（選定區語言）。
_SELECTION_KEYWORDS = ["選這", "選定", "搬進", "就這幾張", "留下這"]
# 1.1d 高/中/低標記（label 便條的常見寫法）。
_PRIORITY_LABELS = {"高", "中", "低", "高優先", "中優先", "低優先"}


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


def _participation_score(notes: list[dict], seats: list[dict]) -> float:
    """Score based on how many seated members contributed notes（≥60% 滿分）。"""
    if not seats:
        return 100.0
    seat_ids = {s.get("agent_id", s.get("user_name", s.get("role", ""))) for s in seats}
    seat_ids = {sid for sid in seat_ids if sid}
    if not seat_ids:
        return 100.0
    authors = {n.get("author", "").split("(")[0].strip() for n in notes}
    covered = sum(1 for sid in seat_ids if any(sid in a for a in authors))
    return _linear_score(covered, max(1.0, len(seat_ids) * 0.6))


def _chat_has_keywords(chat: list[dict], keywords: list[str]) -> bool:
    """Return True if any chat message contains any of the keywords."""
    return any(any(kw in msg.get("content", "") for kw in keywords) for msg in chat)


def _group_coverage_score(canvas: dict) -> float:
    """每群 ≥1 張掛載的覆蓋率（群下掛載 proxy）。無群 → 0。"""
    groups: list[dict] = canvas.get("groups", [])
    if not groups:
        return 0.0
    covered = sum(1 for g in groups if len(g.get("notes", [])) >= 1)
    return _linear_score(covered, len(groups))


def _count_priority_labels(notes: list[dict]) -> int:
    return sum(1 for n in notes if n.get("content", "").strip() in _PRIORITY_LABELS)


def _count_template_notes(notes: list[dict], template_id: str) -> int:
    """以模板句型計數（problem_statement／criteria；deterministic regex）。"""
    from app.canvas.text_templates import validate_template

    count = 0
    for n in notes:
        text = n.get("content", "")
        if not text.strip():
            continue
        try:
            if validate_template(text, template_id).passed:
                count += 1
        except KeyError:  # pragma: no cover - 模板不存在
            return 0
    return count


# ---------------------------------------------------------------------------
# Phase 1 — Discover
# ---------------------------------------------------------------------------

def _score_1_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """經驗分享與利害關係人（1.1a–1.1d）— 04-05 v4.26 §5.2。"""
    notes: list[dict] = canvas.get("notes", [])
    groups: list[dict] = canvas.get("groups", [])
    label_count = _count_priority_labels(notes)
    group_count = len(groups)
    label_score = (
        _linear_score(label_count, group_count) if group_count else 0.0
    )
    return (
        _linear_score(len(notes), 8) * 0.30
        + _range_score(group_count, 2, 5) * 0.25
        + label_score * 0.20
        + _participation_score(notes, seats) * 0.15
        + _linear_score(len(chat), 5) * 0.10
    )


def _score_1_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """發想痛點與情境 — 04-05 v4.26 §5.2。

    痛點張數 proxy＝內容 ≥10 字的便條（具體情境是句子；名字/標籤是短文字）。
    高優先群逐群硬判定在 artifact gate，此處以「每群 ≥1 張掛載」近似。
    """
    notes: list[dict] = canvas.get("notes", [])
    pain_like = sum(1 for n in notes if len(n.get("content", "").strip()) >= 10)
    return (
        _linear_score(pain_like, 6) * 0.35
        + _group_coverage_score(canvas) * 0.25
        + _participation_score(notes, seats) * 0.20
        + _linear_score(len(chat), 8) * 0.20
    )


# ---------------------------------------------------------------------------
# Phase 2 — Define
# ---------------------------------------------------------------------------

def _score_2_1(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """痛點歸類 — 04-05 v4.26 §5.2（主題群 ≥3、每群 ≥1、拖＋說）。"""
    groups: list[dict] = canvas.get("groups", [])
    return (
        _linear_score(len(groups), 3) * 0.40
        + _group_coverage_score(canvas) * 0.35
        + _linear_score(len(chat), 3) * 0.25
    )


def _score_2_2(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """問題定義與深掘（2.2–2.4）— 04-05 v4.26 §5.2。"""
    notes: list[dict] = canvas.get("notes", [])
    ps_count = _count_template_notes(notes, "problem_statement")
    return (
        _linear_score(ps_count, 3) * 0.35
        + (100.0 if _chat_has_keywords(chat, _ROOT_CAUSE_KEYWORDS) else 0.0) * 0.25
        + (100.0 if _chat_has_keywords(chat, _EXISTING_SOLUTION_KEYWORDS) else 0.0) * 0.20
        + _participation_score(notes, seats) * 0.20
    )


def _score_2_3(canvas: dict, chat: list[dict], seats: list[dict]) -> float:
    """訂準則、收斂與設計題目（2.5–2.7，第一鑽石終局）— 04-05 v4.26 §5.2。"""
    notes: list[dict] = canvas.get("notes", [])
    criteria_count = _count_template_notes(notes, "criteria")
    dq_count = sum(1 for n in notes if "我們可以怎麼" in n.get("content", ""))
    return (
        _linear_score(criteria_count, 2) * 0.30
        + _linear_score(dq_count, 1) * 0.30
        + (100.0 if _chat_has_keywords(chat, _SELECTION_KEYWORDS) else 0.0) * 0.25
        + (100.0 if _chat_has_keywords(chat, _CONSENSUS_KEYWORDS) else 0.0) * 0.15
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
#
# Phase 42 C1：舊 _score_1_3（Persona）隨格刪除；舊 2.1（旅程/顏色）、2.2（藍色
# 洞察）、2.3（HMW ★）指標作廢，整組改寫為新桶語意（04-05 v4.26 §5.2）。

_SCORERS: dict[str, object] = {
    "1_1": _score_1_1, "1_2": _score_1_2,
    "2_1": _score_2_1, "2_2": _score_2_2, "2_3": _score_2_3,
}


# Hard minimums: if these are not met, score is capped at 30 (cannot pass threshold)
# Phase 42 C1：persona_groups／journey_groups 隨舊桶刪除；地板取 40 分 preset
# （intensity 0.4）縮放後仍可達的量（1.1b→3、1.2 痛點→2＋既有利害關係人）。
_HARD_MINIMUMS: dict[str, dict[str, int]] = {
    "1.1": {"notes": 3},
    "1.2": {"notes": 5},
}


def _check_hard_minimums(micro_phase: str, canvas: dict) -> bool:
    """Return True if hard minimums are met, False otherwise."""
    mins = _HARD_MINIMUMS.get(micro_phase, {})
    if "notes" in mins:
        if canvas.get("total_notes", 0) < mins["notes"]:
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

    Hard minimums: if note count requirements are not met,
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
