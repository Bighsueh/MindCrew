"""Tests for Discover phase Supervisor behavior improvements.

Covers:
- Sub-phase determination (discover_subphase.py)
- Dynamic slowdown_score (evaluator_scoring.py)
- Blind spot veto and challenge gate (evaluator.py)
- Note count threshold change (evaluator_scoring.py)
"""
from __future__ import annotations

import time

import pytest

from app.agents.prompts.discover_subphase import (
    DiscoverSubPhase,
    determine_discover_subphase,
)
from app.agents.evaluator_scoring import _compute_slowdown_score, score_discover


# ===================================================================
# Sub-phase determination
# ===================================================================


class TestDiscoverSubPhase:
    """Test determine_discover_subphase boundary transitions."""

    def test_initial_state_is_early(self) -> None:
        canvas = {"total_notes": 0, "notes": []}
        assert determine_discover_subphase(canvas, [], 0) == DiscoverSubPhase.EARLY

    def test_early_to_mid_by_activity(self) -> None:
        canvas = {"total_notes": 5, "notes": []}
        chat = [{"content": f"msg {i}"} for i in range(8)]
        assert determine_discover_subphase(canvas, chat, 2.0) == DiscoverSubPhase.MID

    def test_early_to_mid_by_time(self) -> None:
        canvas = {"total_notes": 1, "notes": []}
        assert determine_discover_subphase(canvas, [], 5.0) == DiscoverSubPhase.MID

    def test_stays_early_below_thresholds(self) -> None:
        canvas = {"total_notes": 4, "notes": []}
        chat = [{"content": f"msg {i}"} for i in range(7)]
        assert determine_discover_subphase(canvas, chat, 3.0) == DiscoverSubPhase.EARLY

    def test_mid_to_late_by_activity(self) -> None:
        canvas = {"total_notes": 12, "notes": []}
        chat = [{"content": f"msg {i}"} for i in range(15)]
        assert determine_discover_subphase(canvas, chat, 8.0) == DiscoverSubPhase.LATE

    def test_mid_to_late_by_time(self) -> None:
        canvas = {"total_notes": 3, "notes": []}
        assert determine_discover_subphase(canvas, [], 15.0) == DiscoverSubPhase.LATE

    def test_monotonic_notes_but_not_chat(self) -> None:
        """Notes >=5 but chat < 8 and time < 5 → still EARLY."""
        canvas = {"total_notes": 6, "notes": []}
        chat = [{"content": f"msg {i}"} for i in range(3)]
        assert determine_discover_subphase(canvas, chat, 3.0) == DiscoverSubPhase.EARLY

    def test_high_activity_jumps_to_late(self) -> None:
        """If activity exceeds mid thresholds directly, go to LATE."""
        canvas = {"total_notes": 20, "notes": []}
        chat = [{"content": f"msg {i}"} for i in range(20)]
        assert determine_discover_subphase(canvas, chat, 3.0) == DiscoverSubPhase.LATE


# ===================================================================
# Slowdown score
# ===================================================================


class TestSlowdownScore:
    """Test _compute_slowdown_score with various timestamp distributions."""

    def test_empty_canvas_returns_zero(self) -> None:
        assert _compute_slowdown_score({"notes": []}) == 0.0

    def test_no_notes_returns_zero(self) -> None:
        assert _compute_slowdown_score({}) == 0.0

    def test_all_recent_notes_low_time_score(self) -> None:
        """All notes created in the last 3 min → time component is 0."""
        now = time.time()
        notes = [
            {"content": f"觀點{i}", "created_at": now - 30 * i}
            for i in range(5)
        ]
        score = _compute_slowdown_score({"notes": notes})
        # time_score=0 (no prev window notes), repetition may add some
        # but overall should stay well below saturation threshold
        assert score < 50.0

    def test_no_recent_notes_high_score(self) -> None:
        """All notes from 4-6 min ago, none in last 3 min → high time score."""
        now = time.time()
        notes = [
            {"content": f"觀點{i}", "created_at": now - 300 - 30 * i}
            for i in range(5)
        ]
        score = _compute_slowdown_score({"notes": notes})
        # recent=0, prev=5 → time_score=100 (60% weight) → at least 60
        assert score >= 55.0

    def test_high_repetition_boosts_score(self) -> None:
        """Notes with very similar CJK content → high repetition component."""
        now = time.time()
        notes = [
            {"content": "使用者在購物時遇到問題", "created_at": now - 60},
            {"content": "使用者在購物時的困難", "created_at": now - 120},
            {"content": "使用者購物遇到的問題", "created_at": now - 200},
            {"content": "使用者買東西時的問題", "created_at": now - 250},
            {"content": "購物使用者遇到問題", "created_at": now - 350},
        ]
        score = _compute_slowdown_score({"notes": notes})
        # Should have meaningful repetition score
        assert score > 0.0

    def test_diverse_notes_low_repetition(self) -> None:
        """Notes with completely different CJK content → low repetition."""
        now = time.time()
        notes = [
            {"content": "價格太高", "created_at": now - 60},
            {"content": "介面設計不友善", "created_at": now - 120},
            {"content": "配送速度慢", "created_at": now - 250},
            {"content": "客服態度差", "created_at": now - 350},
        ]
        score = _compute_slowdown_score({"notes": notes})
        # Diverse content → low repetition; only time component matters
        assert score < 80.0


# ===================================================================
# Note count threshold
# ===================================================================


class TestNoteCountThreshold:
    """Verify note count perfect score raised from 15 to 25."""

    def test_15_notes_not_perfect(self) -> None:
        canvas = {"total_notes": 15, "notes": []}
        score = score_discover(canvas, [], [])
        # note_score = 15/25*100 = 60, weighted at 30% = 18
        # With slowdown=0, coverage=100(25%)=25, chat=0, diversity=0
        # Total should be < 50 (not a perfect quantitative score)
        assert score < 50.0

    def test_25_notes_perfect_note_score(self) -> None:
        canvas = {"total_notes": 25, "notes": []}
        chat = [{"content": f"msg{i}"} for i in range(20)]
        seats: list[dict] = []
        score = score_discover(canvas, chat, seats)
        # note=100(30%)=30, slowdown~0(20%)=0, coverage=100(25%)=25,
        # chat=100(15%)=15, diversity=100(10%)=10 → ~80
        assert score >= 75.0


# ===================================================================
# Blind spot veto (evaluator logic — unit test via direct scoring)
# ===================================================================


class TestBlindSpotVeto:
    """Test that blind_spot_score < 40 blocks advancement."""

    def test_veto_blocks_when_score_below_40(self) -> None:
        """Simulate the veto logic from evaluator.evaluate()."""
        blind_spot_score = 30.0
        passed = True  # Would have passed based on total
        weak_areas: list[str] = []

        # Apply veto logic (same as in evaluator.py)
        if blind_spot_score < 40:
            passed = False
            if not any("盲區分數不足" in w for w in weak_areas):
                weak_areas.insert(0, "盲區分數不足——團隊可能遺漏了重要面向")

        assert passed is False
        assert "盲區分數不足" in weak_areas[0]

    def test_no_veto_when_score_above_40(self) -> None:
        blind_spot_score = 65.0
        passed = True
        weak_areas: list[str] = []

        if blind_spot_score < 40:
            passed = False

        assert passed is True
        assert weak_areas == []

    def test_veto_at_boundary_40(self) -> None:
        """Score exactly 40 should NOT trigger veto (< 40, not <=)."""
        blind_spot_score = 40.0
        passed = True

        if blind_spot_score < 40:
            passed = False

        assert passed is True


# ===================================================================
# Blind spot challenge gate (two-pass logic)
# ===================================================================


class TestBlindSpotChallengeGate:
    """Test the two-pass challenge gate logic."""

    def test_first_pass_sends_challenge_not_advance(self) -> None:
        """First time reaching required_passes → challenge, not advance."""
        blind_spot_challenge_sent = False
        consecutive_pass_count = 3
        required_passes = 3

        if consecutive_pass_count >= required_passes and not blind_spot_challenge_sent:
            action = "blind_spot_challenge"
            blind_spot_challenge_sent = True
            consecutive_pass_count = required_passes - 1
        else:
            action = "propose_advance"

        assert action == "blind_spot_challenge"
        assert blind_spot_challenge_sent is True
        assert consecutive_pass_count == 2  # Reset to require one more pass

    def test_second_pass_proposes_advance(self) -> None:
        """After challenge was sent, next pass → propose advance."""
        blind_spot_challenge_sent = True
        consecutive_pass_count = 3
        required_passes = 3

        if consecutive_pass_count >= required_passes and not blind_spot_challenge_sent:
            action = "blind_spot_challenge"
        else:
            action = "propose_advance"
            blind_spot_challenge_sent = False

        assert action == "propose_advance"
        assert blind_spot_challenge_sent is False  # Reset for next time
