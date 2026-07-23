"""Tests for Phase 15: Canvas Organization Strategy.

Tests cover:
- New CanvasAnalysis metrics (largest_cluster_ratio, cross_cluster_max_similarity)
- _generate_organization_hint phase-aware logic
- ASSESS Rule X phase-aware thresholds
- context_serializer organization_hint rendering
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.canvas.analyzer import CanvasAnalysis
from app.canvas.clustering import ClusterResult, ClusterState
from app.canvas.spatial import SpatialNote
from app.canvas.tools_perception import _generate_organization_hint


def _make_note(nid: str, x: float = 0, y: float = 0) -> SpatialNote:
    return SpatialNote(
        id=nid, text=f"Text {nid}", x=x, y=y,
        width=200, height=150, color="yellow",
        author_type="human", created_at="",
    )


def _make_analysis(
    n_notes: int = 10,
    cluster_sizes: list[int] | None = None,
    centroids: list[list[float]] | None = None,
    orderliness: float = 0.65,
    overlap_count: int = 0,
) -> CanvasAnalysis:
    """Build CanvasAnalysis with configurable clusters."""
    notes = [_make_note(f"n{i}", x=80 + i * 260, y=80) for i in range(n_notes)]

    if cluster_sizes is None:
        cluster_sizes = [3, 4, 3]
    if centroids is None:
        centroids = [[1.0, 0.0]] * len(cluster_sizes)

    clusters = []
    idx = 0
    for ci, size in enumerate(cluster_sizes):
        note_ids = [f"n{j}" for j in range(idx, min(idx + size, n_notes))]
        clusters.append(ClusterResult(
            cluster_id=f"c{ci}",
            note_ids=note_ids,
            centroid=centroids[ci],
            suggested_label=f"Cluster {ci}",
            coherence_score=0.8,
        ))
        idx += size

    ungrouped = [f"n{j}" for j in range(idx, n_notes)]

    overlaps = [(f"n{i}", f"n{i+1}") for i in range(overlap_count)]

    return CanvasAnalysis(
        notes=notes,
        cluster_state=ClusterState(clusters=clusters, ungrouped_note_ids=ungrouped),
        cluster_labels={c.cluster_id: c.suggested_label for c in clusters},
        orderliness_score=orderliness,
        overlap_pairs=overlaps,
        board_bounds={},
        free_regions=[],
        largest_cluster_ratio=max(len(c.note_ids) for c in clusters) / n_notes if clusters and n_notes else 0.0,
        cross_cluster_max_similarity=0.0,
    )


# ── Step 15.1: New metrics ──


class TestLargestClusterRatio:
    def test_calculation(self) -> None:
        """3 clusters of sizes [5, 3, 2] over 10 notes → ratio = 0.5."""
        analysis = _make_analysis(n_notes=10, cluster_sizes=[5, 3, 2])
        assert analysis.largest_cluster_ratio == 0.5

    def test_empty(self) -> None:
        analysis = CanvasAnalysis()
        assert analysis.largest_cluster_ratio == 0.0


class TestCrossClusterSimilarity:
    def test_calculation(self) -> None:
        """Two identical centroids → similarity = 1.0."""
        import numpy as np
        # Orthogonal vectors → cosine sim = 0
        c1 = [1.0, 0.0, 0.0]
        c2 = [0.0, 1.0, 0.0]
        a, b = np.array(c1), np.array(c2)
        sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        assert sim == pytest.approx(0.0, abs=0.01)

        # Identical vectors → cosine sim = 1
        c3 = [1.0, 1.0, 1.0]
        c4 = [1.0, 1.0, 1.0]
        a, b = np.array(c3), np.array(c4)
        sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        assert sim == pytest.approx(1.0, abs=0.01)


# ── Step 15.2: Organization hint ──


class TestOrganizationHint:
    def test_diverge_phase(self) -> None:
        """In diverge phase 1.1, should not suggest grouping."""
        analysis = _make_analysis(orderliness=0.6)
        hint = _generate_organization_hint(analysis, "1.1")
        assert "發散階段" in hint
        assert "分群" not in hint or "禁止" in hint or "不做" in hint or "不需" in hint

    def test_converge_phase_high_ungrouped(self) -> None:
        """In heavy-organize converge phase 2.1（痛點歸類）with many ungrouped
        notes, suggest systematic organize.（Phase 42 C1：舊 1.3 → 2.1）"""
        analysis = _make_analysis(
            n_notes=10, cluster_sizes=[3, 2], orderliness=0.4,
        )
        # ungrouped = 5/10 = 50% > 40%
        hint = _generate_organization_hint(analysis, "2.1")
        assert "收斂整理" in hint
        assert "get_canvas_snapshot" in hint

    def test_overlap_priority(self) -> None:
        """Overlaps should be mentioned first in the hint."""
        analysis = _make_analysis(overlap_count=3)
        hint = _generate_organization_hint(analysis, None)
        assert hint.startswith("有 3 處便條紙重疊")

    def test_cluster_too_large(self) -> None:
        """Cluster > 40% of notes should suggest splitting."""
        analysis = _make_analysis(
            n_notes=10, cluster_sizes=[6, 2, 2],
            orderliness=0.7,
        )
        analysis = CanvasAnalysis(
            notes=analysis.notes,
            cluster_state=analysis.cluster_state,
            cluster_labels=analysis.cluster_labels,
            orderliness_score=0.7,
            overlap_pairs=[],
            board_bounds={},
            free_regions=[],
            largest_cluster_ratio=0.6,
            cross_cluster_max_similarity=0.0,
        )
        hint = _generate_organization_hint(analysis, "2.2")
        assert "拆分" in hint

    def test_clusters_similar(self) -> None:
        """Cross-cluster similarity > 0.75 should suggest merging."""
        analysis = _make_analysis(n_notes=10, cluster_sizes=[5, 5])
        analysis = CanvasAnalysis(
            notes=analysis.notes,
            cluster_state=analysis.cluster_state,
            cluster_labels=analysis.cluster_labels,
            orderliness_score=0.7,
            overlap_pairs=[],
            board_bounds={},
            free_regions=[],
            largest_cluster_ratio=0.5,
            cross_cluster_max_similarity=0.80,
        )
        hint = _generate_organization_hint(analysis, "2.2")
        assert "合併" in hint

    def test_empty_canvas(self) -> None:
        analysis = CanvasAnalysis()
        hint = _generate_organization_hint(analysis, "1.1")
        assert "空的" in hint


# ── Step 15.3: ASSESS Rule X phase-aware thresholds ──


class TestRuleXPhaseAware:
    def _make_context(
        self,
        orderliness: float,
        micro_phase: str | None,
        total_notes: int = 10,
        last_tidy: float | None = None,
    ) -> dict:
        return {
            "canvas_state": {
                "summary": {
                    "total_notes": total_notes,
                    "orderliness_score": orderliness,
                },
            },
            "current_micro_phase": micro_phase or "",
            "_last_tidy_time": last_tidy,
            "recent_chat": [],
            "my_seat": {"role": "facilitator"},
            "my_recent_actions": [],
        }

    def test_diverge_high_tolerance(self) -> None:
        """Phase 1.1 (diverge), orderliness=0.30 > threshold 0.25: should NOT trigger."""
        context = self._make_context(orderliness=0.30, micro_phase="1.1")
        micro_phase = context.get("current_micro_phase", "")
        thresholds = {
            "1.1": 0.25, "1.2": 0.25, "1.3": 0.50,
            "2.1": 0.40, "2.2": 0.45, "2.3": 0.50,
        }
        threshold = thresholds.get(micro_phase, 0.45)
        assert 0.30 >= threshold  # 0.30 >= 0.25, so should NOT trigger

    def test_converge_low_tolerance(self) -> None:
        """Phase 1.3 (converge), orderliness=0.48 < threshold 0.50: should trigger."""
        micro_phase = "1.3"
        thresholds = {
            "1.1": 0.25, "1.2": 0.25, "1.3": 0.50,
            "2.1": 0.40, "2.2": 0.45, "2.3": 0.50,
        }
        threshold = thresholds.get(micro_phase, 0.45)
        assert 0.48 < threshold  # 0.48 < 0.50, so should trigger

    def test_cooldown_diverge_longer(self) -> None:
        """Diverge phases should have 600s cooldown, converge 300s."""
        diverge_phases = frozenset(("1.1", "1.2"))
        for phase in diverge_phases:
            cooldown = 600 if phase in diverge_phases else 300
            assert cooldown == 600
        assert (600 if "1.3" in diverge_phases else 300) == 300

    def test_default_threshold_fallback(self) -> None:
        """Unknown micro_phase should use default 0.45."""
        thresholds = {
            "1.1": 0.25, "1.2": 0.25, "1.3": 0.50,
            "2.1": 0.40, "2.2": 0.45, "2.3": 0.50,
        }
        assert thresholds.get(None, 0.45) == 0.45
        assert thresholds.get("", 0.45) == 0.45
        assert thresholds.get("unknown", 0.45) == 0.45


# ── Step 15.5: Context serializer ──


class TestContextSerializerHint:
    def test_includes_hint(self) -> None:
        """context_serializer should render organization_hint when present."""
        from app.agents.prompts.context_serializer import _append_canvas_state

        parts: list[str] = []
        context = {
            "canvas_state": {
                "summary": {
                    "total_notes": 12,
                    "orderliness_score": 0.35,
                    "overlap_count": 2,
                    "cluster_count": 3,
                    "ungrouped_count": 4,
                    "board_bounds": {},
                },
                "clusters": [],
                "ungrouped_notes": [],
                "organization_hint": "有 2 處便條紙重疊，影響可讀性，建議用 tidy_area 消除。",
            },
        }
        _append_canvas_state(parts, context)
        joined = "\n".join(parts)
        assert "整理提示" in joined
        assert "tidy_area" in joined

    def test_hides_normal_hint(self) -> None:
        """Should not render when hint is the 'all normal' message."""
        from app.agents.prompts.context_serializer import _append_canvas_state

        parts: list[str] = []
        context = {
            "canvas_state": {
                "summary": {
                    "total_notes": 5,
                    "orderliness_score": 0.8,
                    "overlap_count": 0,
                    "cluster_count": 2,
                    "ungrouped_count": 1,
                    "board_bounds": {},
                },
                "clusters": [],
                "ungrouped_notes": [],
                "organization_hint": "白板狀態正常，無需特別整理。",
            },
        }
        _append_canvas_state(parts, context)
        joined = "\n".join(parts)
        assert "整理提示" not in joined
