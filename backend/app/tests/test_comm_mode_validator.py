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
    def test_phase41_silent_modes_no_longer_restrict(self) -> None:
        # Phase 41：silent_write / silent_rearrange 已從白名單移除 → fall through 成「無限制」。
        # AI 全階段可同時 chat + create + move（沉默改由軟性護欄取代，Spec 27 v2.4）。
        engine = make_engine()
        actions = [
            {"type": "chat_message", "content": "hi"},
            {"type": "create_note", "text": "x"},
            {"type": "move_note"},
        ]
        for mode in ("silent_write", "silent_rearrange"):
            legal, illegal = engine._validate_actions(actions, comm_mode=mode)
            assert len(legal) == 3, f"{mode} 不應再限制動作"
            assert len(illegal) == 0

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
        for mode in ("reveal_round", "threaded_reveal", "discussion"):
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


class TestAdvanceSubPhaseAction:
    """Phase 42 A1（spec 04-06 §5.8）：組長宣布推進 action 的三層驗證。"""

    def test_crew_cannot_advance_sub_phase(self) -> None:
        engine = make_engine(seat_role="crew_2")
        legal, illegal = engine._validate_actions(
            [{"type": "advance_sub_phase"}], comm_mode="discussion"
        )
        assert len(legal) == 0
        assert len(illegal) == 1
        assert "supervisor" in illegal[0]["_blocked_reason"]

    def test_supervisor_can_advance_sub_phase_in_all_comm_modes(self) -> None:
        # 組長在 reveal_round / threaded_reveal / discussion 都可宣布推進，
        # 不會被自己的 comm_mode 白名單擋下（A1 漣漪重點）。
        engine = make_engine(seat_role="supervisor")
        for mode in ("reveal_round", "threaded_reveal", "discussion"):
            legal, illegal = engine._validate_actions(
                [{"type": "advance_sub_phase"}], comm_mode=mode
            )
            assert len(legal) == 1, f"supervisor advance blocked in mode {mode}"
            assert len(illegal) == 0

    def test_advance_sub_phase_in_think_whitelist(self) -> None:
        # 上游 parse 閘（think._VALID_ACTION_TYPES）漏加會讓 act 層全部碰不到。
        from app.agents.think import _VALID_ACTION_TYPES

        assert "advance_sub_phase" in _VALID_ACTION_TYPES
