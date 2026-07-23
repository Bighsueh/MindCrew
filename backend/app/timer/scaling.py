"""Intensity scaling — Spec 16 §2.4 (v1.1, Phase 39).

純函式、無副作用：把 sub-phase 的「絕對值型」門檻依 TimerConfig.intensity 等比變輕，
讓 40/60/90 分短場也能跑完整第一鑽石（步驟一個不少，便條張數/深度隨時長縮放）。

縮放對象與地板（spec/16 §2.4）：
  - min_artifact_counts      : max(1, round(raw × intensity))   地板 1（每工具至少 1 張）
  - stability_timeout_seconds: max(15, round(raw × intensity))  地板 15 秒
  - target_count（軟上限）    : max(1, round(raw × intensity))   地板 1
  - warmup_goal（暖場團隊目標）: max(8, round(20 × intensity))    地板 8（v2.0, Phase 42 WP1）
  - deliverables_required    : 不縮放（完整性絕對地板）

config=None 或 intensity>=1.0 → 回原值（custom/未帶 intensity 的設定行為與現況一致）。
"""

from __future__ import annotations

from app.stages.sub_phases import SUB_PHASES, SubPhase
from app.timer.schemas import TimerConfig

_STABILITY_FLOOR_SECONDS = 15
_ARTIFACT_FLOOR = 1
_TARGET_FLOOR = 1
_WARMUP_GOAL_BASE = 20
_WARMUP_GOAL_FLOOR = 8


def _intensity_of(config: TimerConfig | None) -> float:
    """回傳有效 intensity；None 或缺欄位視為 1.0（不縮放）。"""
    if config is None:
        return 1.0
    intensity = getattr(config, "intensity", 1.0)
    try:
        return float(intensity)
    except (TypeError, ValueError):
        return 1.0


def _scale(raw: int, intensity: float, floor: int) -> int:
    """等比縮放 + 地板。intensity>=1.0 時回原值。"""
    if intensity >= 1.0:
        return raw
    return max(floor, round(raw * intensity))


def effective_min_artifact_counts(
    sp: SubPhase, config: TimerConfig | None
) -> dict[str, int]:
    """縮放後的 min_artifact_counts（每張地板 1）。"""
    intensity = _intensity_of(config)
    if intensity >= 1.0 or not sp.min_artifact_counts:
        return dict(sp.min_artifact_counts)
    return {
        key: _scale(raw, intensity, _ARTIFACT_FLOOR)
        for key, raw in sp.min_artifact_counts.items()
    }


def effective_stability_seconds(
    sp: SubPhase, config: TimerConfig | None
) -> float:
    """縮放後的整理格靜止秒數（地板 15 秒）。"""
    intensity = _intensity_of(config)
    return float(_scale(sp.stability_timeout_seconds, intensity, _STABILITY_FLOOR_SECONDS))


def effective_target_count(
    sp: SubPhase, config: TimerConfig | None
) -> int | None:
    """縮放後的量爆軟上限（地板 1）。sp.target_count 為 None 時回 None。"""
    if sp.target_count is None:
        return None
    intensity = _intensity_of(config)
    return _scale(sp.target_count, intensity, _TARGET_FLOOR)


def effective_warmup_goal(config: TimerConfig | None) -> int:
    """暖場團隊目標張數（spec/16 §2.4 v2.0）：max(8, round(20 × intensity))。

    各 preset 實值：40 分→8、60 分→11、90 分→16、custom（1.0）→20。
    config=None 視為 intensity 1.0 → 20。
    """
    intensity = _intensity_of(config)
    return max(_WARMUP_GOAL_FLOOR, round(_WARMUP_GOAL_BASE * intensity))


def warmup_goal_for(
    sub_phase_id: str | None, config: TimerConfig | None
) -> int | None:
    """暖場（macro stage = warmup）期間回傳團隊目標張數，否則 None。

    Spec 16 v2.0 §4.5：以 sub_phases 的 macro_stage 查詢判定，不硬編代號比對。
    timer_state WS 事件與 GET /timer 共用此計算來源。
    """
    if not sub_phase_id:
        return None
    sp = SUB_PHASES.get(sub_phase_id)
    if sp is None or sp.macro_stage != "warmup":
        return None
    return effective_warmup_goal(config)


def warmup_soft_seconds_for(
    sub_phase_id: str | None, config: TimerConfig | None
) -> int | None:
    """暖場（macro stage = warmup）期間回傳軟目標秒數（固定 180／3 分），否則 None。

    Spec 28 §3.1：軟 3 分／硬 5 分對所有 preset 固定、不隨 intensity 縮放——
    硬上限＝budget_seconds，軟目標只是檢核點。前端用此值在倒數上標示「3 分軟目標」，
    讓組長「延長到五分鐘」話術有可視指涉（spec 05 §5、spec 16 §4.5）。
    timer_state WS 事件與 GET /timer 共用此計算來源。
    """
    if not sub_phase_id:
        return None
    sp = SUB_PHASES.get(sub_phase_id)
    if sp is None or sp.macro_stage != "warmup":
        return None
    from app.timer.calculator import WARMUP_SOFT_SECONDS

    return WARMUP_SOFT_SECONDS
