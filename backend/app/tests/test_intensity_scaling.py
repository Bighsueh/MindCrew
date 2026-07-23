"""Phase 39 (spec/16 §2.4): intensity 強度縮放純函式測試。

涵蓋：
- 各 intensity 下 min_artifact_counts / stability / target_count 的縮放與地板。
- config=None 或 intensity>=1.0 回原值。
- deliverables_required 不受影響（縮放函式不碰它）。
"""
from __future__ import annotations

from app.stages.sub_phases import SUB_PHASES
from app.timer.calculator import (
    PRESET_40MIN,
    PRESET_60MIN,
    PRESET_90MIN,
)
from app.timer.schemas import TimerConfig
from app.timer.scaling import (
    effective_min_artifact_counts,
    effective_stability_seconds,
    effective_target_count,
    effective_warmup_goal,
    warmup_goal_for,
    warmup_soft_seconds_for,
)

# Phase 40 (spec/16 §2.1 v1.2)：2hr preset 已移除；intensity=1.0 的「不縮放」
# baseline 改用 inline config（剩下的 preset 40/60/90 強度都 < 1.0）。
FULL_CFG = TimerConfig(intensity=1.0)


class TestMinArtifactCounts:
    # Phase 42 C1：縮放對象改新 5+7 格門檻（spec 22 v2.0 §4.3 / 16 §2.4 範例）。
    def test_intensity_one_returns_raw(self) -> None:
        sp = SUB_PHASES["1.1b"]  # stakeholder: 8
        assert effective_min_artifact_counts(sp, FULL_CFG) == {"stakeholder": 8}

    def test_none_config_returns_raw(self) -> None:
        sp = SUB_PHASES["1.1b"]
        assert effective_min_artifact_counts(sp, None) == {"stakeholder": 8}

    def test_40min_stakeholder(self) -> None:
        # spec 16 §2.4 範例：利害關係人 8 → 0.4 → max(1, round(3.2)) = 3
        sp = SUB_PHASES["1.1b"]
        assert effective_min_artifact_counts(sp, PRESET_40MIN) == {"stakeholder": 3}

    def test_40min_pain_point(self) -> None:
        # spec 16 §2.4 範例：痛點 6 → 0.4 → round(2.4) = 2
        sp = SUB_PHASES["1.2"]
        assert effective_min_artifact_counts(sp, PRESET_40MIN) == {"pain_point": 2}

    def test_floor_one_for_small_counts(self) -> None:
        # 2.1 主題群 3 @ 0.4 → 1；2.2 問題定義 3 @ 0.4 → 1（地板 1）
        assert effective_min_artifact_counts(SUB_PHASES["2.1"], PRESET_40MIN) == {
            "problem_candidate": 1
        }
        assert effective_min_artifact_counts(SUB_PHASES["2.2"], PRESET_40MIN) == {
            "problem_statement": 1
        }

    def test_60min_and_90min_monotonic(self) -> None:
        sp = SUB_PHASES["1.1b"]  # stakeholder 8
        c40 = effective_min_artifact_counts(sp, PRESET_40MIN)["stakeholder"]
        c60 = effective_min_artifact_counts(sp, PRESET_60MIN)["stakeholder"]
        c90 = effective_min_artifact_counts(sp, PRESET_90MIN)["stakeholder"]
        c100 = effective_min_artifact_counts(sp, FULL_CFG)["stakeholder"]
        # 0.4→3, 0.55→4, 0.8→6, 1.0→8（單調不減）
        assert c40 <= c60 <= c90 <= c100
        assert (c40, c60, c90, c100) == (3, 4, 6, 8)

    def test_empty_counts_returns_empty(self) -> None:
        # 軟格（1.1d）無 min_artifact_counts。
        assert effective_min_artifact_counts(SUB_PHASES["1.1d"], PRESET_40MIN) == {}

    def test_special_keys_value_stays_one(self) -> None:
        # spec 25 v2.0 §3.4：特殊鍵值固定 1＝啟用旗標（地板 1，不隨 intensity 縮放）。
        assert effective_min_artifact_counts(SUB_PHASES["2.6"], PRESET_40MIN) == {
            "selection_pairing": 1
        }
        assert effective_min_artifact_counts(SUB_PHASES["2.7"], PRESET_40MIN) == {
            "hmw_pairing": 1
        }


class TestStabilitySeconds:
    def test_intensity_one_returns_raw(self) -> None:
        sp = SUB_PHASES["2.1"]  # stability 30
        assert effective_stability_seconds(sp, FULL_CFG) == 30.0

    def test_40min_floors_at_15(self) -> None:
        # 30 * 0.4 = 12 → 地板 15
        sp = SUB_PHASES["2.1"]
        assert effective_stability_seconds(sp, PRESET_40MIN) == 15.0

    def test_90min_scales(self) -> None:
        # 30 * 0.8 = 24
        sp = SUB_PHASES["2.1"]
        assert effective_stability_seconds(sp, PRESET_90MIN) == 24.0

    def test_none_config_raw(self) -> None:
        sp = SUB_PHASES["2.1"]
        assert effective_stability_seconds(sp, None) == 30.0


class TestTargetCount:
    def test_none_target_stays_none(self) -> None:
        # 1.1c target_count None
        sp = SUB_PHASES["1.1c"]
        assert effective_target_count(sp, PRESET_40MIN) is None

    def test_intensity_one_raw(self) -> None:
        sp = SUB_PHASES["1.2"]  # target 12（量爆軟上限）
        assert effective_target_count(sp, FULL_CFG) == 12

    def test_40min_scales_with_floor(self) -> None:
        # 1.2 target 12 * 0.4 = 5
        assert effective_target_count(SUB_PHASES["1.2"], PRESET_40MIN) == 5
        # 2.2 target 6 * 0.4 = round(2.4)=2
        assert effective_target_count(SUB_PHASES["2.2"], PRESET_40MIN) == 2


class TestWarmupGoal:
    """Phase 42 WP1 (spec/16 §2.4 v2.0)：暖場團隊目標 max(8, round(20 × intensity))。"""

    def test_40min_is_eight(self) -> None:
        # 0.4: round(8.0)=8（與地板同值）
        assert effective_warmup_goal(PRESET_40MIN) == 8

    def test_60min_is_eleven(self) -> None:
        # 0.55: round(11.0)=11
        assert effective_warmup_goal(PRESET_60MIN) == 11

    def test_90min_is_sixteen(self) -> None:
        # 0.8: round(16.0)=16
        assert effective_warmup_goal(PRESET_90MIN) == 16

    def test_full_intensity_is_twenty(self) -> None:
        assert effective_warmup_goal(FULL_CFG) == 20

    def test_none_config_is_twenty(self) -> None:
        # config=None 視為 intensity 1.0
        assert effective_warmup_goal(None) == 20

    def test_floor_at_eight(self) -> None:
        # 0.2: round(4.0)=4 → 地板 8
        assert effective_warmup_goal(TimerConfig(intensity=0.2)) == 8

    def test_warmup_goal_for_only_in_warmup_stage(self) -> None:
        # 0.0a（macro stage=warmup）→ 帶目標；非暖場格與 None → None
        assert warmup_goal_for("0.0a", PRESET_90MIN) == 16
        assert warmup_goal_for("1.1a", PRESET_90MIN) is None
        assert warmup_goal_for(None, PRESET_90MIN) is None
        assert warmup_goal_for("not-a-phase", PRESET_90MIN) is None


class TestWarmupSoftSeconds:
    """Bug B（spec 28 §3.1）：暖場軟目標固定 180／3 分，所有 preset 相同、不縮放。"""

    def test_only_in_warmup_stage(self) -> None:
        # 0.0a（macro stage=warmup）→ 帶軟目標；非暖場格、None、未知格 → None
        assert warmup_soft_seconds_for("0.0a", PRESET_90MIN) == 180
        assert warmup_soft_seconds_for("1.1a", PRESET_90MIN) is None
        assert warmup_soft_seconds_for(None, PRESET_90MIN) is None
        assert warmup_soft_seconds_for("not-a-phase", PRESET_90MIN) is None

    def test_fixed_across_presets_and_intensity(self) -> None:
        # 不隨 preset／intensity 縮放——40/60/90 與 config=None 皆為 180。
        assert warmup_soft_seconds_for("0.0a", PRESET_40MIN) == 180
        assert warmup_soft_seconds_for("0.0a", PRESET_60MIN) == 180
        assert warmup_soft_seconds_for("0.0a", None) == 180


class TestDeliverablesUnaffected:
    def test_scaling_does_not_touch_deliverables(self) -> None:
        # 縮放函式不回傳/不修改 deliverables_required；v2.0 配置全空（顏色
        # deliverable 隨 #34 移除）但機制保留——縮放路徑不碰該欄位。
        sp = SUB_PHASES["2.7"]
        before = sp.deliverables_required
        _ = effective_min_artifact_counts(sp, PRESET_40MIN)
        _ = effective_stability_seconds(sp, PRESET_40MIN)
        _ = effective_target_count(sp, PRESET_40MIN)
        assert sp.deliverables_required == before == ()
