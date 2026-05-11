"""Persona A triggers — Spec 14 §2.1 + Phase 18 LLM-judge integration.

每個 trigger 是 async 函式：(context) → trigger_id | None
回 trigger_id 表示應該 fire，回 None 表示不 fire。
所有「內容性質」判斷透過 llm_judge.judge_content，純計數用 rule。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.agents.llm_judge import is_violating, judge_content

logger = logging.getLogger(__name__)


# 推進前一輪要看的 sub_phase 集合（A1 用）
_ANNOUNCE_PHASES: set[str] = {"1.1a", "1.5", "1.6", "2.1", "2.2", "3.1", "3.2", "4.1a", "4.2"}


async def detect_a_triggers(ctx: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Run all Persona A trigger checks. Return [(trigger_id, context_dict), ...]."""
    fired: list[tuple[str, dict[str, str]]] = []

    sub_phase = ctx.get("current_sub_phase") or ""
    if not sub_phase:
        return fired

    # A1: phase enter announce — 由 stage_advancement 廣播事件後 supervisor 第一個 tick fire
    # 這裡簡化：只要當前 sub_phase 在 announce 集合且 supervisor 還沒講過話就 fire
    if sub_phase in _ANNOUNCE_PHASES and not _supervisor_announced_for_phase(ctx, sub_phase):
        from app.stages.sub_phases import SUB_PHASES
        sp = SUB_PHASES.get(sub_phase)
        if sp:
            div = _divergence_label(sub_phase)
            fired.append(("A1_phase_enter_announce", {
                "sub_phase": sub_phase,
                "sub_phase_name": sp.name_zh,
                "divergence_or_convergence": div,
            }))

    # A2: 1.1d scope rationale missing — 由 deliverable check 補上，但這裡也提早提示
    if sub_phase == "1.1d":
        scope_missing = ctx.get("_a2_scope_missing", False)  # 由 router 預判
        if scope_missing:
            fired.append(("A2_scope_rationale_missing", {}))

    # A4: POV count < 3 in 2.2 / 2.3
    if sub_phase in ("2.2", "2.3"):
        pov_count = ctx.get("_pov_count", 0)
        if pov_count < 3:
            fired.append(("A4_pov_count_low", {
                "count": str(pov_count),
                "needed": str(3 - pov_count),
            }))

    # A5: POV tautology — LLM-judge 最後一張 POV
    last_pov = ctx.get("_last_pov_text", "")
    if sub_phase in ("2.2", "2.3") and last_pov:
        result = await judge_content(
            text=last_pov,
            rule_module="pov_quality",
            context={"sub_phase": sub_phase, "zone": "pov_wall"},
        )
        if is_violating(result, min_confidence=0.7):
            fired.append(("A5_pov_tautology", {"pov_text": last_pov[:80]}))

    # A7: criteria-before-vote (2.6 / 4.1c)
    if sub_phase in ("2.6", "4.1c"):
        criteria_count = ctx.get("_criteria_count", 0)
        wants_vote = ctx.get("_wants_open_vote", False)
        if wants_vote and criteria_count < 3:
            fired.append(("A7_no_criteria_before_vote", {"count": str(criteria_count)}))

    # A8: too many winners (after vote close)
    if sub_phase in ("2.6", "4.1c"):
        winner_count = ctx.get("_vote_winner_count", 0)
        if winner_count > 3:
            fired.append(("A8_too_many_winners", {"count": str(winner_count)}))

    # A9: HMW not written for selected POVs (2.7)
    if sub_phase == "2.7":
        missing = ctx.get("_hmw_missing_count", 0)
        if missing > 0:
            fired.append(("A9_hmw_not_written", {"missing_count": str(missing)}))

    # A10: category-shift needed (3.4) — LLM-judge based on idea pool
    if sub_phase == "3.4":
        idea_count = ctx.get("_idea_count", 0)
        idea_sample = ctx.get("_idea_text_sample", "")
        if idea_count >= 6 and idea_sample:
            result = await judge_content(
                text=idea_sample,
                rule_module="category_diversity",
                context={"sub_phase": sub_phase, "zone": "idea_pool"},
            )
            if is_violating(result, min_confidence=0.6):
                fired.append(("A10_category_shift_needed", {
                    "idea_count": str(idea_count),
                    "current_mechanism": ctx.get("_dominant_mechanism", "目前主流機制"),
                    "suggested_mechanism": ctx.get("_suggested_mechanism", "其他角度"),
                }))

    # A12: task before hypothesis (4.1e)
    if sub_phase == "4.1e":
        if ctx.get("_hypothesis_missing", False):
            fired.append(("A12_task_before_hypothesis", {}))

    # A13: v1 production code (4.1f) — LLM judge
    if sub_phase == "4.1f":
        sample = ctx.get("_prototype_text_sample", "")
        if sample:
            result = await judge_content(
                text=sample,
                rule_module="no_production_code",
                context={"sub_phase": sub_phase, "zone": "prototype_zone"},
            )
            if is_violating(result, min_confidence=0.65):
                fired.append(("A13_v1_production_code", {}))

    # A14: debrief shallow (4.2) — LLM judge per answer
    if sub_phase == "4.2":
        debrief_answers = ctx.get("_debrief_answers", [])
        shallow = 0
        for ans in debrief_answers[:3]:
            if not ans:
                shallow += 1
                continue
            result = await judge_content(
                text=ans,
                rule_module="debrief_depth",
                context={"sub_phase": sub_phase},
            )
            if is_violating(result, min_confidence=0.6):
                shallow += 1
        if shallow > 0:
            fired.append(("A14_debrief_shallow", {"shallow_count": str(shallow)}))

    # A15: direction undecided (4.3)
    if sub_phase == "4.3":
        elapsed = ctx.get("_phase_elapsed_min", 0)
        decided = ctx.get("_direction_decided", False)
        if elapsed >= 10 and not decided:
            fired.append(("A15_direction_undecided", {"elapsed_min": str(elapsed)}))

    return fired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _divergence_label(sub_phase: str) -> str:
    """sub-phase 級別的「發散 / 收斂 / 過渡」中文標籤。

    具體分類規則委派給 `app.stages.phase_intent`，避免發散收斂定義
    散落多處（specs/16-timer-system.md §6.5.2）。
    """
    from app.stages.phase_intent import (
        get_phase_intent_by_sub_phase,
        get_phase_intent_label_zh,
    )
    return get_phase_intent_label_zh(get_phase_intent_by_sub_phase(sub_phase))


def _supervisor_announced_for_phase(ctx: dict[str, Any], sub_phase: str) -> bool:
    """Check if supervisor already announced for this sub_phase."""
    recent_chat = ctx.get("recent_chat", [])
    for msg in recent_chat[-10:]:
        if "supervisor" not in str(msg.get("sender", "")).lower():
            continue
        content = msg.get("content", "")
        if sub_phase in content:
            return True
    return False
