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
        # In normal mode (humans present), at most 3 consecutive AI messages are allowed.
        # After 3, the agent must wait for a non-AI message before acting again.
        seats: list[dict] = context.get("seats", [])
        has_humans = any(s.get("type") == "human" for s in seats)
        if has_humans:
            consecutive_ai = self._count_trailing_ai_messages(recent_chat)
            if consecutive_ai >= 3:
                return AssessResult(
                    decision="wait",
                    rule="rule_4_5_consecutive_ai_limit",
                    details={
                        "consecutive_ai_messages": consecutive_ai,
                        "reason": "連續 AI 訊息已達 3 則上限，等待人類或其他成員發言",
                    },
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

        # Rule 6: New event is highly relevant to this agent's recent actions
        if self._has_relevant_event(context, my_seat):
            return AssessResult(
                decision="intervene",
                rule="rule_6_relevant_event",
                details={"reason": "新事件與我最近的發言或操作高度相關"},
            )

        # Rule 7: Probabilistic intervention based on contribution level
        prob = _INTERVENTION_PROBABILITIES.get(ai_contribution, 0.50)

        # Boost Supervisor probability in Discover early sub-phase (Kaner Diamond)
        current_stage = context.get("current_stage", "")
        if current_stage == "discover" and "supervisor" in str(context.get("my_seat", "")).lower():
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
                rule="rule_7_probabilistic",
                details={"probability": prob, "contribution": ai_contribution},
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

    def _has_relevant_event(self, context: dict, my_seat: str) -> bool:
        """Return True if the latest chat message references this agent's recent content."""
        my_actions: list[dict] = context.get("my_recent_actions", [])
        if not my_actions:
            return False
        recent_chat: list[dict] = context.get("recent_chat", [])
        if not recent_chat:
            return False

        # Collect keywords from my last action
        last_action = my_actions[-1]
        my_content: str = last_action.get("content", "").lower()
        if not my_content:
            return False

        # Simple keyword overlap check using CJK characters
        my_words = set(c for c in my_content if "\u4e00" <= c <= "\u9fff")
        if len(my_words) < 3:
            return False

        last_chat_content = recent_chat[-1].get("content", "").lower()
        chat_words = set(c for c in last_chat_content if "\u4e00" <= c <= "\u9fff")

        overlap = my_words & chat_words
        return len(overlap) >= 3
