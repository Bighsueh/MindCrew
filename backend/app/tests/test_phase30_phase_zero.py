"""Phase 0（0.1/0.2）正式移除 regression（spec 22 v2.0 §2.2，Phase 42 C1）.

v1.0（Phase 30）的 Phase 0 結構測試已隨格移除改寫為移除回歸；
``tour_acknowledged_by``／``POST /acknowledge-tour`` 保留（語意與狀態機脫鉤，
spec 22 v2.0 §5.1/§6——endpoint 本步未動，行為由 service 既有路徑承載）。
"""

from __future__ import annotations

from app.canvas.zones import ZONES, get_active_zones
from app.stages.micro_phases import MICRO_PHASES, MICRO_PHASE_ORDER
from app.stages.sub_phases import (
    SUB_PHASE_ORDER,
    SUB_PHASES,
    get_first_sub_phase_of_macro,
)


class TestPhaseZeroRemoved:
    def test_micro_0_1_0_2_removed(self) -> None:
        for phase_id in ("0.1", "0.2"):
            assert phase_id not in MICRO_PHASES
            assert phase_id not in MICRO_PHASE_ORDER

    def test_sub_0_1_0_2_removed(self) -> None:
        for sub_id in ("0.1", "0.2"):
            assert sub_id not in SUB_PHASES
            assert sub_id not in SUB_PHASE_ORDER

    def test_warmup_then_discover_entry(self) -> None:
        # 入場暖身職責由 0.0a（warmup macro）承擔；discover 入口＝1.1a。
        assert SUB_PHASE_ORDER[0] == "0.0a"
        assert SUB_PHASE_ORDER[1] == "1.1a"
        assert get_first_sub_phase_of_macro("warmup") == "0.0a"
        assert get_first_sub_phase_of_macro("discover") == "1.1a"

    def test_task_clarification_zone_removed(self) -> None:
        # spec 22 v2.0 §3.1：zone 隨 0.2 移除。
        assert "task_clarification_zone" not in ZONES
        assert get_active_zones("0.2") == []


class TestTourArtifactsRetained:
    def test_acknowledge_tour_endpoint_retained(self) -> None:
        # spec 22 v2.0 §6：API 保留（前端導覽完成回報用）、與 sub-phase 狀態機脫鉤。
        from app.projects.service import ProjectService

        assert hasattr(ProjectService, "acknowledge_tour")

    def test_tour_acknowledged_by_column_retained(self) -> None:
        # spec 22 v2.0 §5.1：欄位保留、語意改「完成前端導覽」。
        from app.db.models.project import Project

        assert hasattr(Project, "tour_acknowledged_by")


class TestSubPhaseMinArtifactCounts:
    """min_artifact_counts 結構檢查（新 5＋7 格門檻點）。"""

    def test_field_exists_and_is_dict(self) -> None:
        for sub_id in SUB_PHASE_ORDER:
            sp = SUB_PHASES[sub_id]
            assert isinstance(sp.min_artifact_counts, dict), (
                f"{sub_id}.min_artifact_counts is not a dict"
            )

    def test_hard_cells_have_min_artifact_counts(self) -> None:
        """spec 22 v2.0 §4.3 計數型硬格（2.6/2.7 特殊鍵＝批次 C2）。"""
        for sub_id in ("1.1b", "1.2", "2.1", "2.2"):
            sp = SUB_PHASES[sub_id]
            assert sp.min_artifact_counts, (
                f"{sub_id} 缺 min_artifact_counts（artifact gate 需要）"
            )
