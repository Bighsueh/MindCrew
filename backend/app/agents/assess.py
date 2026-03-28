from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Literal

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
    """Lightweight rule engine that decides whether an agent should act.

    Rules are evaluated in strict priority order (1–8).
    No LLM calls are made here.
    """

    def evaluate(
        self,
        context: dict,
        agent_id: str,
        ai_contribution: str = "medium",
        last_action_time: float | None = None,
        last_idle_event_time: float | None = None,
        another_agent_acting: bool = False,
        throttle_min_interval: float = 8.0,
    ) -> AssessResult:
        """Evaluate rules and return an AssessResult.

        Args:
            context: The context buffer dict.
            agent_id: This agent's identifier (used to detect @mention).
            ai_contribution: "low" | "medium" | "high"
            last_action_time: Unix timestamp of the agent's last action.
            last_idle_event_time: Unix timestamp of last canvas/chat event.
            another_agent_acting: True if another AI agent is currently executing.
            throttle_min_interval: Minimum seconds between actions for this level.
        """
        now = time.time()
        recent_chat: list[dict] = context.get("recent_chat", [])
        my_seat: str = context.get("my_seat", "")

        # Rule 0: Supervisor Coordination Directive (hard constraint for Crew)
        directive = context.get("blackboard", {}).get("coordination_directive")
        if directive and "supervisor" not in my_seat.lower():
            invited = directive.get("invited_speaker", "")
            if invited:
                if my_seat.lower() in invited.lower():
                    return AssessResult(
                        decision="intervene",
                        rule="rule_0_invited",
                        details={"reason": "Supervisor 邀請你發言"},
                    )
                else:
                    return AssessResult(
                        decision="wait",
                        rule="rule_0_not_invited",
                        details={"reason": f"Supervisor 指定 {invited} 發言"},
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
        # With humans: max 3 consecutive AI messages (Supervisor: 5)
        # All-AI mode: same agent max 2 consecutive; total max 6 consecutive
        seats: list[dict] = context.get("seats", [])
        has_humans = any(s.get("type") == "human" for s in seats)
        is_supervisor = "supervisor" in my_seat.lower()
        consecutive_ai = self._count_trailing_ai_messages(recent_chat)
        if has_humans:
            # Supervisor has relaxed limit (5) to maintain facilitation ability
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
            # All-AI mode: prevent same agent from dominating
            same_agent_consecutive = self._count_trailing_same_agent(recent_chat, my_seat)
            if same_agent_consecutive >= 2:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_same_agent_limit",
                    details={"reason": "同一 agent 連續 2 則，讓其他成員發言"},
                )
            if consecutive_ai >= 6:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_all_ai_limit",
                    details={"reason": "全 AI 模式連續 6 則，暫停一輪"},
                )

        # Rule 5: Canvas/chat idle beyond threshold
        idle_threshold = _IDLE_THRESHOLDS.get(ai_contribution, 30.0)
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

        # Rule 5.5: Re-engagement — topic overlap with other agents' intentions
        blackboard = context.get("blackboard", {})
        my_actions: list[dict] = context.get("my_recent_actions", [])
        if my_actions and blackboard.get("other_agent_intentions"):
            my_last_content = my_actions[-1].get("content", "")
            if my_last_content:
                for intent in blackboard["other_agent_intentions"]:
                    other_topic = intent.get("focus_topic", "")
                    if other_topic and self._topic_overlap(other_topic, my_last_content):
                        return AssessResult(
                            decision="intervene",
                            rule="rule_5_5_reengagement",
                            details={"reason": f"話題相關：{other_topic}"},
                        )

        # Rule 6: New event is highly relevant (n-gram overlap, not single-char)
        if self._has_relevant_event_ngram(context):
            return AssessResult(
                decision="intervene",
                rule="rule_6_relevant_event",
                details={"reason": "新事件與我最近的發言高度相關"},
            )

        # Rule 6.5: Topic Focus Gate — suppress off-topic proactive initiation
        active_thread = context.get("active_thread")
        if active_thread and active_thread.get("turn_count", 0) < 7:
            participants = active_thread.get("participants", [])
            pending = active_thread.get("pending_addressee")
            am_participant = any(my_seat.lower() in p.lower() for p in participants)
            am_addressed = bool(pending and my_seat.lower() in str(pending).lower())
            if not am_participant and not am_addressed:
                if random.random() > 0.20:  # 80% chance to yield
                    return AssessResult(
                        decision="wait",
                        rule="rule_6_5_topic_focus",
                        details={"reason": "目前有活躍討論串，尚未參與，暫不介入"},
                    )

        # Rule 7: Thread-aware intervention (replaces pure probabilistic)
        prob = _INTERVENTION_PROBABILITIES.get(ai_contribution, 0.50)
        # Supervisor gets a 30% boost — it has facilitation responsibility
        if is_supervisor:
            prob = min(1.0, prob * 1.3)

        if active_thread:
            # Check persistent addressee (survives intervening messages)
            pending = active_thread.get("pending_addressee")
            if pending and my_seat.lower() in str(pending).lower():
                # I was asked a question — must respond
                return AssessResult(
                    decision="intervene",
                    rule="rule_7_addressed",
                    details={"reason": "被點名應回應"},
                )
            if pending and my_seat.lower() not in str(pending).lower():
                # Someone else was addressed and hasn't responded yet — yield
                return AssessResult(
                    decision="wait",
                    rule="rule_7_yield",
                    details={"reason": f"等待 {pending} 回應"},
                )
            # Fall back to current message addressee (for non-persistent cases)
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
            if turn_count >= 6:
                prob *= 0.5  # Mature thread — allow new voices at reduced rate
            else:
                prob *= 0.6  # Active thread — reduce spray

        # Boost Supervisor in Discover early sub-phase (Kaner Diamond)
        current_stage = context.get("current_stage", "")
        if current_stage == "discover" and "supervisor" in my_seat.lower():
            from app.agents.prompts.discover_subphase import (
                DiscoverSubPhase,
                determine_discover_subphase,
            )
            subphase = determine_discover_subphase(
                context.get("canvas_state", {}),
                context.get("recent_chat", []),
                context.get("stage_duration_minutes", 0),
            )
            if subphase == DiscoverSubPhase.EARLY:
                prob = min(1.0, prob * 1.5)

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
        self, recent_chat: list[dict], agent_id: str, seat_role: str
    ) -> bool:
        """Return True if the most recent chat message mentions this agent."""
        if not recent_chat:
            return False
        last_msg = recent_chat[-1]
        content: str = last_msg.get("content", "").lower()
        # Match @agent_id, @seat_role, or just the seat role name
        targets = [
            f"@{agent_id.lower()}",
            f"@{seat_role.lower()}",
            seat_role.lower(),
        ]
        return any(t in content for t in targets if t.strip("@"))

    def _human_typing_recently(self, context: dict) -> bool:
        """Return True if a typing indicator was received within 3 seconds."""
        typing_ts: float | None = context.get("_human_typing_timestamp")
        if typing_ts is None:
            return False
        return (time.time() - typing_ts) < 3.0

    def _count_trailing_ai_messages(self, recent_chat: list[dict]) -> int:
        """Count the number of consecutive AI messages at the tail of recent_chat."""
        count = 0
        for msg in reversed(recent_chat):
            sender_type = msg.get("sender_type", msg.get("type", ""))
            if sender_type == "ai":
                count += 1
            else:
                break
        return count

    def _count_trailing_same_agent(
        self, recent_chat: list[dict], my_seat: str,
    ) -> int:
        """Count consecutive messages from the same agent at tail of chat."""
        count = 0
        my_seat_lower = my_seat.lower()
        for msg in reversed(recent_chat):
            sender = msg.get("sender", "")
            if my_seat_lower in sender.lower():
                count += 1
            else:
                break
        return count

    def _has_relevant_event_ngram(self, context: dict) -> bool:
        """Return True if latest chat shares n-gram overlap with my recent action."""
        my_actions: list[dict] = context.get("my_recent_actions", [])
        if not my_actions:
            return False
        recent_chat: list[dict] = context.get("recent_chat", [])
        if not recent_chat:
            return False

        last_action = my_actions[-1]
        my_content: str = last_action.get("content", "")
        if not my_content:
            return False

        last_chat_content = recent_chat[-1].get("content", "")

        # Use 3-char n-grams instead of single characters
        my_ngrams = self._extract_cjk_ngrams(my_content)
        chat_ngrams = self._extract_cjk_ngrams(last_chat_content)

        if len(my_ngrams) < 2 or len(chat_ngrams) < 2:
            return False

        overlap = my_ngrams & chat_ngrams
        return len(overlap) >= 2

    @staticmethod
    def _extract_cjk_ngrams(text: str, n: int = 3) -> set[str]:
        """Extract character n-grams from CJK text."""
        cjk = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
        if len(cjk) < n:
            return set()
        return {cjk[i : i + n] for i in range(len(cjk) - n + 1)}

    @staticmethod
    def _topic_overlap(text_a: str, text_b: str) -> bool:
        """Return True if two texts share >= 2 CJK trigrams."""
        ngrams_a = AssessEngine._extract_cjk_ngrams(text_a)
        ngrams_b = AssessEngine._extract_cjk_ngrams(text_b)
        if not ngrams_a or not ngrams_b:
            return False
        return len(ngrams_a & ngrams_b) >= 2
