"""Tests for AI 位置合約收斂（spec 10 v2.0 §5.3/§5.5）。

- LLM 位置語彙只剩 `group:` / `near:` / `section:`（省略＝系統放當前作用帶）；
  `grid:` / `region:` / `cluster:` 不再教（§5.3 v2.0 移除）、`color` 不再教（#34）。
- AI 的 `absolute:` / `grid:` / `region:` 逃生口封鎖：忽略並改走預設帶內落點；
  人類 `absolute:` 精準落點不變（spec 27 §7）。
- `group:<gid>` 為 `concept_group:` 的正式對外別名。
"""

from __future__ import annotations

import types
from uuid import uuid4

import pytest

from app.agents.prompts.assembler import _RESPONSE_FORMAT_BASE
from app.canvas.layout_engine import LayoutEngine
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote
from app.canvas.zones import ZONES


# ---------------------------------------------------------------------------
# prompt 教學內容
# ---------------------------------------------------------------------------


def test_prompt_no_longer_teaches_forbidden_position_formats():
    """spec 10 §5.3 v2.0：grid:/region:/cluster: 不可再出現於 LLM 輸出 → 不教。"""
    assert "grid:" not in _RESPONSE_FORMAT_BASE
    assert "region:" not in _RESPONSE_FORMAT_BASE
    assert "cluster:" not in _RESPONSE_FORMAT_BASE
    assert "target_region" not in _RESPONSE_FORMAT_BASE
    assert "absolute:" not in _RESPONSE_FORMAT_BASE


def test_prompt_teaches_semantic_position_vocabulary():
    assert "group:" in _RESPONSE_FORMAT_BASE
    assert "near:" in _RESPONSE_FORMAT_BASE
    assert "section:" in _RESPONSE_FORMAT_BASE


def test_prompt_no_longer_teaches_color_param():
    """#34：便條色＝作者席位色，由系統決定——不教 color。"""
    assert '"color"' not in _RESPONSE_FORMAT_BASE
    assert "color?" not in _RESPONSE_FORMAT_BASE


# ---------------------------------------------------------------------------
# layout engine：group: 別名
# ---------------------------------------------------------------------------


def _member(nid: str, group: str, x: float, y: float) -> SpatialNote:
    return SpatialNote(
        id=nid, text=nid, x=x, y=y, width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type="ai", created_at="",
        kind="content", concept_group_id=group,
    )


def test_group_alias_matches_concept_group():
    engine = LayoutEngine()
    notes = [_member("a", "顧客", 400, 400), _member("b", "顧客", 400, 565)]
    via_group = engine.resolve_position("group:顧客", notes)
    via_concept = engine.resolve_position("concept_group:顧客", notes)
    assert via_group == via_concept


# ---------------------------------------------------------------------------
# AI 逃生口封鎖（人類不受影響）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_registry(monkeypatch):
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project", _empty
    )


def _analysis(notes=None):
    return types.SimpleNamespace(
        notes=notes or [], cluster_state=types.SimpleNamespace(clusters=[]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "position", ["absolute:5000,9000", "grid:3,1", "region:bottom-right"]
)
async def test_ai_forbidden_position_formats_fall_back_to_band(position):
    """AI 給禁用格式 → 完全忽略、走「省略」的帶內掃位（≡ position=""）。"""
    from app.canvas.tools_manipulation import _resolve_concept_position

    engine = LayoutEngine()
    band = ZONES["icebreaker_zone"].default_bounds
    expected = engine._place_in_section(band, [], 15)

    x, y = await _resolve_concept_position(
        position=position,
        group_id=None,
        is_threaded=False,
        engine=engine,
        analysis=_analysis(),
        project_id=uuid4(),
        sub_phase_id="0.0a",
        author_type="ai",
    )
    assert (x, y) == expected
    assert band.contains(x, y)


# ---------------------------------------------------------------------------
# act 層：整面重排與 move 逃生口封鎖
# ---------------------------------------------------------------------------


@pytest.fixture()
def _act_wire(monkeypatch):
    async def _noop(*args, **kwargs):
        pass

    monkeypatch.setattr(
        "app.canvas.stability_detector.record_canvas_action", _noop
    )
    monkeypatch.setattr(
        "app.agents.act_canvas._update_last_event_ts", _noop
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["all", None])
async def test_act_layer_blocks_full_board_tidy(_act_wire, scope):
    """spec 27 §7 鐵律：tidy_area scope 缺省/all → 擋下，不執行任何搬動。"""
    from app.agents.act_canvas import execute_canvas_tool

    action = {"scope": scope} if scope is not None else {}
    res = await execute_canvas_tool(
        "tidy_area", action, uuid4(), "crew_1", "小美", sub_phase_id="2.1",
    )
    assert res["success"] is False
    assert res["error"] == "tidy_scope_forbidden"


@pytest.mark.asyncio
@pytest.mark.parametrize("to", ["absolute:100,100", "grid:2,1", "region:center"])
async def test_act_layer_blocks_forbidden_move_destination(_act_wire, to):
    from app.agents.act_canvas import execute_canvas_tool

    res = await execute_canvas_tool(
        "move_note", {"note_id": "n1", "to": to}, uuid4(), "crew_1", "小美",
        sub_phase_id="2.1",
    )
    assert res["success"] is False
    assert res["error"].startswith("forbidden_destination")


@pytest.mark.asyncio
async def test_human_absolute_still_respected():
    from app.canvas.tools_manipulation import _resolve_concept_position

    engine = LayoutEngine()
    x, y = await _resolve_concept_position(
        position="absolute:5000,9000",
        group_id=None,
        is_threaded=False,
        engine=engine,
        analysis=_analysis(),
        project_id=uuid4(),
        sub_phase_id="0.0a",
        author_type="human",
    )
    assert (x, y) == (5000.0, 9000.0)
