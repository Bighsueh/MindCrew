"""Persona B triggers — Spec 14 §2.2.

All content-related triggers use llm_judge with regex pre-filter.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.llm_judge import is_violating, judge_content

logger = logging.getLogger(__name__)

# Phases that are pure 發散 (forbid feasibility/criticism in stricter sense).
# Phase 35: 清理殘留 3.1/3.2/3.3 entries（已無對應 sub_phase）。
# Phase 42 C1：舊 1.5（原始捕捉）→ 新 1.2（發想痛點與情境）。
_DIVERGENT_PHASES: set[str] = {
    "1.1a", "1.1b", "1.2",
    "2.2",
}

# B12（離題提醒）不在「刻意天馬行空／講個人經驗」的自由關運行——這些關本就鼓勵發散與
# 跑題式的個人故事，off_topic judge 會把正當內容（如 0.0a 的怪用途、1.1a 的真實經驗）
# 誤判離題、每 tick 狂 fire 把組長卡在「拉回離題」，並連帶餓死 persona-A 佇列（A1 進場
# 宣布永遠輪不到 → docker live 2026-06-19 實證 B12 98 次 vs B13 2 次、pending_a 漲到 17）。
_NO_OFF_TOPIC_PHASES: set[str] = {"0.0a", "1.1a"}


async def detect_b_triggers(ctx: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Run all Persona B trigger checks."""
    fired: list[tuple[str, dict[str, str]]] = []

    sub_phase = ctx.get("current_sub_phase") or ""
    recent_chat = ctx.get("recent_chat", [])
    # Phase 42 B2：judge_content 無 owning_user_id 時保守跳過（永不 violate）——
    # base_agent 注入 _owning_user_id，這裡轉傳給所有 judge 呼叫。
    owning_user_id = ctx.get("_owning_user_id")

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
                owning_user_id=owning_user_id,
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
                owning_user_id=owning_user_id,
            )
            if is_violating(result, min_confidence=0.65):
                fired.append(("B2_feasibility_in_diverge", {
                    "sub_phase": sub_phase,
                    "matched_phrase": text[:60],
                }))

    # B3 系列： 四階遞進壓力 trigger
    # Phase 35 (spec/16 §6.5.5): 同 phase 只 fire 一次 — 由 ctx["_supervisor_fired_triggers"]
    # 提供已 fire 集合（context_buffer 從 Redis 載入），這裡逐個 guard。
    used_pct = ctx.get("time_budget_used_pct", 0.0)
    deliverable_done = ctx.get("_deliverable_done", False)
    # phase_intent 由 context_buffer 注入；舊呼叫點若沒灌入，預設 transitional
    # 不會引發發散階段專屬 trigger（B3a / B3c）。
    phase_intent = ctx.get("phase_intent", "transitional")
    fired_set: set[str] = ctx.get("_supervisor_fired_triggers", set()) or set()

    remaining = max(0, 100 - int(used_pct))
    pressure_payload = {
        "sub_phase": sub_phase,
        "used_pct": str(int(used_pct)),
        "remaining_pct": str(remaining),
    }

    # critical：≥90% 不論意圖，強制 re-scope（原 B3 改名為 _critical_rescope）
    if used_pct >= 90.0 and not deliverable_done:
        if "B3_critical_rescope" not in fired_set:
            fired.append(("B3_critical_rescope", pressure_payload))
    # B3c：75-90% 仍在發散 → 宣告結束發散
    elif used_pct >= 75.0 and phase_intent == "divergent":
        if "B3c_close_diverge" not in fired_set:
            fired.append(("B3c_close_diverge", pressure_payload))
    # B3b：67-75% 任何意圖 → 停止開新主題，收到候選 ≤ 3
    elif used_pct >= 67.0:
        if "B3b_two_thirds_focus" not in fired_set:
            fired.append(("B3b_two_thirds_focus", pressure_payload))
    # B3a：50-67% 且發散 → 提醒可開始挑潛力候選
    elif used_pct >= 50.0 and phase_intent == "divergent":
        if "B3a_halfway_pivot" not in fired_set:
            fired.append(("B3a_halfway_pivot", pressure_payload))

    # B4: phase sync drift — agents at different sub_phases
    # 全 AI 模式下 sub_phase 由 project 統一決定，主要對人類混合模式有用
    drift = ctx.get("_phase_drift", None)
    if drift and isinstance(drift, dict):
        fired.append(("B4_phase_sync_drift", drift))

    # （micro_phase 3.x 已不存在，原 condition `sub_phase in ("3.2","3.3","3.4")` 永遠 false）。
    # 整段已移除以避免 dead code 誤導未來貢獻者。

    # B6: silent member + LLM judge 沉默類型
    silent_member = ctx.get("_silent_member_candidate")
    if silent_member:
        # 用 chat 氣氛判斷類型
        chat_summary = _summarize_recent_chat(recent_chat[-5:])
        result = await judge_content(
            text=chat_summary,
            rule_module="silence_type",
            context={"sub_phase": sub_phase, "silent_member": silent_member.get("name")},
            owning_user_id=owning_user_id,
        )
        # violate = 退縮型，需要點名
        if is_violating(result, min_confidence=0.6):
            fired.append(("B6_silent_member", {
                "member": silent_member.get("name", "某成員"),
                "silent_minutes": str(silent_member.get("silent_minutes", 5)),
            }))

    # B7（peek in silent_write）已隨 Phase 41 移除沉默模式一併刪除——沒有沉默階段就沒有
    # 「偷看別人寫」的違規；避免定錨改由發散期 prompt 軟性護欄（反echo）承載（Spec 27 v2.4）。

    # B9: solution-language in Phase 2
    if sub_phase.startswith("2.") and last_non_sup:
        text = last_non_sup.get("content", "")
        if text:
            result = await judge_content(
                text=text,
                rule_module="no_solution_language",
                context={"sub_phase": sub_phase},
                owning_user_id=owning_user_id,
            )
            if is_violating(result, min_confidence=0.7):
                fired.append(("B9_solution_language", {
                    "speaker": last_non_sup.get("sender", ""),
                    "matched_phrase": text[:60],
                }))

    # B12: 一般離題（spec 15 v2.0 §2.3.1，Phase 42 B2，#21）。
    # 兩型：規則外/meta 提問（答完收束）＋討論整體跑題（主動拉回）。
    # 無 dedup（每次離題都該被接住）；門檻 0.7（B2 裁定）。
    # 自由發想關（_NO_OFF_TOPIC_PHASES）不跑——避免把正當的怪用途／個人經驗誤判離題狂 fire。
    if last_non_sup and sub_phase not in _NO_OFF_TOPIC_PHASES:
        text = last_non_sup.get("content", "")
        if text:
            result = await judge_content(
                text=text,
                rule_module="off_topic",
                context={"sub_phase": sub_phase, "recent_chat": recent_chat[-3:]},
                owning_user_id=owning_user_id,
            )
            if is_violating(result, min_confidence=0.7):
                fired.append(("B12_off_topic_redirect", {
                    "speaker": last_non_sup.get("sender", ""),
                    "matched_phrase": text[:60],
                }))

    # B13: 經驗分享逐一邀請（Phase 42，1.1a 隊友沉默修復；spec 22 1.1a / 04-03 §3.2）。
    # 1.1a 是引導式逐一邀請——組長把每位還沒分享過自身經驗的隊友一位一位點名帶出來。
    # _share_status 由 context_buffer 對組長注入（僅 1.1a）；無 dedup（每 tick 重發直到全員
    # 分享，self-terminating＝missing 清空就不再 fire）。persona B：「讓每個人都有發言空間」。
    # **不依賴 A1 進場宣布已 fire**（docker live 揪出：B12 離題提醒每 tick 搶 persona-B 優先、
    # 把 A1 擠進 pending-A 佇列永不標記 fired → 若 gate 在 A1 上，B13 會被連帶餓死永不 fire）。
    # 框題由 1.1a 進場腳本（SUB_PHASE_ENTRY）承載，不靠 A1 那則 chat 宣布；故 B13 一進 1.1a
    # 有未分享 crew 即可邀（與 B12 等其他 persona-B trigger 同 tick 併發、合併 dispatch）。
    share_status = ctx.get("_share_status")
    if (
        sub_phase == "1.1a"
        and share_status is not None
        and getattr(share_status, "has_human", False)
        and getattr(share_status, "missing_crew_seats", ())
    ):
        seats_missing = share_status.missing_crew_seats
        names_missing = share_status.missing_crews
        target_seat = seats_missing[0]
        fired.append(("B13_share_invite_next", {
            "next_crew_name": names_missing[0] if names_missing else target_seat,
            "next_crew_seat": target_seat,
            "remaining": str(len(seats_missing)),
        }))
        # 防失能 crew 卡死：每次邀請嘗試（＝B13 fire，每個 supervisor 決策週期至多一次）對
        # 目標席位累計一次；達上限（share_experience._INVITE_CAP）仍沒分享 → share_status 把它
        # 從 missing 扣除、改邀下一位。以 B13 fire 為信號＝同時涵蓋 set_directive 與 @-mention
        # 兩種執行路徑、且不會雙重計數（一週期一次）。alive crew 被邀後本週期內即回應、離開
        # missing，不會被誤跳。best-effort：_project_id 缺或 Redis 失敗只 log。
        _pid = ctx.get("_project_id")
        if _pid is not None:
            try:
                from app.progression.share_experience import bump_invite

                await bump_invite(_pid, target_seat)
            except Exception:
                logger.debug("B13 bump_invite failed", exc_info=True)

    # 原「deliverable 達成 + timer ≥ 90% → 主動問是否推進」trigger 已於 Phase 42 廢除
    # （spec/16 §4.6）：與「達標即推進」矛盾，職能併入組長常態推進迴路。

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
