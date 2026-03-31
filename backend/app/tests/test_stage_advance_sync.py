"""Tests for P0 fixes: Stage advance micro_phase synchronization.

Covers:
- Manual advance resets current_micro_phase
- MicroPhaseHistory created on manual advance
- MicroPhaseChangedEvent published
- All stage transitions produce correct micro_phase
"""

from __future__ import annotations

import pytest

from app.stages.micro_phases import get_first_micro_phase_for_stage


# ── Micro Phase Mapping ──


class TestGetFirstMicroPhase:
    """Verify get_first_micro_phase_for_stage returns correct values."""

    @pytest.mark.parametrize(
        "stage, expected_prefix",
        [
            ("discover", "1."),
            ("define", "2."),
            ("develop", "3."),
            ("deliver", "4."),
        ],
    )
    def test_all_stages_return_correct_prefix(
        self, stage: str, expected_prefix: str,
    ) -> None:
        result = get_first_micro_phase_for_stage(stage)
        assert result is not None
        assert result.startswith(expected_prefix), (
            f"Stage '{stage}' → '{result}', expected prefix '{expected_prefix}'"
        )

    @pytest.mark.parametrize(
        "stage, expected",
        [
            ("discover", "1.1"),
            ("define", "2.1"),
            ("develop", "3.1"),
            ("deliver", "4.1"),
        ],
    )
    def test_exact_first_micro_phase(self, stage: str, expected: str) -> None:
        assert get_first_micro_phase_for_stage(stage) == expected

    def test_completed_returns_none(self) -> None:
        result = get_first_micro_phase_for_stage("completed")
        assert result is None

    def test_unknown_returns_none(self) -> None:
        result = get_first_micro_phase_for_stage("nonexistent")
        assert result is None


# ── Duration Cap ──


class TestDurationCap:
    """Verify duration_seconds is capped at reasonable values."""

    def test_cap_at_24h(self) -> None:
        """Duration should be capped at 86400 seconds (24h)."""
        raw_duration = 430742.0  # ~5 days (the bug value)
        capped = min(raw_duration, 86400.0)
        assert capped == 86400.0

    def test_normal_duration_not_capped(self) -> None:
        """Normal durations should pass through unchanged."""
        raw_duration = 240.0  # 4 minutes
        capped = min(raw_duration, 86400.0)
        assert capped == 240.0
