from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Literal

from app.agents.assess_heuristics import (
    extract_cjk_ngrams,
    has_relevant_event_ngram,
    heuristic_has_stance,
)
from app.agents.llm_context import LLMCallContext
from app.agents.turn_controller import TurnController, TurnPolicy
from app.llm.factory import LLMProviderFactory

logger = logging.getLogger(__name__)

DecisionType = Literal["intervene", "wait", "observe"]

# Mapping from ai_contribution level to idle threshold seconds (spec §2.2 Rule 5)
_IDLE_THRESHOLDS: dict[str, float] = {
    "low": 60.0,
    "medium": 30.0,
    "high": 15.0,
}

# Probabilistic intervention chances per contribution level (spec §2.2 Rule 7)
_INTERVENTION_PROBABILITIES: dict[str, float] = {
    "low": 0.30,
    "medium": 0.50,
    "high": 0.80,
}

# 病根 D 軟護欄：便條數超過該 sub-phase target_count 的此倍數 → 視為「量爆掉」，
# 觸發整理（不被發散階段寬鬆 orderliness 門檻與長 cooldown 拖住，避免像截圖那樣
# 暖場 5 張的區累積到 ~150 張仍不整理）。保守取 3x 以免小波動就打擾。
_VOLUME_SOFT_CAP_FACTOR = 3
_VOLUME_OVERFLOW_COOLDOWN = 300.0


def _resolve_target_count(sub_phase_id: str) -> int | None:
    """回傳該 sub-phase 的 target_count（軟上限）；未知 / 無設定 → None。"""
    if not sub_phase_id:
        return None
    try:
        from app.stages.sub_phases import get_sub_phase

        return get_sub_phase(sub_phase_id).target_count
    except (KeyError, AttributeError):
        return None


@dataclass
class AssessResult:
    decision: DecisionType
    rule: str          # e.g. "rule_1_mention", "rule_8_default"
    details: dict = field(default_factory=dict)


class AssessEngine:
    """Rule engine with LLM-enhanced semantic judgments.

    Rules are evaluated in strict priority order (1–8).
    Semantic judgments (stance detection, topic relevance) use LLM
    with heuristic fallback when LLM is unavailable.
    """

    async def evaluate(
        self,
        context: dict,
        agent_id: str,
        ai_contribution: str = "medium",
        last_action_time: float | None = None,
        last_idle_event_time: float | None = None,
        another_agent_acting: bool = False,
        throttle_min_interval: float = 8.0,
        llm_ctx: "LLMCallContext | None" = None,
        controller: TurnController | None = None,
    ) -> AssessResult:
        """Evaluate rules and return an AssessResult."""
        now = time.time()
        recent_chat: list[dict] = context.get("recent_chat", [])
        my_seat: str = context.get("my_seat", "")

        # Phase strategy info (Phase 13)
        phase_strategy = context.get("phase_strategy", {})
        comm_strategy = phase_strategy.get("comm_strategy", "")
        comm_goal = phase_strategy.get("comm_goal", "")
        supervisor_mode = phase_strategy.get("supervisor_mode", "")
        is_supervisor = "supervisor" in my_seat.lower()

        # Phase 28：所有 AssessResult 帶上 turn_policy，方便 trace 對齊論文分析。
        policy_value = controller.policy.value if controller else "cued"

        def _result(
            decision: DecisionType, rule: str, details: dict
        ) -> AssessResult:
            tagged = {**details, "turn_policy": policy_value}
            return AssessResult(decision=decision, rule=rule, details=tagged)

        # Spec 13 — Sticky-Only Strategy: comm_mode gate (highest priority)
        # 注意：comm_mode 真正的「允許哪些 action」限制在 Act layer 強制（見 act.py），
        # 這裡只負責 reveal_round 的輪序判斷（必須在 ASSESS 階段就 yield，否則該 agent 會發起無效 LLM 呼叫）。
        comm_mode = context.get("comm_mode", "discussion")

        if comm_mode == "reveal_round":
            # Phase 28：1.1c phase machine 仍主導 reveal_queue；但底層改用
            # TurnController 來判斷「現在是不是我的回合」。RoundRobinPolicy 是 wrap
            # reveal_queue.peek_next_seat 的最小 façade，所以 1.1c 行為完全不變；
            # 其他場域 (教師全域切到 Round-Robin) 也可以共用同一條路徑。
            if controller is not None and controller.policy == TurnPolicy.ROUND_ROBIN:
                turn_decision = await controller.is_my_turn(my_seat, context)
                if not turn_decision.can_act:
                    return _result(
                        "wait",
                        "rule_0_2_reveal_not_my_turn",
                        {
                            "reason": (
                                f"揭示輪：等待 {turn_decision.next_speaker} 唸出，"
                                "目前不是你的回合"
                            ),
                            "next_seat": turn_decision.next_speaker,
                        },
                    )
            else:
                reveal_queue = context.get("reveal_queue", [])
                if reveal_queue:
                    next_seat = reveal_queue[0]
                    if my_seat != next_seat:
                        return _result(
                            "wait",
                            "rule_0_2_reveal_not_my_turn",
                            {
                                "reason": f"揭示輪：等待 {next_seat} 唸出，目前不是你的回合",
                                "next_seat": next_seat,
                            },
                        )

        # Rule 0.3: Supervisor awaiting crew reply (Fix #1)
        # Supervisor 點名某 crew 後，鎖 45s 或直到 crew 回覆，避免連續搶話。
        if is_supervisor:
            project_id = context.get("_project_id")
            if project_id is not None:
                try:
                    from app.agents.supervisor.awaiting_reply import check_awaiting_reply
                    awaited = await check_awaiting_reply(project_id, recent_chat)
                    if awaited is not None:
                        return AssessResult(
                            decision="wait",
                            rule="rule_0_3_awaiting_reply",
                            details={
                                "reason": f"等待 {awaited.display_name}（{awaited.seat_role}）回應",
                                "awaited_seat": awaited.seat_role,
                            },
                        )
                except Exception:
                    logger.debug("awaiting-reply check failed", exc_info=True)

        # Rule 0.8b: 暖場已有人回答後，組長別再對同一人連續催（修「還沒聽到你的點子」洗版 3+ 遍）。
        # 人一旦開口，若上一則就是組長自己（＝要連兩次發話、中間沒人回應）→ 先等，把球留給參與者；
        # 出現新的人類/crew 發言（上一則非組長）即解除，組長可接話或邀下一位。Rule 0.3 的 awaiting
        # 鎖在暖場常因沒喊到名字而未設定 → 這條不依賴鎖、直接兜住連續催。僅 0.0a + supervisor 套用。
        if (
            (context.get("current_sub_phase") or "").strip() == "0.0a"
            and is_supervisor
            and recent_chat
        ):
            human_spoke = any(m.get("sender_type") == "human" for m in recent_chat)
            last_is_supervisor = (
                "supervisor" in str(recent_chat[-1].get("sender_id", "")).lower()
            )
            if human_spoke and last_is_supervisor:
                return _result(
                    "wait",
                    "rule_0_8b_warmup_cue_satisfied",
                    {"reason": "暖場：人已經回答了，先別重複催同一個人，把空間留給大家"},
                )

        # Rule 0: Turn Gate — Phase 28+ 泛化到三個 policy（cued / round_robin /
        # open_floor）。由 TurnController.is_my_turn 統一決定「現在輪到誰」：
        #   - cued：supervisor 恆 True、被點名 crew（含 all_crew）True、其餘 wait
        #   - round_robin：依 reveal_queue 隊首，非隊首一律 wait（含 supervisor）
        #   - open_floor：預設 True，僅在他人 raise_hand 時非優先席位 wait
        # 此 gate 取代舊版「只 cued、且有 last_sender_is_supervisor 例外」的漏洞，
        # 確保 reactive / relevance 規則無法繞過輪流規則。
        if controller is not None:
            turn_decision = await controller.is_my_turn(my_seat, context)
            if not turn_decision.can_act:
                # cued：同一 tick 被 @mention 即視為點名信號 → 放行（點名機制；
                # 此時 invited_speaker 可能尚未寫入 blackboard）。RR / OF 不放行，
                # 避免 mention 成為繞過輪流的後門。
                cued_mention_override = (
                    controller.policy == TurnPolicy.CUED
                    and self._is_mentioned(
                        recent_chat, agent_id, my_seat, context.get("seats")
                    )
                )
                if not cued_mention_override:
                    return _result(
                        "wait",
                        "rule_0_turn_gate",
                        {
                            "reason": "輪流規則：目前不是你的回合",
                            "policy": controller.policy.value,
                            "controller_reason": turn_decision.reason,
                            "next_seat": turn_decision.next_speaker,
                        },
                    )

        # Rule 0.8（v2.0, Phase 42 A2，spec 20 v2.0 §11.5）：回合鎖在 ASSESS 的執行點。
        # 由 v1.0「暖場人類第一次發言前 crew 一律 wait（僅 0.0a）」**泛化**為「每回合
        # 重新上鎖」（全 sub-phase 適用）：本回合此 crew 已輸出過、或全員輪過正等真人
        # （waiting_for_human）→ 擋下。回合鎖以真人在席與否判定，全 AI 房恆不擋。
        # 組長（supervisor）豁免——凍結期間仍可發引導/提醒/教練訊息（§11.6）。
        # 舊「真人第一次發言後整關放行」行為不得殘留（§11.5）。
        if not is_supervisor:
            _rl_project_id = context.get("_project_id")
            _rl_sub_phase = (context.get("current_sub_phase") or "").strip()
            if _rl_project_id is not None and _rl_sub_phase:
                from app.agents.round_lock import is_crew_blocked

                _blocked, _reason_zh = await is_crew_blocked(
                    _rl_project_id, _rl_sub_phase, my_seat
                )
                if _blocked:
                    return _result(
                        "wait",
                        "rule_0_8_round_lock",
                        {"reason": _reason_zh or "回合鎖：先把空間留給使用者"},
                    )

        # Rule 0.5: Debate Stance — debate/competition 模式下不同維度 Crew boost
        # 先用 LLM 處理，未來可規則化
        if comm_goal in ("debate", "mild_competition") and not is_supervisor:
            if len(recent_chat) >= 1:
                has_stance = await self._has_stance_in_recent(recent_chat[-3:], my_seat, llm_ctx=llm_ctx)
                if has_stance:
                    return AssessResult(
                        decision="intervene",
                        rule="rule_0_5_debate_stance",
                        details={"reason": "辯論模式：不同維度的觀點需要回應", "boost": 0.30},
                    )

        # Rule 0.1: Fresh project bootstrap — supervisor must greet first
        if is_supervisor and not recent_chat:
            return AssessResult(
                decision="intervene",
                rule="rule_0_1_fresh_project",
                details={"reason": "全新專案：Supervisor 引導開場"},
            )

        # Rule 1: @mention 或被點名 — Phase 28：只在 Cued 模式視為 intervene 信號。
        # Round-Robin / Open-Floor 由各自的 cooldown / queue 控制節奏，避免 mention
        # 變成繞過輪流規則的後門。
        if self._is_mentioned(
            recent_chat, agent_id, my_seat, context.get("seats")
        ):
            if controller is None or controller.policy == TurnPolicy.CUED:
                return _result(
                    "intervene",
                    "rule_1_mention",
                    {"reason": "直接被點名或提問"},
                )

        # Rule 2: Human typing in the last 3 seconds
        if self._human_typing_recently(context):
            return AssessResult(
                decision="wait",
                rule="rule_2_human_typing",
                details={"reason": "有人類正在輸入"},
            )

        # Rule 2.5（多訊息連發 debounce）：人類最近 ~2s 內發過群組訊息 → 先等。
        # typing 指示只在「打字中」有效、訊息送出後即失效，連發第 2 則距第 1 則 0.5s 就不被
        # Rule 2 擋；本規則讓 agent 等連發停了再回**最後一則**（打錯字訂正一次回應，不對每個
        # 中間則各回一次）。回 "wait"（非 intervene）故不經 reactive/cooldown 閘。
        if self._human_messaged_recently(context):
            return AssessResult(
                decision="wait",
                rule="rule_2_5_human_message_recent",
                details={"reason": "使用者剛發訊息，稍候可能的後續（連發 debounce）"},
            )

        # Rule 3: Another AI agent is currently acting
        if another_agent_acting:
            return AssessResult(
                decision="wait",
                rule="rule_3_agent_acting",
                details={"reason": "另一個 AI Agent 正在執行行動"},
            )

        # Rule 4: Throttle minimum interval not reached
        if last_action_time is not None:
            elapsed = now - last_action_time
            if elapsed < throttle_min_interval:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_throttle",
                    details={
                        "elapsed_seconds": round(elapsed, 1),
                        "min_interval": throttle_min_interval,
                    },
                )

        # Rule 4.5: Consecutive AI message limit (spec §5.2, §6)
        seats: list[dict] = context.get("seats", [])
        has_human_seat = any(s.get("type") == "human" for s in seats)
        # Check if humans are actively chatting (not just sitting)
        human_chatted = any(
            m.get("sender_type") == "human" for m in recent_chat[-10:]
        ) if recent_chat else False
        consecutive_ai = self._count_trailing_ai_messages(recent_chat)
        if has_human_seat and human_chatted:
            # Humans are actively participating — respect strict limits
            ai_limit = 5 if is_supervisor else 3
            if consecutive_ai >= ai_limit:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_consecutive_ai_limit",
                    details={
                        "consecutive_ai_messages": consecutive_ai,
                        "reason": f"連續 AI 訊息已達 {ai_limit} 則上限，等待人類發言",
                    },
                )
        else:
            # All-AI mode (or human seated but not chatting, or observer-only)
            # Only limit per-agent spam — do NOT permanently block all agents.
            # The proactive cooldown budget (Solution C) already rate-limits overall.
            same_agent_consecutive = self._count_trailing_same_agent(recent_chat, my_seat)
            if same_agent_consecutive >= 4:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_same_agent_limit",
                    details={"reason": "同一 agent 連續 4 則，讓其他成員發言"},
                )

        # Rule X: Canvas orderliness trigger (Phase 14, enhanced Phase 15)
        canvas_summary = context.get("canvas_state", {}).get("summary")
        if canvas_summary and canvas_summary.get("total_notes", 0) > 8:
            orderliness = canvas_summary.get("orderliness_score", 1.0)
            last_tidy = context.get("_last_tidy_time")
            total_notes = canvas_summary.get("total_notes", 0)

            # 病根 D 軟護欄：便條數超過該 sub-phase 的 target_count 軟上限（×係數）→ 量爆掉，
            # 觸發整理。獨立於 orderliness（即使分數尚可，過量本身就該整理/併同類）。
            sub_phase_id = (context.get("current_sub_phase") or "").strip()
            target_count = _resolve_target_count(sub_phase_id)
            if (
                target_count
                and total_notes >= target_count * _VOLUME_SOFT_CAP_FACTOR
                and (last_tidy is None or (now - last_tidy) > _VOLUME_OVERFLOW_COOLDOWN)
            ):
                return AssessResult(
                    decision="intervene",
                    rule="rule_x_volume_overflow",
                    details={
                        "reason": "便條數超過該階段軟上限，需整理 / 併同類",
                        "total_notes": total_notes,
                        "target_count": target_count,
                        "sub_phase": sub_phase_id,
                    },
                )

            micro_phase = context.get("current_micro_phase", "")
            # First-diamond micro_phases only（Phase 42 C1：新 6 桶，舊 1.3 移除）.
            _ORDERLINESS_THRESHOLDS: dict[str, float] = {
                "1.1": 0.25, "1.2": 0.25,
                "2.1": 0.40, "2.2": 0.45, "2.3": 0.50,
            }
            threshold = _ORDERLINESS_THRESHOLDS.get(micro_phase, 0.45)

            _DIVERGE_PHASES = frozenset(("1.1", "1.2"))
            cooldown = 600 if micro_phase in _DIVERGE_PHASES else 300

            if orderliness < threshold and (last_tidy is None or (now - last_tidy) > cooldown):
                return AssessResult(
                    decision="intervene",
                    rule="rule_x_canvas_untidy",
                    details={
                        "reason": "白板凌亂度高",
                        "orderliness_score": orderliness,
                        "threshold": threshold,
                        "micro_phase": micro_phase,
                    },
                )

        # Rule 5: Canvas/chat idle beyond threshold
        role_status = context.get("my_role_status", "normal")
        idle_threshold = _IDLE_THRESHOLDS.get(ai_contribution, 30.0)
        if role_status == "suppressed":
            idle_threshold *= 2.0
        if last_idle_event_time is not None:
            idle_seconds = now - last_idle_event_time
            if idle_seconds > idle_threshold:
                return AssessResult(
                    decision="intervene",
                    rule="rule_5_idle",
                    details={
                        "idle_seconds": round(idle_seconds, 1),
                        "threshold": idle_threshold,
                    },
                )

        # Rule 5.5: Re-engagement + Peer Relevance Trigger
        # 先用 LLM 處理，未來可規則化
        blackboard = context.get("blackboard", {})
        my_actions: list[dict] = context.get("my_recent_actions", [])
        if my_actions and blackboard.get("other_agent_intentions"):
            my_last_content = my_actions[-1].get("content", "")
            if my_last_content:
                for intent in blackboard["other_agent_intentions"]:
                    other_topic = intent.get("focus_topic", "")
                    if other_topic and await self._topic_overlap(other_topic, my_last_content, llm_ctx=llm_ctx):
                        return AssessResult(
                            decision="intervene",
                            rule="rule_5_5_reengagement",
                            details={"reason": f"話題相關：{other_topic}"},
                        )
        if recent_chat and my_actions and not is_supervisor:
            my_last_content = my_actions[-1].get("content", "")
            if my_last_content:
                for msg in recent_chat[-3:]:
                    sender = msg.get("sender", "")
                    sender_type = msg.get("sender_type", "")
                    if my_seat.lower() not in sender.lower() and "ai" in str(sender_type).lower():
                        msg_content = msg.get("content", "")
                        if msg_content and await self._topic_overlap(msg_content, my_last_content, llm_ctx=llm_ctx):
                            return AssessResult(
                                decision="intervene",
                                rule="rule_5_5_peer_relevance",
                                details={"reason": f"回應 {sender} 的觀點（語義相關）"},
                            )

        # Rule 6: New event is highly relevant (n-gram overlap, not single-char)
        if has_relevant_event_ngram(context):
            return AssessResult(
                decision="intervene",
                rule="rule_6_relevant_event",
                details={"reason": "新事件與我最近的發言高度相關"},
            )

        # Rule 6.4: Short-message one-responder gate
        recent_chat = context.get("recent_chat", [])
        if recent_chat:
            last_msg = recent_chat[-1]
            last_content = last_msg.get("content", "")
            last_sender_type = last_msg.get("sender_type", last_msg.get("sender", ""))
            is_human_msg = "human" in str(last_sender_type).lower()
            is_short = len(last_content.strip()) <= 6 and "？" not in last_content and "?" not in last_content
            if is_human_msg and is_short:
                ai_responses_after = 0
                for msg in reversed(recent_chat[:-1]) if len(recent_chat) > 1 else []:
                    sender = msg.get("sender_type", msg.get("sender", ""))
                    if "ai" in str(sender).lower():
                        ai_responses_after += 1
                    else:
                        break
                if ai_responses_after >= 1:
                    return AssessResult(
                        decision="wait",
                        rule="rule_6_4_short_msg_gate",
                        details={"reason": f"簡短訊息「{last_content}」已有 AI 回應，不重複"},
                    )

        # Rule 6.6: Supervisor Silent Mode
        if is_supervisor and supervisor_mode == "silent":
            idle_seconds_for_silent = 0.0
            if last_idle_event_time is not None:
                idle_seconds_for_silent = now - last_idle_event_time
            if idle_seconds_for_silent < idle_threshold:
                return AssessResult(
                    decision="observe",
                    rule="rule_6_6_supervisor_silent",
                    details={"reason": "沉默觀察模式：尚未冷場"},
                )

        # Rule 6.5: Topic Focus Gate
        active_thread = context.get("active_thread")
        if active_thread and active_thread.get("turn_count", 0) < 7:
            participants = active_thread.get("participants", [])
            pending = active_thread.get("pending_addressee")
            am_participant = any(my_seat.lower() in p.lower() for p in participants)
            am_addressed = bool(pending and my_seat.lower() in str(pending).lower())
            if not am_participant and not am_addressed:
                if comm_strategy == "simultaneous":
                    yield_probability = 0.20
                elif comm_strategy == "one_by_one":
                    yield_probability = 0.70
                else:
                    yield_probability = 0.50
                if random.random() < yield_probability:
                    return AssessResult(
                        decision="wait",
                        rule="rule_6_5_topic_focus",
                        details={"reason": "目前有活躍討論串，尚未參與，暫不介入"},
                    )

        # Rule 7: Thread-aware intervention
        prob = _INTERVENTION_PROBABILITIES.get(ai_contribution, 0.50)
        if is_supervisor:
            prob = min(1.0, prob * 1.3)
        if comm_goal in ("debate", "mild_competition"):
            prob = min(1.0, prob * 1.3)

        if active_thread:
            pending = active_thread.get("pending_addressee")
            if pending and my_seat.lower() in str(pending).lower():
                return AssessResult(
                    decision="intervene",
                    rule="rule_7_addressed",
                    details={"reason": "被點名應回應"},
                )
            if pending and my_seat.lower() not in str(pending).lower():
                return AssessResult(
                    decision="wait",
                    rule="rule_7_yield",
                    details={"reason": f"等待 {pending} 回應"},
                )
            addressed_to = active_thread.get("addressed_to")
            if addressed_to and my_seat.lower() in str(addressed_to).lower():
                return AssessResult(
                    decision="intervene",
                    rule="rule_7_addressed",
                    details={"reason": "被點名應回應"},
                )
            if addressed_to and my_seat.lower() not in str(addressed_to).lower():
                return AssessResult(
                    decision="wait",
                    rule="rule_7_yield",
                    details={"reason": f"等待 {addressed_to} 回應"},
                )
            turn_count = active_thread.get("turn_count", 0)
            role_status = context.get("my_role_status", "normal")
            if role_status == "suppressed":
                prob *= 0.6
            elif role_status == "protagonist":
                prob = min(1.0, prob * 1.4)
            elif turn_count >= 6:
                # Softer decay when human is silent or absent, to keep crew active
                human_chatting_r7 = any(
                    m.get("sender_type") == "human" for m in recent_chat[-10:]
                )
                prob *= 0.5 if human_chatting_r7 else 0.7
            else:
                prob *= 0.7
        else:
            role_status = context.get("my_role_status", "normal")
            if role_status == "protagonist":
                prob = min(1.0, prob * 1.4)
            elif role_status == "suppressed":
                prob *= 0.6

        if random.random() < prob:
            return AssessResult(
                decision="intervene",
                rule="rule_7_thread_aware",
                details={"probability": round(prob, 2), "contribution": ai_contribution},
            )

        # Rule 8: Default — observe
        return AssessResult(
            decision="observe",
            rule="rule_8_default",
            details={"reason": "以上規則皆不觸發，保持觀察"},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # Legacy display name mapping kept for backward compatibility.
    # Phase 19: persona-based name is preferred via ``context["seats"]``.
    _DISPLAY_NAMES: dict[str, str] = {
        "supervisor": "ai 引導者",
        "crew_1": "ai 同理心專家",
        "crew_2": "ai 結構化專家",
        "crew_3": "ai 創意專家",
        "crew_4": "ai 可行性專家",
    }

    def _is_mentioned(
        self,
        recent_chat: list[dict],
        agent_id: str,
        seat_role: str,
        seats: list[dict] | None = None,
    ) -> bool:
        """Return True if the most recent chat message mentions this agent."""
        if not recent_chat:
            return False
        last_msg = recent_chat[-1]
        content: str = last_msg.get("content", "").lower()
        targets = [
            f"@{agent_id.lower()}",
            f"@{seat_role.lower()}",
            seat_role.lower(),
        ]
        # Phase 19: prefer persona.name from seats
        persona_name = ""
        if seats:
            for s in seats:
                role = s.get("role") or s.get("seat_role")
                if role == seat_role:
                    persona = s.get("persona") if isinstance(s, dict) else None
                    if isinstance(persona, dict):
                        persona_name = str(persona.get("name", "")).strip().lower()
                    if not persona_name:
                        dn = s.get("display_name", "")
                        if dn:
                            persona_name = str(dn).lower()
                    break
        if persona_name:
            targets.append(persona_name)
        # Legacy display name fallback
        legacy = self._DISPLAY_NAMES.get(seat_role, "")
        if legacy:
            targets.append(legacy)
        return any(t in content for t in targets if t.strip("@"))

    def _human_typing_recently(self, context: dict) -> bool:
        """Return True if a typing indicator was received within 3 seconds."""
        typing_ts: float | None = context.get("_human_typing_timestamp")
        if typing_ts is None:
            return False
        return (time.time() - typing_ts) < 3.0

    # 連發 debounce 窗：略大於 chat_ws 的 _HUMAN_INPUT_DEBOUNCE_SECONDS(1.5s)，
    # 確保回合鎖那一側先處理完最後一則，agent 才接話。
    _HUMAN_MSG_DEBOUNCE_SECONDS = 2.0

    def _human_messaged_recently(self, context: dict) -> bool:
        """Return True if a human sent a group message within the burst-debounce window.

        讀 ``_human_last_message_timestamp``（chat_ws group 分支寫的 human_last_msg_ts）。
        讓 agent 等使用者連發停了再回最後一則（Rule 2.5）。
        """
        msg_ts: float | None = context.get("_human_last_message_timestamp")
        if msg_ts is None:
            return False
        return (time.time() - msg_ts) < self._HUMAN_MSG_DEBOUNCE_SECONDS

    def _count_trailing_ai_messages(self, recent_chat: list[dict]) -> int:
        count = 0
        for msg in reversed(recent_chat):
            sender_type = msg.get("sender_type", msg.get("type", ""))
            if sender_type == "ai":
                count += 1
            else:
                break
        return count

    def _count_trailing_same_agent(self, recent_chat: list[dict], my_seat: str) -> int:
        count = 0
        my_seat_lower = my_seat.lower()
        for msg in reversed(recent_chat):
            sender = msg.get("sender", "")
            if my_seat_lower in sender.lower():
                count += 1
            else:
                break
        return count

    async def _topic_overlap(
        self,
        text_a: str,
        text_b: str,
        *,
        llm_ctx: LLMCallContext | None = None,
    ) -> bool:
        """Return True if two texts are topically related.

        Falls back to a heuristic n-gram check when ``llm_ctx`` is missing
        (so the engine still works in tests / non-agent contexts).
        """
        ngrams_a = extract_cjk_ngrams(text_a)
        ngrams_b = extract_cjk_ngrams(text_b)
        if not ngrams_a or not ngrams_b:
            return False
        if llm_ctx is None:
            return len(ngrams_a & ngrams_b) >= 4
        try:
            llm_service = LLMProviderFactory.get_service()
            response = await llm_service.chat_completion(
                messages=[
                    {"role": "system", "content": "你是文字分析助手。"},
                    {"role": "user", "content": (
                        "以下兩段文字的主題相關度是高/中/低？只回答 high/medium/low\n\n"
                        f"文字A：{text_a[:200]}\n文字B：{text_b[:200]}"
                    )},
                ],
                temperature=0.0,
                max_tokens=10,
                caller="assess_topic_overlap",
                owning_user_id=llm_ctx.owning_user_id,
                project_id=llm_ctx.project_id,
            )
            return "high" in response.content.lower()
        except Exception:
            logger.debug("_topic_overlap LLM fallback to heuristic")
            return len(ngrams_a & ngrams_b) >= 4

    async def _has_stance_in_recent(
        self,
        messages: list[dict],
        my_seat: str,
        *,
        llm_ctx: LLMCallContext | None = None,
    ) -> bool:
        """Check if recent messages contain a stance from a different agent.

        # 先用 LLM 處理，未來可規則化
        """
        candidates: list[str] = []
        for msg in messages:
            sender = msg.get("sender", "")
            sender_type = msg.get("sender_type", "")
            if my_seat.lower() in sender.lower():
                continue
            if "ai" not in str(sender_type).lower():
                continue
            content = msg.get("content", "")
            if content:
                candidates.append(content)
        if not candidates:
            return False
        combined = "\n---\n".join(c[:150] for c in candidates)
        if llm_ctx is None:
            return heuristic_has_stance(candidates)
        try:
            llm_service = LLMProviderFactory.get_service()
            response = await llm_service.chat_completion(
                messages=[
                    {"role": "system", "content": "你是文字分析助手。"},
                    {"role": "user", "content": (
                        "以下訊息中是否有任何一則包含明確的觀點立場？"
                        "只回答 true 或 false\n\n"
                        f"{combined}"
                    )},
                ],
                temperature=0.0,
                max_tokens=10,
                caller="assess_stance",
                owning_user_id=llm_ctx.owning_user_id,
                project_id=llm_ctx.project_id,
            )
            return "true" in response.content.lower()
        except Exception:
            logger.debug("_has_stance_in_recent LLM fallback to heuristic")
            return heuristic_has_stance(candidates)
