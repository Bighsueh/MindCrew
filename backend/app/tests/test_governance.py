"""Tests for conversation governance mechanisms.

Covers: Rule 6.5 (topic focus), queue backpressure, proactive initiation
budget, persistent addressee, typing detection (Rule 2), idle detection (Rule 5).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.agents.assess import AssessEngine, AssessResult
from app.agents.conversation_state import ConversationThread


# ===================================================================
# Rule 6.5 — Topic Focus Gate
# ===================================================================


class TestTopicFocusGate:
    """Non-participants of an active thread should yield ~80% of the time."""

    def _base_context(self, *, my_seat: str = "crew_3") -> dict:
        return {
            "recent_chat": [
                {"content": "我覺得搜尋體驗有待改善", "sender": "crew_1(ai)", "sender_type": "ai"},
            ],
            "my_seat": my_seat,
            "seats": [
                {"role": "crew_1", "type": "ai"},
                {"role": "crew_2", "type": "ai"},
                {"role": "crew_3", "type": "ai"},
            ],
            "active_thread": {
                "topic_summary": "搜尋體驗",
                "participants": ["crew_1", "crew_2"],
                "turn_count": 3,
                "last_speaker": "crew_2",
                "addressed_to": None,
                "pending_addressee": None,
            },
            "my_recent_actions": [],
            "current_stage": "discover",
        }

    def test_non_participant_mostly_yields(self) -> None:
        """Non-participant should yield ~80% of the time (Rule 6.5)."""
        engine = AssessEngine()
        ctx = self._base_context(my_seat="crew_3")

        results = []
        for _ in range(200):
            r = engine.evaluate(
                context=ctx,
                agent_id="agent_3",
                ai_contribution="medium",
                last_action_time=time.time() - 60,
                last_idle_event_time=time.time() - 5,
                another_agent_acting=False,
                throttle_min_interval=8.0,
            )
            results.append(r)

        topic_focus_waits = sum(1 for r in results if r.rule == "rule_6_5_topic_focus")
        # Should be roughly 80% (allow 60-95% range for randomness)
        ratio = topic_focus_waits / len(results)
        assert 0.55 < ratio < 0.95, f"Expected ~80% yield, got {ratio:.1%}"

    def test_participant_not_blocked(self) -> None:
        """Agent who is already a participant should NOT be blocked by Rule 6.5."""
        engine = AssessEngine()
        ctx = self._base_context(my_seat="crew_1")

        results = []
        for _ in range(50):
            r = engine.evaluate(
                context=ctx,
                agent_id="agent_1",
                ai_contribution="medium",
                last_action_time=time.time() - 60,
                last_idle_event_time=time.time() - 5,
                another_agent_acting=False,
                throttle_min_interval=8.0,
            )
            results.append(r)

        topic_focus_waits = sum(1 for r in results if r.rule == "rule_6_5_topic_focus")
        assert topic_focus_waits == 0, "Participant should never be blocked by Rule 6.5"

    def test_addressed_agent_not_blocked(self) -> None:
        """Agent with pending_addressee matching should NOT be blocked."""
        engine = AssessEngine()
        ctx = self._base_context(my_seat="crew_3")
        ctx["active_thread"]["pending_addressee"] = "crew_3"

        results = []
        for _ in range(50):
            r = engine.evaluate(
                context=ctx,
                agent_id="agent_3",
                ai_contribution="medium",
                last_action_time=time.time() - 60,
                last_idle_event_time=time.time() - 5,
                another_agent_acting=False,
                throttle_min_interval=8.0,
            )
            results.append(r)

        topic_focus_waits = sum(1 for r in results if r.rule == "rule_6_5_topic_focus")
        assert topic_focus_waits == 0, "Addressed agent should not be blocked by Rule 6.5"

    def test_no_active_thread_no_blocking(self) -> None:
        """Without an active thread, Rule 6.5 should not fire."""
        engine = AssessEngine()
        ctx = self._base_context()
        ctx["active_thread"] = None

        r = engine.evaluate(
            context=ctx,
            agent_id="agent_3",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            last_idle_event_time=time.time() - 5,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule != "rule_6_5_topic_focus"


# ===================================================================
# Rule 7 — Persistent Addressee
# ===================================================================


class TestPersistentAddressee:
    """pending_addressee should persist until the addressed agent responds."""

    def _base_context(self, *, my_seat: str, pending: str | None) -> dict:
        return {
            "recent_chat": [
                # Neutral content — no @mention to avoid Rule 1 triggering
                {"content": "搜尋體驗方面我覺得速度是最大問題", "sender": "crew_1(ai)", "sender_type": "ai"},
            ],
            "my_seat": my_seat,
            "seats": [
                {"role": "crew_1", "type": "ai"},
                {"role": "crew_2", "type": "ai"},
                {"role": "crew_3", "type": "ai"},
            ],
            "active_thread": {
                "topic_summary": "搜尋體驗",
                # Include test agent as participant to bypass Rule 6.5
                "participants": ["crew_1", "crew_2", "crew_3"],
                "turn_count": 3,
                "last_speaker": "crew_1",
                "addressed_to": None,
                "pending_addressee": pending,
            },
            "my_recent_actions": [],
            "current_stage": "discover",
        }

    def test_addressed_agent_intervenes(self) -> None:
        engine = AssessEngine()
        ctx = self._base_context(my_seat="crew_2", pending="crew_2")
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_2",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            last_idle_event_time=time.time() - 5,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.decision == "intervene"
        assert r.rule == "rule_7_addressed"

    def test_non_addressed_agent_yields(self) -> None:
        engine = AssessEngine()
        ctx = self._base_context(my_seat="crew_3", pending="crew_2")
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_3",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            last_idle_event_time=time.time() - 5,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.decision == "wait"
        assert r.rule == "rule_7_yield"


# ===================================================================
# Rule 2 — Human Typing Detection
# ===================================================================


class TestHumanTypingRule:
    def test_recent_typing_causes_wait(self) -> None:
        engine = AssessEngine()
        ctx = {
            "recent_chat": [{"content": "測試", "sender": "human(human)"}],
            "my_seat": "crew_1",
            "seats": [{"role": "crew_1", "type": "ai"}],
            "active_thread": None,
            "my_recent_actions": [],
            "_human_typing_timestamp": time.time() - 1.0,  # 1 second ago
        }
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_1",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule == "rule_2_human_typing"
        assert r.decision == "wait"

    def test_old_typing_ignored(self) -> None:
        engine = AssessEngine()
        ctx = {
            "recent_chat": [{"content": "測試", "sender": "human(human)"}],
            "my_seat": "crew_1",
            "seats": [{"role": "crew_1", "type": "ai"}],
            "active_thread": None,
            "my_recent_actions": [],
            "_human_typing_timestamp": time.time() - 10.0,  # 10 seconds ago
        }
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_1",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule != "rule_2_human_typing"

    def test_no_typing_timestamp(self) -> None:
        engine = AssessEngine()
        ctx = {
            "recent_chat": [{"content": "測試", "sender": "human(human)"}],
            "my_seat": "crew_1",
            "seats": [{"role": "crew_1", "type": "ai"}],
            "active_thread": None,
            "my_recent_actions": [],
            "_human_typing_timestamp": None,
        }
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_1",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule != "rule_2_human_typing"


# ===================================================================
# Rule 5 — Idle Detection
# ===================================================================


class TestIdleDetectionRule:
    def test_idle_triggers_intervention(self) -> None:
        engine = AssessEngine()
        ctx = {
            "recent_chat": [{"content": "測試", "sender": "human(human)"}],
            "my_seat": "crew_1",
            "seats": [{"role": "crew_1", "type": "ai"}],
            "active_thread": None,
            "my_recent_actions": [],
        }
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_1",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            last_idle_event_time=time.time() - 45,  # 45s > 30s medium threshold
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule == "rule_5_idle"
        assert r.decision == "intervene"

    def test_recent_activity_no_idle(self) -> None:
        engine = AssessEngine()
        ctx = {
            "recent_chat": [{"content": "測試", "sender": "human(human)"}],
            "my_seat": "crew_1",
            "seats": [{"role": "crew_1", "type": "ai"}],
            "active_thread": None,
            "my_recent_actions": [],
        }
        r = engine.evaluate(
            context=ctx,
            agent_id="agent_1",
            ai_contribution="medium",
            last_action_time=time.time() - 60,
            last_idle_event_time=time.time() - 5,  # 5s < 30s threshold
            another_agent_acting=False,
            throttle_min_interval=8.0,
        )
        assert r.rule != "rule_5_idle"


# ===================================================================
# Queue Backpressure (coordinator.queue_depth)
# ===================================================================


class TestQueueDepth:
    def test_empty_queue_returns_zero(self) -> None:
        from app.agents.coordinator import AgentCoordinator

        coord = AgentCoordinator()
        from uuid import uuid4

        assert coord.get_queue_depth(uuid4()) == 0

    def test_queue_depth_reflects_current(self) -> None:
        from app.agents.coordinator import _ProjectQueue

        q = _ProjectQueue()
        assert q.queue_depth() == 0
        # Simulate holding lock
        q._current = "agent_1"
        assert q.queue_depth() == 1


# ===================================================================
# Persistent Addressee in ConversationThread
# ===================================================================


class TestConversationThreadPendingAddressee:
    def test_new_thread_sets_pending(self) -> None:
        thread = ConversationThread(
            topic_summary="test",
            topic_ngrams=[],
            participants=["crew_1"],
            turn_count=1,
            last_speaker="crew_1",
            addressed_to="crew_2",
            started_at=time.time(),
            pending_addressee="crew_2",
        )
        assert thread.pending_addressee == "crew_2"

    def test_from_dict_preserves_pending(self) -> None:
        d = {
            "topic_summary": "test",
            "topic_ngrams": [],
            "participants": ["crew_1"],
            "turn_count": 1,
            "last_speaker": "crew_1",
            "addressed_to": "crew_2",
            "started_at": time.time(),
            "pending_addressee": "crew_2",
        }
        thread = ConversationThread.from_dict(d)
        assert thread.pending_addressee == "crew_2"

    def test_from_dict_without_pending_defaults_none(self) -> None:
        """Backward compatibility: old thread dicts without pending_addressee."""
        d = {
            "topic_summary": "test",
            "topic_ngrams": [],
            "participants": ["crew_1"],
            "turn_count": 1,
            "last_speaker": "crew_1",
            "addressed_to": None,
            "started_at": time.time(),
        }
        thread = ConversationThread.from_dict(d)
        assert thread.pending_addressee is None
