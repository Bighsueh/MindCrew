"""Timer 預算分配計算 — Spec 16 v2.0 §2.1.

Phase 42 C1：各 sub-phase 的時間上限改為「該 macro 預算 × 基準比例」計算
（取代 v1.x 的「每 preset 絕對分鐘表」——舊表含已刪除的 1.5/1.6 格，整段作廢）。
捨入規則（spec 16 v2.0 §2.1）：非末格四捨五入、各格地板 1 分；捨入總和與
macro 預算的差額由該 macro 佔比最大的格吸收。
"""

from __future__ import annotations

from app.timer.schemas import TimerConfig
from app.stages.sub_phases import SUB_PHASES


# Phase 42 B1 (spec/16 §2.1/§4.4 v2.0、spec/28 §3.1)：暖場固定「軟 3 分／硬 5 分」、
# 所有 preset（含 custom）相同，是時間比例分配原則（#19）的唯一明文例外。
# 0.0a 的 time-box（budget）＝硬上限 5 分；軟目標 3 分為檢核點（三情境退場），
# 由 evaluator / signal_panel 消費，不進 config（固定值、不可調）。
WARMUP_HARD_BUDGET_MINUTES = 5
WARMUP_SOFT_SECONDS = 180


# Phase 42 C1 (spec/16 §2.1 v2.0)：新 5+7 格的「佔該 macro 預算比例」基準表
# （intensity 1.0 基準；數字依模擬實測調整——模擬驅動，可調）。
# 這些是各格 time-box（時間上限）、不是下限：訊號達成＋真人 gate 過 → 隨時推進，
# 剩餘時間回流後面的格（spec 16 §4）。
SUB_PHASE_BUDGET_RATIOS: dict[str, dict[str, float]] = {
    "discover": {
        "1.1a": 0.15,   # 經驗分享
        "1.1b": 0.25,   # 發想利害關係人
        "1.1c": 0.15,   # 一起歸類
        "1.1d": 0.10,   # 排先後順序
        "1.2": 0.35,    # 發想痛點與情境（重頭戲）
    },
    "define": {
        "2.1": 0.15,    # 痛點歸類
        "2.2": 0.25,    # 問題定義
        "2.3": 0.12,    # 追問根源
        "2.4": 0.12,    # 盤點現有解法
        "2.5": 0.08,    # 訂收斂準則
        "2.6": 0.18,    # 依準則挑問題定義（時間安全閥所在）
        "2.7": 0.10,    # 改寫設計題目
    },
}


# Phase 40 (spec/16-timer-system §2.1 v1.2): 移除 120/240 分（2hr/4hr）preset。
# 工作坊改以 40/60/90 分短場 + custom 為主；想跑滿強度的長場以 custom 自訂。
# 系統 fallback / 預設 preset ＝ 90 分（見下方 DEFAULT_PRESET）。
# Phase 42 B1：warmup 固定預留硬上限 5 分，剩餘 total−5 依 discover:define ≈ 60:40
# 分配（spec/16 §2.1 v2.0 表：90→51/34、60→33/22、40→21/14）。
# Phase 42 C1：preset 不再帶逐格絕對分鐘表（只固定 0.0a），逐格上限由比例表推導。
PRESET_90MIN = TimerConfig(
    version=1,
    total_session_minutes=90,
    intensity=0.8,
    macro_budgets={"warmup": WARMUP_HARD_BUDGET_MINUTES, "discover": 51, "define": 34},
    sub_phase_overrides={"0.0a": WARMUP_HARD_BUDGET_MINUTES},
    warning_thresholds_pct=[75, 90, 100],
    auto_advance_on_timeout=False,
    allow_overrun=True,
    preset_id="timer_preset_90min",
)


PRESET_60MIN = TimerConfig(
    version=1,
    total_session_minutes=60,
    intensity=0.55,
    macro_budgets={"warmup": WARMUP_HARD_BUDGET_MINUTES, "discover": 33, "define": 22},
    sub_phase_overrides={"0.0a": WARMUP_HARD_BUDGET_MINUTES},
    warning_thresholds_pct=[75, 90, 100],
    auto_advance_on_timeout=False,
    allow_overrun=True,
    preset_id="timer_preset_60min",
)


PRESET_40MIN = TimerConfig(
    version=1,
    total_session_minutes=40,
    intensity=0.4,
    macro_budgets={"warmup": WARMUP_HARD_BUDGET_MINUTES, "discover": 21, "define": 14},
    sub_phase_overrides={"0.0a": WARMUP_HARD_BUDGET_MINUTES},
    warning_thresholds_pct=[75, 90, 100],
    auto_advance_on_timeout=False,
    allow_overrun=True,
    preset_id="timer_preset_40min",
)


# 系統 fallback / 預設 preset — config=None、未知 preset_id、舊專案缺 config 時使用。
DEFAULT_PRESET = PRESET_90MIN


PRESETS: dict[str, TimerConfig] = {
    "timer_preset_40min": PRESET_40MIN,
    "timer_preset_60min": PRESET_60MIN,
    "timer_preset_90min": PRESET_90MIN,
}


def _allocate_macro_minutes(
    macro_total_mins: int,
    ratios: dict[str, float],
    overridden_mins: dict[str, int],
) -> dict[str, int]:
    """單一 macro 的逐格分鐘分配（spec 16 v2.0 §2.1 捨入規則）。

    - 顯式 override 的格直接採用、退出比例池；其餘格按重新正規化的比例分剩餘預算。
    - 非末格四捨五入、各格地板 1 分；差額由（比例池中）佔比最大的格吸收（同樣地板 1）。
    """
    result: dict[str, int] = dict(overridden_mins)
    pool = {sid: r for sid, r in ratios.items() if sid not in overridden_mins}
    if not pool:
        return result

    remaining = max(0, macro_total_mins - sum(overridden_mins.values()))
    weight_sum = sum(pool.values()) or 1.0
    largest = max(pool, key=lambda sid: pool[sid])

    assigned = 0
    for sid, ratio in pool.items():
        if sid == largest:
            continue
        mins = max(1, round(remaining * (ratio / weight_sum)))
        result[sid] = mins
        assigned += mins
    result[largest] = max(1, remaining - assigned)
    return result


def compute_sub_phase_budgets(config: TimerConfig) -> dict[str, int]:
    """從 macro_budgets ＋ 比例表算出每個 sub_phase 的預算（秒）。

    - warmup：0.0a 固定硬上限 5 分（override 或 WARMUP_HARD_BUDGET_MINUTES）。
    - discover / define：macro 預算 × SUB_PHASE_BUDGET_RATIOS（捨入規則見
      ``_allocate_macro_minutes``）；config.sub_phase_overrides 中屬現役格的
    顯式 override 優先（teacher / custom 路徑），不在比例表的未知格 id 忽略
    （含舊 custom config 殘留的已刪格 1.5/1.6 等）。
    """
    result: dict[str, int] = {}

    overrides_mins = {
        sid: mins
        for sid, mins in config.sub_phase_overrides.items()
        if sid in SUB_PHASES
    }

    # 暖場固定（比例分配原則的明文例外）。
    result["0.0a"] = overrides_mins.pop("0.0a", WARMUP_HARD_BUDGET_MINUTES) * 60

    for macro, ratios in SUB_PHASE_BUDGET_RATIOS.items():
        total_mins = int(config.macro_budgets.get(macro, 0))
        macro_overrides = {
            sid: mins for sid, mins in overrides_mins.items() if sid in ratios
        }
        if total_mins <= 0:
            # macro 預算缺漏（不完整的 custom config）→ 只能用顯式 override。
            for sid, mins in macro_overrides.items():
                result[sid] = mins * 60
            continue
        allocated = _allocate_macro_minutes(total_mins, ratios, macro_overrides)
        for sid, mins in allocated.items():
            result[sid] = mins * 60

    return result


def get_phase_budget_seconds(
    config: TimerConfig | None,
    sub_phase_id: str,
) -> int:
    """單一 sub_phase 的預算秒數。"""
    if config is None:
        config = DEFAULT_PRESET
    budgets = compute_sub_phase_budgets(config)
    return budgets.get(sub_phase_id, 300)  # 預設 5 分鐘


def load_preset(preset_id: str) -> TimerConfig:
    return PRESETS.get(preset_id, DEFAULT_PRESET)
