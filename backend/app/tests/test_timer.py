"""Tests for Timer system (Phase 18 Stream B)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.timer.calculator import (
    DEFAULT_2HR_PRESET,
    PRESETS,
    compute_sub_phase_budgets,
    get_phase_budget_seconds,
    load_preset,
)
from app.timer.schemas import TimerConfig, TimerState, now_iso
from app.timer.service import TimerService


class Test2HrPreset:
    def test_default_totals_120_min(self) -> None:
        macro_total = sum(DEFAULT_2HR_PRESET.macro_budgets.values())
        assert macro_total == 120
        assert DEFAULT_2HR_PRESET.total_session_minutes == 120

    def test_warning_thresholds_default(self) -> None:
        assert DEFAULT_2HR_PRESET.warning_thresholds_pct == [75, 90, 100]

    def test_not_auto_advance_by_default(self) -> None:
        assert DEFAULT_2HR_PRESET.auto_advance_on_timeout is False
        assert DEFAULT_2HR_PRESET.allow_overrun is True


class TestPresets:
    def test_2hr_and_4hr_registered(self) -> None:
        assert "timer_preset_2hr" in PRESETS
        assert "timer_preset_4hr" in PRESETS

    def test_load_preset_falls_back_to_2hr(self) -> None:
        assert load_preset("nonexistent") == DEFAULT_2HR_PRESET

    def test_4hr_doubles_2hr_macro(self) -> None:
        assert PRESETS["timer_preset_4hr"].total_session_minutes == 240


class TestBudgetCalculator:
    def test_override_takes_precedence(self) -> None:
        budgets = compute_sub_phase_budgets(DEFAULT_2HR_PRESET)
        # 1.5 has override of 12 minutes = 720 seconds
        assert budgets["1.5"] == 12 * 60

    def test_unset_sub_phase_gets_share_of_macro(self) -> None:
        budgets = compute_sub_phase_budgets(DEFAULT_2HR_PRESET)
        # Discover total 45 min, sub_phase_overrides 1.1a-d (5+5+8+3)=21 + 1.5 12 + 1.6 8 = 41 min
        # Remaining 4 min split among 1.2/1.3/1.4 (3 sub_phases) = 80 secs each
        # All should be > 0
        for sid in ("1.2", "1.3", "1.4"):
            assert budgets[sid] > 0

    def test_get_phase_budget_seconds(self) -> None:
        assert get_phase_budget_seconds(DEFAULT_2HR_PRESET, "1.5") == 720

    def test_fallback_for_unknown_sub_phase(self) -> None:
        assert get_phase_budget_seconds(DEFAULT_2HR_PRESET, "99.99") == 300


class TestTimerState:
    def test_is_paused_default_false(self) -> None:
        state = TimerState()
        assert state.is_paused() is False

    def test_is_paused_with_paused_at(self) -> None:
        state = TimerState(paused_at=now_iso())
        assert state.is_paused() is True

    def test_parse_started_at_valid(self) -> None:
        ts = now_iso()
        state = TimerState(phase_started_at=ts)
        parsed = state.parse_started_at()
        assert parsed is not None
        assert parsed.tzinfo is not None

    def test_parse_started_at_invalid(self) -> None:
        state = TimerState(phase_started_at="not-iso")
        assert state.parse_started_at() is None


class TestUsedSecondsCompute:
    def test_zero_when_no_start_time(self) -> None:
        state = TimerState()
        assert TimerService._compute_used_seconds(state) == 0

    def test_subtracts_paused_seconds(self) -> None:
        # Started 100s ago, paused for 30s
        started = datetime.now(timezone.utc) - timedelta(seconds=100)
        state = TimerState(
            phase_started_at=started.isoformat(),
            total_paused_seconds=30,
        )
        used = TimerService._compute_used_seconds(state)
        # Roughly 70s (100 - 30)
        assert 65 <= used <= 75

    def test_still_paused_includes_running_pause(self) -> None:
        started = datetime.now(timezone.utc) - timedelta(seconds=60)
        paused = datetime.now(timezone.utc) - timedelta(seconds=20)
        state = TimerState(
            phase_started_at=started.isoformat(),
            paused_at=paused.isoformat(),
            total_paused_seconds=10,
        )
        used = TimerService._compute_used_seconds(state)
        # 60s elapsed, but paused for last 20s + 10s already paused = 30s pause → 30s effective
        assert 25 <= used <= 35
