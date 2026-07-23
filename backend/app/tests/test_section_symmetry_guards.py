"""R1b-re：section 帶的寫路徑對稱性防護——Fable 重稽核 357f979 揪出的缺口。

357f979 修好了 create/move 的 section id 可見性與落點吸附，但「便條會進出 section
帶」的其他座標寫路徑沒有對稱掃描（成員資格純由位置衍生，gate/closing/感知三方共用）：

  ① swap_notes 無 pinned 防護 → 成員被靜默換出（退選）／牆上便條換入（幽靈入選）
  ② cluster/region tidy（_grouped_tidy）收不到 forbidden → start_y 排進選定帶
  ③ compute_arrangement 無禁區 → 排列尾端延伸進帶＝幽靈入選
  ④ move 的 section 目標解析失敗後靜默 fallback 到自動格位（move 無 gate 兜底）
  ⑤ list_sections 對「合法 JSON 但非 object」的壞資料上炸（窄 except）
  ⑥ 感知端 sections 供應斷掉零 log；section 成員被 row≥21 封存過濾隱形
  ⑦ 唯一區兜底 INFO 級＝把「LLM 沒用真 id」的訊號藏起來（升 WARNING）
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.canvas import tools_manipulation as tm
from app.canvas.layout_engine import NOTE_HEIGHT, get_layout_engine
from app.canvas.tools_manipulation import resolve_section_target
from app.canvas.zones import Bounds

_BAND = Bounds(x=100.0, y=6169.0, w=2400.0, h=700.0)
_BAND_BOTTOM = _BAND.y + _BAND.h


def _async(value):
    async def _f(*a, **k):
        return value
    return _f


def _note(nid: str, x: float, y: float, *, gid: str | None = None,
          kind: str = "content") -> SimpleNamespace:
    return SimpleNamespace(
        id=nid, x=x, y=y, cx=x + 100.0, cy=y + 95.0,
        width=200.0, height=190.0, kind=kind, concept_group_id=gid,
    )


# ── ① swap_notes ────────────────────────────────────────────────────────────


class TestSwapGuardsSectionMembers:
    @pytest.mark.asyncio
    async def test_swap_with_member_rejected(self, monkeypatch) -> None:
        member = _note("ps_sel", 400.0, 6300.0)   # 帶內（選定 PS）
        wall = _note("n_wall", 300.0, 300.0)      # 牆上
        analysis = SimpleNamespace(
            notes=[member, wall], cluster_state=SimpleNamespace(clusters=[]),
        )
        monkeypatch.setattr(
            tm, "get_spatial_analyzer",
            lambda: SimpleNamespace(analyze=_async(analysis)),
        )
        monkeypatch.setattr("app.canvas.sections.selection_members", _async([member]))
        called = {}

        async def fake_batch(*a, **k):
            called["yes"] = True
            return True

        monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

        res = await tm.tool_swap_notes(uuid4(), "ps_sel", "n_wall")

        assert res["success"] is False
        assert "section_pinned" in res["error"]
        assert "yes" not in called  # 座標完全沒被寫

    @pytest.mark.asyncio
    async def test_swap_between_wall_notes_still_works(self, monkeypatch) -> None:
        """回歸守衛：兩張牆上便條照常交換。"""
        a = _note("n_a", 300.0, 300.0)
        b = _note("n_b", 600.0, 500.0)
        analysis = SimpleNamespace(
            notes=[a, b], cluster_state=SimpleNamespace(clusters=[]),
        )
        monkeypatch.setattr(
            tm, "get_spatial_analyzer",
            lambda: SimpleNamespace(analyze=_async(analysis)),
        )
        monkeypatch.setattr("app.canvas.sections.selection_members", _async([]))
        captured = {}

        async def fake_batch(pid, coords, moved_by=None):
            captured["coords"] = {c["id"]: (c["x"], c["y"]) for c in coords}
            return True

        monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

        res = await tm.tool_swap_notes(uuid4(), "n_a", "n_b")

        assert res["success"] is True
        assert captured["coords"]["n_a"] == (600.0, 500.0)
        assert captured["coords"]["n_b"] == (300.0, 300.0)


# ── ②③ layout engine 禁區帶 ─────────────────────────────────────────────────


class TestClearForbiddenDy:
    def test_no_overlap_returns_zero(self) -> None:
        engine = get_layout_engine()
        dy = engine._clear_forbidden_dy(
            top=300.0, bottom=900.0, left=100.0, right=2000.0,
            forbidden=(_BAND,),
        )
        assert dy == 0.0

    def test_overlap_shifts_below_band(self) -> None:
        engine = get_layout_engine()
        dy = engine._clear_forbidden_dy(
            top=6000.0, bottom=6400.0, left=100.0, right=2000.0,
            forbidden=(_BAND,),
        )
        assert 6000.0 + dy >= _BAND_BOTTOM  # 整塊被移到帶下緣以下


class TestGroupedTidyAvoidsBand:
    """cluster/region tidy 的排格區塊不得排進 section 帶。"""

    def _cluster_fixture(self):
        cluster_notes = [_note(f"n{i}", 300.0 + i * 50, 300.0, gid="g1")
                         for i in range(4)]
        # 帶內成員把「既有內容最底」推到帶內 → 修復前 start_y 直接落在帶中。
        member = _note("ps_sel", 400.0, 6300.0)
        clusters = [SimpleNamespace(
            cluster_id="c1", note_ids=[n.id for n in cluster_notes],
        )]
        return cluster_notes, member, clusters

    def test_cluster_tidy_lands_below_band(self) -> None:
        engine = get_layout_engine()
        cluster_notes, member, clusters = self._cluster_fixture()

        updates = engine.compute_tidy(
            scope="cluster", target="c1", strategy="align_grid",
            notes=cluster_notes + [member], clusters=clusters,
            forbidden=(_BAND,),
        )

        assert updates  # 有排
        assert all(u.y >= _BAND_BOTTOM for u in updates), (
            "排格區塊必須整塊讓開選定帶，否則被整理的便條全部幽靈入選"
        )

    def test_label_anchors_shift_with_content(self) -> None:
        """標籤落點與內容吃同一組 forbidden，位移一致。"""
        engine = get_layout_engine()
        cluster_notes, member, clusters = self._cluster_fixture()
        common = dict(
            scope="cluster", target="c1", strategy="align_grid",
            notes=cluster_notes + [member], clusters=clusters,
        )

        updates = engine.compute_tidy(**common, forbidden=(_BAND,))
        anchors = engine.compute_group_label_anchors(**common, forbidden=(_BAND,))

        assert anchors["g1"][1] >= _BAND_BOTTOM
        # 標籤帶在內容上方：anchor y ≤ 內容最小 y
        assert anchors["g1"][1] <= min(u.y for u in updates)

    def test_without_forbidden_behavior_unchanged(self) -> None:
        """回歸守衛：無 forbidden 時沿用原落點（不因新參數漂移）。"""
        engine = get_layout_engine()
        cluster_notes, member, clusters = self._cluster_fixture()
        common = dict(
            scope="cluster", target="c1", strategy="align_grid",
            notes=cluster_notes + [member], clusters=clusters,
        )

        assert engine.compute_tidy(**common) == engine.compute_tidy(
            **common, forbidden=(),
        )


class TestArrangementAvoidsBand:
    def test_vertical_tail_shifts_below_band(self) -> None:
        """就地錨定的 vertical 排列尾端伸進帶內 → 整塊下移。"""
        engine = get_layout_engine()
        notes = [_note(f"n{i}", 300.0, 5900.0 + i * 10) for i in range(3)]

        updates = engine.compute_arrangement(
            note_ids=[n.id for n in notes], layout="vertical",
            target_region="", notes=notes, forbidden=(_BAND,),
        )

        assert all(
            u.y >= _BAND_BOTTOM or u.y + NOTE_HEIGHT <= _BAND.y for u in updates
        )
        assert all(u.y >= _BAND_BOTTOM for u in updates)  # 本例整塊下移

    def test_without_forbidden_behavior_unchanged(self) -> None:
        engine = get_layout_engine()
        notes = [_note(f"n{i}", 300.0, 5900.0 + i * 10) for i in range(3)]
        kwargs = dict(
            note_ids=[n.id for n in notes], layout="vertical",
            target_region="", notes=notes,
        )

        assert engine.compute_arrangement(**kwargs) == engine.compute_arrangement(
            **kwargs, forbidden=(),
        )


# ── ④ move 解析失敗 fail-loud ────────────────────────────────────────────────


class TestMoveSectionTargetFailLoud:
    @pytest.mark.asyncio
    async def test_unresolvable_section_move_rejected(self, monkeypatch) -> None:
        """解析不到的 section 目標 → 拒絕，不再靜默瞬移到自動格位。"""
        monkeypatch.setattr("app.canvas.sections.get_section_bounds_map", _async({}))
        monkeypatch.setattr("app.canvas.sections.list_sections", _async([]))
        called = {}

        async def fake_batch(*a, **k):
            called["yes"] = True
            return True

        monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

        res = await tm.tool_move_note(uuid4(), "n1", to="section:幻覺id")

        assert res["success"] is False
        assert "section_not_found" in res["error"]
        assert "yes" not in called  # 沒有任何座標寫入

    @pytest.mark.asyncio
    async def test_real_section_id_move_still_works(self, monkeypatch) -> None:
        """回歸守衛：真 id 照常搬進帶。"""
        sec_id = "sec_9f1c2a3b"
        monkeypatch.setattr(
            "app.canvas.sections.get_section_bounds_map",
            _async({sec_id: _BAND}),
        )
        note = _note("n1", 300.0, 300.0)
        analysis = SimpleNamespace(
            notes=[note], cluster_state=SimpleNamespace(clusters=[]),
        )
        monkeypatch.setattr(
            tm, "get_spatial_analyzer",
            lambda: SimpleNamespace(analyze=_async(analysis)),
        )
        monkeypatch.setattr(
            tm, "get_layout_engine",
            lambda: SimpleNamespace(
                resolve_position=lambda **k: (400.0, 6300.0),
            ),
        )
        captured = {}

        async def fake_batch(pid, coords, moved_by=None):
            captured["coords"] = coords
            return True

        monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

        res = await tm.tool_move_note(uuid4(), "n1", to=f"section:{sec_id}")

        assert res["success"] is True
        assert captured["coords"][0]["y"] == 6300.0


# ── 便條 id 剝前綴容錯（live 房 ff8ad088 實證的有機路徑殺手）────────────────


class TestNoteIdPrefixTolerance:
    """LLM 把 `shape:note_…` 抄成 `note_…` → move/swap/arrange/cites 全滅。"""

    def test_bare_id_gets_prefixed(self) -> None:
        notes = [_note("shape:note_123_4", 100.0, 100.0)]
        assert tm._normalize_note_id("note_123_4", notes) == "shape:note_123_4"

    def test_exact_id_passes_through(self) -> None:
        notes = [_note("shape:note_123_4", 100.0, 100.0)]
        assert tm._normalize_note_id("shape:note_123_4", notes) == "shape:note_123_4"

    def test_unknown_id_unchanged(self) -> None:
        """全不中原樣回——下游照常回報失敗，不憑空造 id。"""
        notes = [_note("shape:note_123_4", 100.0, 100.0)]
        assert tm._normalize_note_id("note_999", notes) == "note_999"

    @pytest.mark.asyncio
    async def test_move_with_bare_id_writes_real_id(self, monkeypatch) -> None:
        """實機劇本：crew 用裸 id move 進選定區 → 對齊回真 id、寫入成功。"""
        sec_id = "sec_333fd715"
        monkeypatch.setattr(
            "app.canvas.sections.get_section_bounds_map",
            _async({sec_id: _BAND}),
        )
        note = _note("shape:note_1784216033840_4", 300.0, 300.0)
        analysis = SimpleNamespace(
            notes=[note], cluster_state=SimpleNamespace(clusters=[]),
        )
        monkeypatch.setattr(
            tm, "get_spatial_analyzer",
            lambda: SimpleNamespace(analyze=_async(analysis)),
        )
        monkeypatch.setattr(
            tm, "get_layout_engine",
            lambda: SimpleNamespace(resolve_position=lambda **k: (400.0, 6300.0)),
        )
        captured = {}

        async def fake_batch(pid, coords, moved_by=None):
            captured["coords"] = coords
            return True

        monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

        res = await tm.tool_move_note(
            uuid4(), "note_1784216033840_4", to=f"section:{sec_id}",
        )

        assert res["success"] is True
        assert captured["coords"][0]["id"] == "shape:note_1784216033840_4"


# ── ⑤ list_sections 壞資料韌性 ──────────────────────────────────────────────


class TestListSectionsBadEntryTolerance:
    @pytest.mark.asyncio
    async def test_non_object_payload_skipped_with_warning(self, caplog) -> None:
        """合法 JSON 但非 object（如 '5'）→ 跳過該筆＋WARNING，不上炸。"""
        from app.canvas import sections as sections_mod

        good = '{"title": "選定區", "x": 100.0, "y": 6169.0, "w": 2400.0, "h": 700.0, "order": 1}'
        fake_redis = SimpleNamespace(
            hgetall=_async({"sec_ok": good, "sec_bad": "5"}),
            aclose=_async(None),
        )
        with (
            patch.object(sections_mod, "_get_redis", new=AsyncMock(return_value=fake_redis)),
            caplog.at_level(logging.WARNING, logger="app.canvas.sections"),
        ):
            got = await sections_mod.list_sections(uuid4())

        assert [s["id"] for s in got] == ["sec_ok"]
        assert any("Bad section entry" in r.message for r in caplog.records)


# ── ⑥ 感知：sections 供應斷掉留痕＋section 成員不被封存過濾隱形 ─────────────


class TestPerceptionResilience:
    @pytest.mark.asyncio
    async def test_sections_failure_leaves_warning(self, caplog) -> None:
        from app.canvas import tools_perception

        with (
            patch.object(
                tools_perception, "get_canvas_summary",
                new=AsyncMock(return_value={"summary": {"total_notes": 0}}),
            ),
            patch.object(
                tools_perception, "get_spatial_analyzer",
                return_value=_FakeAnalyzer([]),
            ),
            patch.object(
                tools_perception, "selection_members", new=AsyncMock(return_value=[])
            ),
            patch.object(
                tools_perception, "list_sections",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
            caplog.at_level(logging.WARNING, logger="app.canvas.tools_perception"),
        ):
            snap = await tools_perception.get_canvas_snapshot(uuid4())

        assert snap["sections"] == []
        assert any("list_sections 失敗" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_member_note_flagged_in_section(self) -> None:
        from app.canvas import tools_perception

        member = _note("r1", 400.0, 6300.0)
        member.text = "選定｜符合準則：影響力——理由"
        member.color = "yellow"
        member.author_type = "ai"
        member.author_name = "crew_1"
        member.cites = []

        with (
            patch.object(
                tools_perception, "get_canvas_summary",
                new=AsyncMock(return_value={"summary": {"total_notes": 1}}),
            ),
            patch.object(
                tools_perception, "get_spatial_analyzer",
                return_value=_FakeAnalyzer([member]),
            ),
            patch.object(
                tools_perception, "selection_members",
                new=AsyncMock(return_value=[member]),
            ),
            patch.object(
                tools_perception, "list_sections", new=AsyncMock(return_value=[])
            ),
        ):
            snap = await tools_perception.get_canvas_snapshot(uuid4())

        assert snap["notes"][0]["in_section"] is True
        assert snap["notes"][0]["selected_ps"] is False  # 理由便條非 PS

    def test_normalize_canvas_exempts_section_members(self) -> None:
        """row≥21 封存過濾：section 成員（理由便條/標籤）豁免、一般深行照濾。"""
        from app.agents.context_buffer import _normalize_canvas

        snapshot = {
            "summary": {"total_notes": 3},
            "notes": [
                {"id": "top", "grid_position": [0, 2], "text": "牆上"},
                {"id": "reason", "grid_position": [1, 22], "text": "理由",
                 "in_section": True},
                {"id": "deep", "grid_position": [1, 23], "text": "封存"},
            ],
            "clusters": [],
            "ungrouped_notes": [],
        }

        ids = {n["id"] for n in _normalize_canvas(snapshot)["spatial_notes"]}

        assert ids == {"top", "reason"}


# ── ⑦ 唯一區兜底升 WARNING ──────────────────────────────────────────────────


class TestUniqueFallbackIsObservable:
    @pytest.mark.asyncio
    async def test_unique_fallback_logs_warning(self, caplog) -> None:
        """兜底吃掉「沒用真 id」必須以 WARNING 留痕（不再 INFO 隱形）。"""
        sections = {"sec_only": _BAND}
        with (
            patch(
                "app.canvas.sections.list_sections",
                new=AsyncMock(return_value=[{"id": "sec_only", "title": "選定區"}]),
            ),
            caplog.at_level(logging.WARNING, logger="app.canvas.tools_manipulation"),
        ):
            got = await resolve_section_target(uuid4(), "section:s1", sections)

        assert got == "section:sec_only"
        assert any("唯一動態區兜底" in r.message for r in caplog.records)


class _FakeAnalyzer:
    def __init__(self, notes: list) -> None:
        self._notes = notes

    async def analyze(self, project_id, *, fresh: bool = False):
        return SimpleNamespace(
            notes=self._notes, overlap_pairs=[],
            cluster_state=SimpleNamespace(clusters=[], ungrouped_note_ids=[]),
            board_bounds=None, orderliness_score=1.0,
            largest_cluster_ratio=0.0, cross_cluster_max_similarity=0.0,
        )
