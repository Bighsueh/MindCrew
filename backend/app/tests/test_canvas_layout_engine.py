"""Tests for canvas layout engine (Phase 14, Step 14.6)."""

import pytest

from app.canvas.clustering import ClusterResult
from app.canvas.layout_engine import LayoutEngine, CoordinateUpdate
from app.canvas.spatial import SpatialNote, NOTE_WIDTH, NOTE_HEIGHT


def _make_note(
    id: str, x: float, y: float,
    width: float = NOTE_WIDTH, height: float = NOTE_HEIGHT,
) -> SpatialNote:
    return SpatialNote(
        id=id, text="test", x=x, y=y,
        width=width, height=height,
        color="yellow", author_type="human", created_at="",
    )


@pytest.fixture
def engine() -> LayoutEngine:
    return LayoutEngine()


class TestResolvePosition:
    def test_grid_format(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("grid:2,1", [])
        assert x > 0 and y > 0

    def test_near_format(self, engine: LayoutEngine) -> None:
        ref = _make_note("n1", 100, 100)
        x, y = engine.resolve_position("near:n1", [ref])
        # Should be adjacent to n1, not on top of it
        assert not (x == 100 and y == 100)

    def test_region_format(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("region:bottom-right", [])
        assert x > 0 and y > 0

    def test_cluster_format(self, engine: LayoutEngine) -> None:
        notes = [
            _make_note("n1", 100, 100),
            _make_note("n2", 150, 120),
        ]
        cluster = ClusterResult(
            cluster_id="c1", note_ids=["n1", "n2"],
            centroid=[0.0], coherence_score=0.9,
        )
        x, y = engine.resolve_position("cluster:c1", notes, clusters=[cluster])
        # Should be near the cluster members
        assert 0 < x < 2000
        assert 0 < y < 2000

    def test_fallback_on_invalid(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("invalid:xyz", [])
        assert x >= 0 and y >= 0


class TestComputeArrangement:
    def test_grid_layout(self, engine: LayoutEngine) -> None:
        notes = [_make_note(f"n{i}", i * 300, 0) for i in range(6)]
        ids = [f"n{i}" for i in range(6)]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="grid", target_region="top-left",
            notes=notes, columns=3,
        )
        assert len(updates) == 6
        # Check non-overlapping: no two notes at same position
        positions = {(u.x, u.y) for u in updates}
        assert len(positions) == 6

    def test_horizontal_layout(self, engine: LayoutEngine) -> None:
        ids = ["n1", "n2", "n3"]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="horizontal", target_region="center",
            notes=notes,
        )
        assert len(updates) == 3
        # All same y, increasing x
        ys = {u.y for u in updates}
        assert len(ys) == 1  # all same row

    def test_vertical_layout(self, engine: LayoutEngine) -> None:
        ids = ["n1", "n2", "n3"]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="vertical", target_region="center",
            notes=notes,
        )
        assert len(updates) == 3
        xs = {u.x for u in updates}
        assert len(xs) == 1  # all same column

    def test_circular_layout(self, engine: LayoutEngine) -> None:
        ids = [f"n{i}" for i in range(5)]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="circular", target_region="center",
            notes=notes,
        )
        assert len(updates) == 5


def _grouped_note(
    id: str, group: str | None, kind: str = "content",
) -> SpatialNote:
    return SpatialNote(
        id=id, text=f"text-{id}", x=0, y=0, width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type="ai", created_at="",
        kind=kind, concept_group_id=group,
    )


class TestComputeTidy:
    def test_tidy_all(self, engine: LayoutEngine) -> None:
        notes = [_make_note(f"n{i}", i * 50, i * 50) for i in range(5)]
        updates = engine.compute_tidy(
            scope="all", target=None, strategy="align_grid",
            notes=notes,
        )
        assert len(updates) == 5

    def test_tidy_empty(self, engine: LayoutEngine) -> None:
        updates = engine.compute_tidy(
            scope="all", target=None, strategy="align_grid",
            notes=[],
        )
        assert len(updates) == 0


class TestGroupedTidy:
    """病根 E：整理依 concept_group_id 排成欄、各群分開、冪等。"""

    def _two_group_notes(self) -> list[SpatialNote]:
        return (
            [_grouped_note(f"k{i}", "顧客") for i in range(3)]
            + [_grouped_note(f"d{i}", "店員") for i in range(2)]
        )

    def test_groups_occupy_separate_columns(self, engine: LayoutEngine) -> None:
        notes = self._two_group_notes()
        updates = engine.compute_tidy("all", None, "align_grid", notes)
        pos = {u.id: (u.x, u.y) for u in updates}
        kehu_xs = {pos[f"k{i}"][0] for i in range(3)}
        dianyuan_xs = {pos[f"d{i}"][0] for i in range(2)}
        # 同群同欄（x 相同）、兩群不同欄（x 不重疊）。
        assert len(kehu_xs) == 1 and len(dianyuan_xs) == 1
        assert kehu_xs.isdisjoint(dianyuan_xs)

    def test_idempotent(self, engine: LayoutEngine) -> None:
        notes = self._two_group_notes()
        first = engine.compute_tidy("all", None, "align_grid", notes)
        # 套用第一次結果後再整理一次 → 完全相同座標（不閃動）。
        moved = []
        fmap = {u.id: u for u in first}
        for n in notes:
            u = fmap[n.id]
            moved.append(_grouped_note(n.id, n.concept_group_id))
            moved[-1] = SpatialNote(
                id=n.id, text=n.text, x=u.x, y=u.y, width=NOTE_WIDTH, height=NOTE_HEIGHT,
                color="yellow", author_type="ai", created_at="",
                kind="content", concept_group_id=n.concept_group_id,
            )
        second = engine.compute_tidy("all", None, "align_grid", moved)
        assert {(u.id, u.x, u.y) for u in first} == {(u.id, u.x, u.y) for u in second}

    def test_label_anchors_above_content(self, engine: LayoutEngine) -> None:
        notes = self._two_group_notes()
        anchors = engine.compute_group_label_anchors("all", None, "align_grid", notes)
        updates = {u.id: u for u in engine.compute_tidy("all", None, "align_grid", notes)}
        assert set(anchors.keys()) == {"顧客", "店員"}
        # 標籤 y 在該群內容之上。
        assert anchors["顧客"][1] < updates["k0"].y
        # 標籤 x 與該群欄對齊。
        assert anchors["顧客"][0] == updates["k0"].x

    def test_label_notes_excluded_from_columns(self, engine: LayoutEngine) -> None:
        notes = self._two_group_notes() + [_grouped_note("lbl", "顧客", kind="label")]
        updates = engine.compute_tidy("all", None, "align_grid", notes)
        # label 便條不在內容欄更新中。
        assert all(u.id != "lbl" for u in updates)


def _placed_note(
    id: str, group: str | None, x: float, y: float,
    kind: str = "content", author_type: str = "ai",
) -> SpatialNote:
    return SpatialNote(
        id=id, text=f"text-{id}", x=x, y=y, width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type=author_type, created_at="",
        kind=kind, concept_group_id=group,
    )


class TestGroupScopeTidy:
    """spec 10 v2.0 §5.7 scope=group：就地收攏單一群（auto_reflow 保底用）。

    與 scope=all 的差異：錨在該群自己的左上角（不搬到全板最下方）、
    不動其他群、只送有變化的差異。
    """

    def _scattered_group(self) -> list[SpatialNote]:
        return [
            _placed_note("g0", "顧客", 300, 300),
            _placed_note("g1", "顧客", 900, 700),
            _placed_note("g2", "顧客", 1400, 350),
            _placed_note("o0", "店員", 300, 1500),  # 他群，不得動
        ]

    def test_group_tidy_anchors_in_place(self, engine: LayoutEngine) -> None:
        notes = self._scattered_group()
        updates = engine.compute_tidy("group", "顧客", "align_grid", notes)
        ids = {u.id for u in updates}
        assert "o0" not in ids  # 他群不動
        pos = {u.id: (u.x, u.y) for u in updates}
        for n in notes[:3]:
            pos.setdefault(n.id, (n.x, n.y))
        # 錨點＝群成員原 min(x), min(y)（就地收攏，不跳到板底）。
        assert min(pos[f"g{i}"][0] for i in range(3)) == 300
        assert min(pos[f"g{i}"][1] for i in range(3)) == 300

    def test_group_tidy_result_has_no_overlap(self, engine: LayoutEngine) -> None:
        notes = self._scattered_group()
        updates = {u.id: u for u in engine.compute_tidy("group", "顧客", "align_grid", notes)}
        final = []
        for n in notes:
            u = updates.get(n.id)
            final.append(
                _placed_note(n.id, n.concept_group_id, u.x if u else n.x, u.y if u else n.y)
            )
        from app.canvas.spatial import detect_overlaps
        assert not detect_overlaps(final)

    def test_group_tidy_idempotent_and_diff_only(self, engine: LayoutEngine) -> None:
        notes = self._scattered_group()
        first = {u.id: u for u in engine.compute_tidy("group", "顧客", "align_grid", notes)}
        moved = [
            _placed_note(
                n.id, n.concept_group_id,
                first[n.id].x if n.id in first else n.x,
                first[n.id].y if n.id in first else n.y,
            )
            for n in notes
        ]
        # 已在目標位 → 不再送任何差異（不經 Yjs 造成閃動）。
        second = engine.compute_tidy("group", "顧客", "align_grid", moved)
        assert second == []

    def test_group_tidy_avoids_other_groups_notes(self, engine: LayoutEngine) -> None:
        notes = self._scattered_group() + [_placed_note("blocker", "店員", 300, 465)]
        updates = {u.id: u for u in engine.compute_tidy("group", "顧客", "align_grid", notes)}
        final = []
        for n in notes:
            u = updates.get(n.id)
            final.append(
                _placed_note(n.id, n.concept_group_id, u.x if u else n.x, u.y if u else n.y)
            )
        from app.canvas.spatial import detect_overlaps
        assert not detect_overlaps(final)

    def test_group_label_anchor_above_group(self, engine: LayoutEngine) -> None:
        notes = self._scattered_group()
        anchors = engine.compute_group_label_anchors("group", "顧客", "align_grid", notes)
        assert set(anchors) == {"顧客"}
        ax, ay = anchors["顧客"]
        assert ax == 300
        assert ay < 300  # 標籤在群內容之上


class TestCollisionDetection:
    def test_no_collision(self, engine: LayoutEngine) -> None:
        notes = [_make_note("n1", 0, 0)]
        assert not engine._has_collision(500, 500, NOTE_WIDTH, NOTE_HEIGHT, notes)

    def test_collision(self, engine: LayoutEngine) -> None:
        notes = [_make_note("n1", 0, 0)]
        assert engine._has_collision(50, 50, NOTE_WIDTH, NOTE_HEIGHT, notes)


class TestFindNonCollidingNeverOverlaps:
    """病根 C-2：區域被填滿、螺旋搜尋耗盡時，舊 fallback 回傳 (x+W+gap, y) 會「保證重疊」。

    修復後：對任何飽和集合，``_find_non_colliding`` 都必須回傳不重疊落點。
    """

    def test_saturated_field_returns_free_slot(self, engine: LayoutEngine) -> None:
        from app.canvas.layout_engine import SPACING_VALUES

        # 以 100px 步距密鋪（便條 200x150 > 步距 → 連續覆蓋），範圍大於螺旋可達距離
        # （20 圈 × ~215px ≈ 4300px），逼出 fallback 路徑。
        notes = [
            _make_note(f"n{c}-{r}", c * 100, r * 100)
            for c in range(96)
            for r in range(73)
        ]
        x, y = engine._find_non_colliding(
            4750, 3600, notes, SPACING_VALUES["default"]
        )
        assert not engine._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes)

    def test_empty_notes_returns_seed(self, engine: LayoutEngine) -> None:
        x, y = engine._find_non_colliding(500, 500, [], 15)
        assert not engine._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, [])
