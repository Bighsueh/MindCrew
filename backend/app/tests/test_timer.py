"""Tests for Timer system (Phase 18 Stream B)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.timer.calculator import (
    DEFAULT_PRESET,
    PRESETS,
    compute_sub_phase_budgets,
    get_phase_budget_seconds,
    load_preset,
)
from app.timer.events import TimerStateEvent
from app.timer.schemas import TimerConfig, TimerState, now_iso
from app.timer.service import TimerService


class TestDefaultPreset:
    """Phase 40 (spec/16 §2.1 v1.2): 系統預設 preset ＝ 90 分。"""

    def test_default_is_90min(self) -> None:
        budgets = DEFAULT_PRESET.macro_budgets
        # Phase 42 B1 (spec/16 §2.1 v2.0)：暖場固定硬上限 5 分；
        # 第一鑽石(discover+define)=total−5=85 分。
        assert budgets["discover"] + budgets["define"] == 85
        assert budgets["warmup"] == 5
        assert DEFAULT_PRESET.total_session_minutes == 90
        assert DEFAULT_PRESET.preset_id == "timer_preset_90min"

    def test_warning_thresholds_default(self) -> None:
        assert DEFAULT_PRESET.warning_thresholds_pct == [75, 90, 100]

    def test_not_auto_advance_by_default(self) -> None:
        assert DEFAULT_PRESET.auto_advance_on_timeout is False
        assert DEFAULT_PRESET.allow_overrun is True


class TestPresets:
    def test_2hr_and_4hr_removed(self) -> None:
        # Phase 40 (spec/16 §2.1 v1.2): 120/240 分 preset 已永久移除。
        assert "timer_preset_2hr" not in PRESETS
        assert "timer_preset_4hr" not in PRESETS

    def test_only_short_presets_registered(self) -> None:
        assert set(PRESETS) == {
            "timer_preset_40min",
            "timer_preset_60min",
            "timer_preset_90min",
        }

    def test_load_preset_falls_back_to_default(self) -> None:
        assert load_preset("nonexistent") == DEFAULT_PRESET

    # Phase 39 (spec/16 §2.1 v1.1): 40/60/90 短場 preset。
    def test_short_presets_registered(self) -> None:
        for pid in ("timer_preset_40min", "timer_preset_60min", "timer_preset_90min"):
            assert pid in PRESETS

    def test_short_presets_macro_totals(self) -> None:
        # Phase 42 B1 (spec/16 §2.1 v2.0)：warmup 固定 5；total−5 依 60:40 分配。
        expected = {
            "timer_preset_40min": (40, 0.4, 5, 21, 14),
            "timer_preset_60min": (60, 0.55, 5, 33, 22),
            "timer_preset_90min": (90, 0.8, 5, 51, 34),
        }
        for pid, (total, intensity, warmup, disc, define) in expected.items():
            cfg = PRESETS[pid]
            assert cfg.total_session_minutes == total
            assert cfg.intensity == intensity
            assert cfg.macro_budgets == {
                "warmup": warmup, "discover": disc, "define": define,
            }

    def test_short_presets_compute_budgets_positive(self) -> None:
        # compute_sub_phase_budgets 不爆；warmup 唯一格 0.0a 有正預算。
        for pid in ("timer_preset_40min", "timer_preset_60min", "timer_preset_90min"):
            budgets = compute_sub_phase_budgets(PRESETS[pid])
            assert budgets
            assert all(v >= 0 for v in budgets.values())
            assert budgets.get("0.0a", 0) > 0


class TestBudgetCalculator:
    def test_ratio_allocation_matches_spec_example(self) -> None:
        # Phase 42 C1（spec 16 v2.0 §2.1）：90 分 preset 示例——
        # discover 51 → 8/13/8/5/17；define 34 → 5/9/4/4/3/6/3。
        budgets = compute_sub_phase_budgets(DEFAULT_PRESET)
        expected_mins = {
            "0.0a": 5,
            "1.1a": 8, "1.1b": 13, "1.1c": 8, "1.1d": 5, "1.2": 17,
            "2.1": 5, "2.2": 9, "2.3": 4, "2.4": 4, "2.5": 3, "2.6": 6, "2.7": 3,
        }
        assert {k: v // 60 for k, v in budgets.items()} == expected_mins

    def test_ratio_sums_match_macro_budgets(self) -> None:
        # 捨入差額由佔比最大格吸收 → 每 macro 加總分毫不差。
        budgets = compute_sub_phase_budgets(DEFAULT_PRESET)
        assert sum(v for k, v in budgets.items() if k.startswith("1.")) == 51 * 60
        assert sum(v for k, v in budgets.items() if k.startswith("2.")) == 34 * 60

    def test_explicit_override_takes_precedence(self) -> None:
        # teacher/custom 顯式 override 的現役格優先；其餘格按重新正規化比例分。
        from app.timer.schemas import TimerConfig

        cfg = TimerConfig(
            total_session_minutes=90,
            intensity=0.8,
            macro_budgets={"warmup": 5, "discover": 51, "define": 34},
            sub_phase_overrides={"0.0a": 5, "1.2": 20, "1.5": 9},  # 1.5=已刪格，忽略
        )
        budgets = compute_sub_phase_budgets(cfg)
        assert budgets["1.2"] == 20 * 60
        assert "1.5" not in budgets
        assert sum(v for k, v in budgets.items() if k.startswith("1.")) == 51 * 60

    def test_get_phase_budget_seconds(self) -> None:
        assert get_phase_budget_seconds(DEFAULT_PRESET, "1.2") == 17 * 60

    def test_fallback_for_unknown_sub_phase(self) -> None:
        assert get_phase_budget_seconds(DEFAULT_PRESET, "99.99") == 300


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


class TestTimerStateEventPayload:
    """Phase 42 WP1 (spec/16 §4.5)：timer_state 增帶本關上限/已用與 warmup_goal。"""

    def test_to_dict_includes_sub_phase_fields(self) -> None:
        event = TimerStateEvent(
            project_id=uuid4(),
            current_sub_phase="0.0a",
            budget_seconds=240,
            used_seconds=60,
            paused=False,
            used_pct=25.0,
            sub_phase_budget_seconds=240,
            sub_phase_used_seconds=60,
            warmup_goal=16,
        )
        payload = event.to_dict()["payload"]
        assert payload["sub_phase_budget_seconds"] == 240
        assert payload["sub_phase_used_seconds"] == 60
        assert payload["warmup_goal"] == 16
        # 既有欄位不變（additive alias，不取代舊欄位）
        assert payload["budget_seconds"] == 240
        assert payload["used_seconds"] == 60

    def test_to_dict_warmup_goal_none_outside_warmup(self) -> None:
        event = TimerStateEvent(
            project_id=uuid4(),
            current_sub_phase="1.1a",
            budget_seconds=600,
            used_seconds=30,
            paused=False,
            used_pct=5.0,
            sub_phase_budget_seconds=600,
            sub_phase_used_seconds=30,
            warmup_goal=None,
        )
        payload = event.to_dict()["payload"]
        assert payload["warmup_goal"] is None


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
