"""Move-delta 可讀事件管線測試 — Phase 42 C0，spec 10 v2.0 §4.7。

涵蓋：
1. context_serializer：canvas_moves fixture → 確定性自然語句渲染
2. move_ingest：Redis cursor 防重複（真 Redis、mock sidecar 事件）
3. 真人 move 事件 → round_lock.register_human_input("move") 的接線
4. 事件語意化：區名反推（動態 section 優先）、真人顯示名
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.agents.prompts.context_serializer import build_context_description
from app.canvas import move_ingest as ingest_mod
from app.canvas.move_ingest import _area_name, _enrich, ingest_moves
from app.config import settings


# ---------------------------------------------------------------------------
# 1. serializer 渲染（確定性字串）
# ---------------------------------------------------------------------------


def _base_context(moves: list[dict]) -> dict:
    return {
        "project_name": "測試專案",
        "current_stage": "define",
        "stage_duration_minutes": 3,
        "canvas_state": {},
        "recent_chat": [],
        "seats": [],
        "my_seat": "crew_a",
        "my_recent_actions": [],
        "blackboard": {},
        "canvas_moves": moves,
    }


class TestSerializerRendering:
    def test_renders_human_move_sentence(self) -> None:
        moves = [
            {
                "moved_by": "陳柏宇",
                "is_human": True,
                "content": "客服電話等很久",
                "from_area": "還沒歸類的痛點",
                "to_area": "選定區",
                "from_group": None,
                "to_group": None,
                "neighbors": [{"content": "排隊排到放棄", "group_id": None}],
            }
        ]
        text = build_context_description(_base_context(moves))
        assert "【白板最近的移動】" in text
        assert (
            "陳柏宇（真人） 把便條「客服電話等很久」從「還沒歸類的痛點」"
            "搬到「選定區」，現在它旁邊是「排隊排到放棄」。"
        ) in text

    def test_renders_group_change_and_caps_at_five(self) -> None:
        moves = [
            {
                "moved_by": "小美",
                "is_human": False,
                "content": f"概念{i}",
                "from_area": "A 區",
                "to_area": "B 區",
                "from_group": None,
                "to_group": "顧客",
                "neighbors": [],
            }
            for i in range(7)
        ]
        text = build_context_description(_base_context(moves))
        assert "歸進「顧客」群" in text
        # 只渲染近 5 筆
        assert "概念2" in text and "概念6" in text
        assert "概念0" not in text and "概念1" not in text

    def test_no_moves_no_section(self) -> None:
        text = build_context_description(_base_context([]))
        assert "【白板最近的移動】" not in text


# ---------------------------------------------------------------------------
# 2/3. ingest：cursor 防重 + 真人 move 解鎖接線（真 Redis）
# ---------------------------------------------------------------------------


def _sidecar_event(seq: int, *, is_human: bool = False) -> dict:
    return {
        "seq": seq,
        "note_id": f"shape:note_{seq}",
        "content": f"概念{seq}",
        "moved_by": "__human__" if is_human else "小美(ai)",
        "is_human": is_human,
        "before": {"x": 200, "y": 200, "group_id": None},
        "after": {"x": 500, "y": 200, "group_id": "顧客"},
        "neighbors_after": [{"id": "n9", "content": "鄰居", "group_id": None}],
        "moved_at": "2026-06-12T00:00:00Z",
    }


@pytest.fixture
def _ingest_env(monkeypatch):
    """Mock sidecar 事件來源與 DB facts；Redis 用真的（cursor / canvas_moves）。"""
    state: dict = {"events": [], "latest_seq": 0, "human_calls": []}

    async def _fake_get_move_events(self, project_id, since=0):
        events = [e for e in state["events"] if e["seq"] > since]
        return {"events": events, "latest_seq": state["latest_seq"]}

    from app.bridge.canvas_ops import CanvasOps

    monkeypatch.setattr(CanvasOps, "get_move_events", _fake_get_move_events)

    async def _fake_facts(project_id):
        return "2.1", "陳柏宇"

    monkeypatch.setattr(ingest_mod, "_project_facts", _fake_facts)

    async def _empty_zones(project_id):
        return {}

    async def _no_sections(project_id):
        return []

    monkeypatch.setattr(ingest_mod, "get_all_zones_for_project", _empty_zones)
    monkeypatch.setattr(ingest_mod, "list_sections", _no_sections)

    async def _fake_register(project_id, sub_phase, input_type):
        state["human_calls"].append((sub_phase, input_type))
        return True

    import app.agents.round_lock as round_lock_mod

    monkeypatch.setattr(round_lock_mod, "register_human_input", _fake_register)
    return state


async def _read_moves(project_id) -> list[dict]:
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        raw = await r.lrange(f"canvas_moves:{project_id}", 0, -1)
        return [json.loads(m) for m in raw]
    finally:
        await r.aclose()


async def _cleanup(project_id) -> None:
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.delete(
            f"canvas_moves:{project_id}", f"move_events:cursor:{project_id}"
        )
    finally:
        await r.aclose()


@pytest.mark.asyncio
class TestIngestCursor:
    async def test_cursor_prevents_duplicates(self, _ingest_env) -> None:
        project_id = uuid4()
        try:
            _ingest_env["events"] = [_sidecar_event(1), _sidecar_event(2)]
            _ingest_env["latest_seq"] = 2

            assert await ingest_moves(project_id) == 2
            # 同一批再 ingest → cursor 已前進，不重複
            assert await ingest_moves(project_id) == 0
            moves = await _read_moves(project_id)
            assert len(moves) == 2

            # 新事件進來 → 只消化新的
            _ingest_env["events"].append(_sidecar_event(3))
            _ingest_env["latest_seq"] = 3
            assert await ingest_moves(project_id) == 1
            assert len(await _read_moves(project_id)) == 3
        finally:
            await _cleanup(project_id)

    async def test_human_move_registers_round_lock(self, _ingest_env) -> None:
        project_id = uuid4()
        try:
            _ingest_env["events"] = [_sidecar_event(1, is_human=True)]
            _ingest_env["latest_seq"] = 1
            await ingest_moves(project_id)
            assert _ingest_env["human_calls"] == [("2.1", "move")]

            # 真人顯示名由席位解析、AI tag 去後綴
            moves = await _read_moves(project_id)
            assert moves[0]["moved_by"] == "陳柏宇"
            assert moves[0]["is_human"] is True
        finally:
            await _cleanup(project_id)

    async def test_ai_move_does_not_register(self, _ingest_env) -> None:
        project_id = uuid4()
        try:
            _ingest_env["events"] = [_sidecar_event(1, is_human=False)]
            _ingest_env["latest_seq"] = 1
            await ingest_moves(project_id)
            assert _ingest_env["human_calls"] == []
            moves = await _read_moves(project_id)
            assert moves[0]["moved_by"] == "小美"
        finally:
            await _cleanup(project_id)


# ---------------------------------------------------------------------------
# 4. 區名反推與事件語意化（純函式）
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_section_takes_priority_over_zone(self) -> None:
        sections = [{"id": "sec_a", "title": "選定區", "x": 100, "y": 3000, "w": 2400, "h": 700}]
        assert _area_name(200, 3100, "2.6", {}, sections) == "選定區"

    def test_zone_fallback_then_unzoned(self) -> None:
        # RC1 帶模型：2.1 的牆＝pain_wall（default 帶 y=2540..3540）；框標題留空後
        # in-scene 短名由 ZONE_NAMES_ZH 供應（#13）。
        name = _area_name(200, 2700, "2.1", {}, [])
        assert name == "痛點牆"
        assert _area_name(99999, 99999, "2.1", {}, []) == "未分區"

    def test_enrich_shapes_event(self) -> None:
        enriched = _enrich(
            _sidecar_event(5), sub_phase="2.1", zone_bounds={}, sections=[],
            human_name="陳柏宇",
        )
        assert enriched["moved_by"] == "小美"
        assert enriched["to_group"] == "顧客"
        assert enriched["neighbors"] == [{"content": "鄰居", "group_id": None}]
