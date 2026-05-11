"""Tests for ActEngine._validate_actions comm_mode whitelist (Phase 18 Step A1)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.agents.act import ActEngine


def make_engine(seat_role: str = "crew_1") -> ActEngine:
    return ActEngine(
        project_id=uuid4(),
        agent_id="agent_test",
        agent_name="Test",
        seat_role=seat_role,
        is_supervisor=(seat_role == "supervisor"),
    )


class TestCommModeWhitelist:
    def test_silent_write_blocks_chat(self) -> None:
        engine = make_engine()
        actions = [
            {"type": "chat_message", "content": "hi"},
            {"type": "create_note", "text": "x"},
        ]
        legal, illegal = engine._validate_actions(actions, comm_mode="silent_write")
        assert len(legal) == 1
        assert legal[0]["type"] == "create_note"
        assert len(illegal) == 1
        assert illegal[0]["type"] == "chat_message"
        assert "silent_write" in illegal[0]["_blocked_reason"]

    def test_silent_rearrange_only_allows_move(self) -> None:
        engine = make_engine()
        actions = [
            {"type": "chat_message"},
            {"type": "create_note"},
            {"type": "move_note"},
            {"type": "swap_notes"},
        ]
        legal, illegal = engine._validate_actions(actions, comm_mode="silent_rearrange")
        legal_types = {a["type"] for a in legal}
        assert legal_types == {"move_note", "swap_notes"}
        assert len(illegal) == 2

    def test_reveal_round_allows_chat_and_create(self) -> None:
        engine = make_engine()
        actions = [
            {"type": "chat_message"},
            {"type": "create_note"},
            {"type": "move_note"},
        ]
        legal, illegal = engine._validate_actions(actions, comm_mode="reveal_round")
        legal_types = {a["type"] for a in legal}
        assert legal_types == {"chat_message", "create_note"}
        assert any(a["type"] == "move_note" for a in illegal)

    def test_discussion_allows_everything(self) -> None:
        engine = make_engine()
        actions = [
            {"type": "chat_message"},
            {"type": "create_note"},
            {"type": "move_note"},
            {"type": "edit_note"},
            {"type": "delete_note"},
            {"type": "swap_notes"},
            {"type": "tidy_area"},
            {"type": "arrange_notes"},
        ]
        legal, illegal = engine._validate_actions(actions, comm_mode="discussion")
        assert len(legal) == 8
        assert len(illegal) == 0

    def test_no_action_always_allowed(self) -> None:
        engine = make_engine()
        actions = [{"type": "no_action", "reason": "watching"}]
        for mode in ("silent_write", "silent_rearrange", "reveal_round", "discussion"):
            legal, illegal = engine._validate_actions(actions, comm_mode=mode)
            assert len(legal) == 1, f"no_action blocked in mode {mode}"
            assert len(illegal) == 0

    def test_crew_cannot_advance_stage_regardless_of_mode(self) -> None:
        engine = make_engine(seat_role="crew_1")
        actions = [{"type": "advance_stage"}]
        legal, illegal = engine._validate_actions(actions, comm_mode="discussion")
        assert len(legal) == 0
        assert len(illegal) == 1
        assert "supervisor" in illegal[0]["_blocked_reason"]

    def test_supervisor_can_advance(self) -> None:
        engine = make_engine(seat_role="supervisor")
        actions = [{"type": "advance_stage"}]
        legal, illegal = engine._validate_actions(actions, comm_mode="discussion")
        assert len(legal) == 1
        assert len(illegal) == 0

    def test_unknown_mode_defaults_to_no_restriction(self) -> None:
        # Spec 13: 沒列在表的 mode 視為 no comm-mode constraint
        engine = make_engine()
        actions = [{"type": "chat_message"}, {"type": "create_note"}]
        legal, illegal = engine._validate_actions(actions, comm_mode="unknown_mode")
        assert len(legal) == 2
        assert len(illegal) == 0
