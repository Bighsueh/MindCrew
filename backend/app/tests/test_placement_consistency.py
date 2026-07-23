"""Tests for RC3 放置一致性 — per-project 放置鎖＋寫後一致新鮮讀＋預設帶內落點＋座標夾制。

根因（rootcause 2026-06-21 RC3）：落點計算吃 3 秒 Redis 快取、讀-算-寫無鎖，
兩個 agent 併發貼會讀同一份過期快照、各自算出「不碰撞」卻撞在一起；
預設 ``region:center`` 讓所有沒帶 position 的便條往板中心堆。
"""

from __future__ import annotations

import asyncio
import types
from uuid import uuid4

import pytest

from app.canvas.analyzer import CanvasAnalysis, SpatialAnalyzer
from app.canvas.clustering import ClusterState
from app.canvas.layout_engine import get_layout_engine
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote, detect_overlaps
from app.canvas.zones import ZONES


# ---------------------------------------------------------------------------
# fresh=True 繞過讀快取（寫後一致）
# ---------------------------------------------------------------------------


def _shape(nid: str, x: float, y: float) -> dict:
    return {"id": nid, "content": nid, "x": x, "y": y, "width": 200, "height": 150}


@pytest.mark.asyncio
async def test_fresh_bypasses_read_cache(monkeypatch):
    analyzer = SpatialAnalyzer.__new__(SpatialAnalyzer)  # 不觸發 embedding client

    async def _cached(self, key):
        return SpatialAnalyzer._deserialize_notes([_shape("stale", 1, 1)])

    async def _fetch(self, project_id):
        return [_shape("live", 2, 2)]

    async def _write(self, key, shapes):
        pass

    monkeypatch.setattr(SpatialAnalyzer, "_read_state_cache", _cached)
    monkeypatch.setattr(SpatialAnalyzer, "_fetch_full_state", _fetch)
    monkeypatch.setattr(SpatialAnalyzer, "_write_state_cache", _write)

    pid = uuid4()
    stale = await analyzer.get_full_state(pid)
    assert [n.id for n in stale] == ["stale"]

    live = await analyzer.get_full_state(pid, fresh=True)
    assert [n.id for n in live] == ["live"]


# ---------------------------------------------------------------------------
# 預設落點（position 省略）＝當前作用帶的空位（spec 10 §5.5）
# ---------------------------------------------------------------------------


@pytest.fixture()
def _no_registry(monkeypatch):
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project", _empty
    )


@pytest.mark.asyncio
async def test_omitted_position_lands_in_active_band(_no_registry):
    from app.canvas.tools_manipulation import _resolve_concept_position

    analysis = types.SimpleNamespace(
        notes=[], cluster_state=types.SimpleNamespace(clusters=[]),
    )
    x, y = await _resolve_concept_position(
        position="",
        group_id=None,
        is_threaded=False,
        engine=get_layout_engine(),
        analysis=analysis,
        project_id=uuid4(),
        sub_phase_id="0.0a",
    )
    b = ZONES["icebreaker_zone"].default_bounds
    assert b.contains(x, y)
    # 帶內掃描（左上內容列），不是板中心 (790, 1000)。
    assert y < b.y + b.h / 2


# ---------------------------------------------------------------------------
# 座標夾制（AI 落點永不為負）
# ---------------------------------------------------------------------------


def test_clamp_to_board_floors_negative_coords():
    from app.canvas.tools_manipulation import _clamp_to_board

    assert _clamp_to_board(-126.9, -5.0) == (20.0, 20.0)
    assert _clamp_to_board(500.0, 700.0) == (500.0, 700.0)


# ---------------------------------------------------------------------------
# per-project 放置鎖：併發 create 不互疊
# ---------------------------------------------------------------------------


class _FakeBoard:
    """共享假白板：add_note 有 I/O 延遲，用來拉大 race window。"""

    def __init__(self):
        self.notes: list[SpatialNote] = []
        self._n = 0

    def analysis(self) -> CanvasAnalysis:
        return CanvasAnalysis(
            notes=list(self.notes), cluster_state=ClusterState(),
        )

    async def add_note(self, project_id, content, position, **kwargs):
        await asyncio.sleep(0.02)  # 模擬 sidecar HTTP 往返
        self._n += 1
        nid = f"n{self._n}"
        self.notes.append(
            SpatialNote(
                id=nid, text=content, x=position["x"], y=position["y"],
                width=NOTE_WIDTH, height=NOTE_HEIGHT, color="yellow",
                author_type="ai", created_at="",
            )
        )
        return nid


@pytest.mark.asyncio
async def test_concurrent_creates_do_not_overlap(_no_registry, monkeypatch):
    from app.canvas import tools_manipulation as tm

    board = _FakeBoard()
    stale_snapshot = board.analysis()  # 兩個 agent 都拿到「空白板」的過期快照

    class _FakeAnalyzer:
        async def analyze(self, project_id, *, fresh: bool = False):
            # RC3 情境：非 fresh 讀到共同的過期快照；fresh 讀到即時狀態。
            return board.analysis() if fresh else stale_snapshot

        async def invalidate_semantic_cache(self, project_id):
            pass

        async def invalidate_full_state_cache(self, project_id):
            pass

    fake_ops = types.SimpleNamespace(add_note=board.add_note)

    async def _gate_pass(text, modules, **kwargs):
        return types.SimpleNamespace(
            passed=True, violated_rule=None, violated_module=None,
            matched_text=None, message_zh=None,
        )

    monkeypatch.setattr(tm, "get_spatial_analyzer", lambda: _FakeAnalyzer())
    monkeypatch.setattr(tm, "canvas_ops", fake_ops)
    monkeypatch.setattr(tm, "check_text_with_llm", _gate_pass)

    pid = uuid4()
    r1, r2 = await asyncio.gather(
        tm.tool_create_note(
            project_id=pid, text="想法甲：野餐墊", author_name="crew_1",
            sub_phase_id="0.0a",
        ),
        tm.tool_create_note(
            project_id=pid, text="想法乙：遮陽帽", author_name="crew_2",
            sub_phase_id="0.0a",
        ),
    )

    assert r1["success"] and r2["success"]
    assert len(board.notes) == 2
    assert not detect_overlaps(board.notes), [
        (n.id, n.x, n.y) for n in board.notes
    ]
