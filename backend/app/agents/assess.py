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

        # Rule 0: Strategy Gate — OO 策略下只有被 @mention 的人可行動
        if comm_strategy == "one_by_one" and not is_supervisor:
            last_sender_is_supervisor = False
            if recent_chat:
                last_sender = recent_chat[-1].get("sender", "")
                last_sender_is_supervisor = "supervisor" in last_sender.lower()
            am_mentioned = self._is_mentioned(recent_chat, agent_id, my_seat)
            if not last_sender_is_supervisor and not am_mentioned:
                return AssessResult(
                    decision="wait",
                    rule="rule_0_strategy_gate",
                    details={"reason": "OO 模式：等待 Supervisor 點名"},
                )

        # Rule 0.5: Debate Stance — debate/competition 模式下不同維度 Crew boost
        # 先用 LLM 處理，未來可規則化
        if comm_goal in ("debate", "mild_competition") and not is_supervisor:
            if len(recent_chat) >= 1:
                has_stance = await self._has_stance_in_recent(recent_chat[-3:], my_seat)
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

        # Rule 1: @mention or direct question to this agent
        if self._is_mentioned(recent_chat, agent_id, my_seat):
            return AssessResult(
                decision="intervene",
                rule="rule_1_mention",
                details={"reason": "直接被點名或提問"},
            )

        # Rule 2: Human typing in the last 3 seconds
        if self._human_typing_recently(context):
            return AssessResult(
                decision="wait",
                rule="rule_2_human_typing",
                details={"reason": "有人類正在輸入"},
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
        has_humans = any(s.get("type") == "human" for s in seats)
        consecutive_ai = self._count_trailing_ai_messages(recent_chat)
        if has_humans:
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
            same_agent_consecutive = self._count_trailing_same_agent(recent_chat, my_seat)
            if same_agent_consecutive >= 4:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_same_agent_limit",
                    details={"reason": "同一 agent 連續 4 則，讓其他成員發言"},
                )
            if consecutive_ai >= 15:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_all_ai_limit",
                    details={"reason": "全 AI 模式連續 15 則，暫停一輪"},
                )

        # Rule X: Canvas orderliness trigger (Phase 14, enhanced Phase 15)
        canvas_summary = context.get("canvas_state", {}).get("summary")
        if canvas_summary and canvas_summary.get("total_notes", 0) > 8:
            orderliness = canvas_summary.get("orderliness_score", 1.0)
            last_tidy = context.get("_last_tidy_time")

            micro_phase = context.get("current_micro_phase", "")
            _ORDERLINESS_THRESHOLDS: dict[str, float] = {
                "1.1": 0.25, "1.2": 0.25,
                "1.3": 0.50,
                "2.1": 0.40, "2.2": 0.45, "2.3": 0.50,
                "3.1": 0.20,
                "3.2": 0.50, "3.3": 0.55,
                "4.1": 0.40, "4.2": 0.45, "4.3": 0.45,
            }
            threshold = _ORDERLINESS_THRESHOLDS.get(micro_phase, 0.45)

            _DIVERGE_PHASES = frozenset(("1.1", "1.2", "3.1"))
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
                    if other_topic and await self._topic_overlap(other_topic, my_last_content):
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
                        if msg_content and await self._topic_overlap(msg_content, my_last_content):
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
                if comm_strategy in ("simultaneous", "simultaneous_summarizer"):
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
                prob *= 0.5
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

    def _is_mentioned(
        self, recent_chat: list[dict], agent_id: str, seat_role: str,
    ) -> bool:
        """Return True if the most recent chat message mentions this agent."""
        if not recent_chat:
            return False
        last_msg = recent_chat[-1]
        content: str = last_msg.get("content", "").lower()
        targets = [f"@{agent_id.lower()}", f"@{seat_role.lower()}", seat_role.lower()]
        return any(t in content for t in targets if t.strip("@"))

    def _human_typing_recently(self, context: dict) -> bool:
        """Return True if a typing indicator was received within 3 seconds."""
        typing_ts: float | None = context.get("_human_typing_timestamp")
        if typing_ts is None:
            return False
        return (time.time() - typing_ts) < 3.0

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

    async def _topic_overlap(self, text_a: str, text_b: str) -> bool:
        """Return True if two texts are topically related.

        # 先用 LLM 處理，未來可規則化
        """
        ngrams_a = extract_cjk_ngrams(text_a)
        ngrams_b = extract_cjk_ngrams(text_b)
        if not ngrams_a or not ngrams_b:
            return False
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
            )
            return "high" in response.content.lower()
        except Exception:
            logger.debug("_topic_overlap LLM fallback to heuristic")
            return len(ngrams_a & ngrams_b) >= 4

    async def _has_stance_in_recent(self, messages: list[dict], my_seat: str) -> bool:
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
            )
            return "true" in response.content.lower()
        except Exception:
            logger.debug("_has_stance_in_recent LLM fallback to heuristic")
            return heuristic_has_stance(candidates)
