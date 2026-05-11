"""Timer 預算分配計算 — Spec 15 §2."""

from __future__ import annotations

from app.timer.schemas import TimerConfig
from app.stages.sub_phases import SUB_PHASES


# Spec 15 §2 — 2 小時 DT 活動 preset
DEFAULT_2HR_PRESET = TimerConfig(
    version=1,
    total_session_minutes=120,
    macro_budgets={"discover": 45, "define": 30, "develop": 25, "deliver": 20},
    sub_phase_overrides={
        "1.1a": 5, "1.1b": 5, "1.1c": 8, "1.1d": 3,
        "1.5": 12, "1.6": 8,
        "2.2": 10, "2.5": 3, "2.6": 4, "2.7": 3,
        "3.2": 10, "3.3": 10,
        "4.1f": 12, "4.2": 5,
    },
    warning_thresholds_pct=[75, 90, 100],
    auto_advance_on_timeout=False,
    allow_overrun=True,
    preset_id="timer_preset_2hr",
)


# 4 小時 workshop preset
PRESET_4HR = TimerConfig(
    version=1,
    total_session_minutes=240,
    macro_budgets={"discover": 90, "define": 60, "develop": 50, "deliver": 40},
    sub_phase_overrides={},
    warning_thresholds_pct=[75, 90, 100],
    auto_advance_on_timeout=False,
    allow_overrun=True,
    preset_id="timer_preset_4hr",
)


PRESETS: dict[str, TimerConfig] = {
    "timer_preset_2hr": DEFAULT_2HR_PRESET,
    "timer_preset_4hr": PRESET_4HR,
}


def compute_sub_phase_budgets(config: TimerConfig) -> dict[str, int]:
    """從 macro_budgets + sub_phase_overrides 算出每個 sub_phase 的預算（秒）。

    沒被 override 的 sub_phase 自動分配該 macro 剩餘預算（平均分）。
    """
    result: dict[str, int] = {}

    # 先填 override
    for sub_id, mins in config.sub_phase_overrides.items():
        if sub_id in SUB_PHASES:
            result[sub_id] = mins * 60

    # 按 macro 分組，把剩餘預算平均分給未 override 的 sub_phase
    for macro, total_mins in config.macro_budgets.items():
        total_secs = total_mins * 60
        macro_sub_ids = [
            sid for sid, sp in SUB_PHASES.items()
            if sp.macro_stage == macro
        ]
        if not macro_sub_ids:
            continue

        overridden = [sid for sid in macro_sub_ids if sid in result]
        unset = [sid for sid in macro_sub_ids if sid not in result]

        used = sum(result[sid] for sid in overridden)
        remaining = max(0, total_secs - used)

        if unset:
            share = remaining // len(unset)
            for sid in unset:
                result[sid] = share

    return result


def get_phase_budget_seconds(
    config: TimerConfig | None,
    sub_phase_id: str,
) -> int:
    """單一 sub_phase 的預算秒數。"""
    if config is None:
        config = DEFAULT_2HR_PRESET
    budgets = compute_sub_phase_budgets(config)
    return budgets.get(sub_phase_id, 300)  # 預設 5 分鐘


def load_preset(preset_id: str) -> TimerConfig:
    return PRESETS.get(preset_id, DEFAULT_2HR_PRESET)
