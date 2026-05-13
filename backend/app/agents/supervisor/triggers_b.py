"""Persona B triggers — Spec 14 §2.2 + B11 主動問.

All content-related triggers use llm_judge with regex pre-filter.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.llm_judge import is_violating, judge_content

logger = logging.getLogger(__name__)

# Phases that are pure 發散 (forbid feasibility/criticism in stricter sense)
_DIVERGENT_PHASES: set[str] = {
    "1.1a", "1.1b", "1.5",
    "2.2",
    "3.1", "3.2", "3.3",
}


async def detect_b_triggers(ctx: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Run all Persona B trigger checks."""
    fired: list[tuple[str, dict[str, str]]] = []

    sub_phase = ctx.get("current_sub_phase") or ""
    recent_chat = ctx.get("recent_chat", [])

    # B1: criticism — LLM judge on most recent non-supervisor message
    last_non_sup = _latest_non_supervisor_message(recent_chat)
    if last_non_sup:
        speaker = last_non_sup.get("sender", "")
        text = last_non_sup.get("content", "")
        if text:
            result = await judge_content(
                text=text,
                rule_module="no_criticism",
                context={"sub_phase": sub_phase, "recent_chat": recent_chat[-3:]},
            )
            if is_violating(result, min_confidence=0.65):
                fired.append(("B1_criticism", {
                    "speaker": speaker,
                    "matched_phrase": text[:60],
                }))

    # B2: feasibility-talk in divergent phase
    if sub_phase in _DIVERGENT_PHASES and last_non_sup:
        text = last_non_sup.get("content", "")
        if text:
            result = await judge_content(
                text=text,
                rule_module="no_feasibility_talk",
                context={"sub_phase": sub_phase},
            )
            if is_violating(result, min_confidence=0.65):
                fired.append(("B2_feasibility_in_diverge", {
                    "sub_phase": sub_phase,
                    "matched_phrase": text[:60],
                }))

    # B3 系列：specs/16-timer-system.md §6.5.5 四階遞進壓力 trigger
    used_pct = ctx.get("time_budget_used_pct", 0.0)
    deliverable_done = ctx.get("_deliverable_done", False)
    # phase_intent 由 context_buffer 注入；舊呼叫點若沒灌入，預設 transitional
    # 不會引發發散階段專屬 trigger（B3a / B3c）。
    phase_intent = ctx.get("phase_intent", "transitional")

    remaining = max(0, 100 - int(used_pct))
    pressure_payload = {
        "sub_phase": sub_phase,
        "used_pct": str(int(used_pct)),
        "remaining_pct": str(remaining),
    }

    # critical：≥90% 不論意圖，強制 re-scope（原 B3 改名為 _critical_rescope）
    if used_pct >= 90.0 and not deliverable_done:
        fired.append(("B3_critical_rescope", pressure_payload))
    # B3c：75-90% 仍在發散 → 宣告結束發散
    elif used_pct >= 75.0 and phase_intent == "divergent":
        fired.append(("B3c_close_diverge", pressure_payload))
    # B3b：67-75% 任何意圖 → 停止開新主題，收到候選 ≤ 3
    elif used_pct >= 67.0:
        fired.append(("B3b_two_thirds_focus", pressure_payload))
    # B3a：50-67% 且發散 → 提醒可開始挑潛力候選
    elif used_pct >= 50.0 and phase_intent == "divergent":
        fired.append(("B3a_halfway_pivot", pressure_payload))

    # B4: phase sync drift — agents at different sub_phases
    # 全 AI 模式下 sub_phase 由 project 統一決定，主要對人類混合模式有用
    drift = ctx.get("_phase_drift", None)
    if drift and isinstance(drift, dict):
        fired.append(("B4_phase_sync_drift", drift))

    # B5: multi-HMW concurrency
    active_hmw_count = ctx.get("_active_hmw_count", 1)
    if sub_phase in ("3.2", "3.3", "3.4") and active_hmw_count > 1:
        # 多 HMW 是合理的（已收斂出 2-3 個），只在「同時討論」時警告
        if ctx.get("_multi_hmw_simultaneously", False):
            fired.append(("B5_multi_hmw_concurrency", {"hmw_count": str(active_hmw_count)}))

    # B6: silent member + LLM judge 沉默類型
    silent_member = ctx.get("_silent_member_candidate")
    if silent_member:
        # 用 chat 氣氛判斷類型
        chat_summary = _summarize_recent_chat(recent_chat[-5:])
        result = await judge_content(
            text=chat_summary,
            rule_module="silence_type",
            context={"sub_phase": sub_phase, "silent_member": silent_member.get("name")},
        )
        # violate = 退縮型，需要點名
        if is_violating(result, min_confidence=0.6):
            fired.append(("B6_silent_member", {
                "member": silent_member.get("name", "某成員"),
                "silent_minutes": str(silent_member.get("silent_minutes", 5)),
            }))

    # B7: peek in silent_write
    comm_mode = ctx.get("comm_mode", "discussion")
    if comm_mode == "silent_write" and last_non_sup:
        text = last_non_sup.get("content", "").lower()
        if any(kw in text for kw in ("你寫了", "你的便條", "看到你寫", "你那邊寫")):
            fired.append(("B7_peek_in_silent_write", {}))

    # B9: solution-language in Phase 2
    if sub_phase.startswith("2.") and last_non_sup:
        text = last_non_sup.get("content", "")
        if text:
            result = await judge_content(
                text=text,
                rule_module="no_solution_language",
                context={"sub_phase": sub_phase},
            )
            if is_violating(result, min_confidence=0.7):
                fired.append(("B9_solution_language", {
                    "speaker": last_non_sup.get("sender", ""),
                    "matched_phrase": text[:60],
                }))

    # B10: sticky deletion in develop
    recent_action = ctx.get("_last_canvas_action", {})
    if (sub_phase.startswith("3.") and
            recent_action.get("type") == "delete_note"):
        fired.append(("B10_sticky_deletion_in_develop", {
            "speaker": recent_action.get("agent_name", "某成員"),
        }))

    # B11: deliverable done + timer ≥ 75% → 主動問
    if used_pct >= 75.0 and deliverable_done:
        already_asked = ctx.get("_b11_already_asked_this_phase", False)
        if not already_asked:
            fired.append(("B11_advance_prompt", {
                "sub_phase": sub_phase,
                "used_pct": str(int(used_pct)),
            }))

    return fired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_non_supervisor_message(recent_chat: list[dict]) -> dict | None:
    for msg in reversed(recent_chat):
        sender = msg.get("sender", "").lower()
        sender_id = msg.get("sender_id", "").lower()
        if "supervisor" in sender or "supervisor" in sender_id or "引導" in sender:
            continue
        return msg
    return None


def _summarize_recent_chat(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        sender = m.get("sender", "?")
        content = (m.get("content", "") or "")[:80]
        parts.append(f"{sender}: {content}")
    return "\n".join(parts)
