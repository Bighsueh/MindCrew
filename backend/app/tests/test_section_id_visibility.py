"""動態 section id 對 agent 可見性 — 2026-07-13 有機 live 揪出的真 bug。

根因（兩房重現）：agent 的 prompt/context 從來沒有真實 section id（grep `sec_`=0），
卻有 assembler few-shot 的 `section:s1` → crew 一律幻覺 id（抄 s1、或拿中文標題當
id）→ `section:` 解析不到 → **靜默** snap 回靜態 zone → 選定理由便條落到問題定義牆
→ `selection_members` 看不到 → 2.6 收口閘有機永遠不過，只能 forced_closure 兜底。

本檔鎖住修復後的七道防線（對齊 commit 357f979 修法①–⑦編號；R1b-re 補齊⑦守衛
並修正原檔頭「四道/五條/六組」三個數字打架的殭屍敘述）：
  ① 感知快照吐出真 section id（tools_perception）
  ② 序列化層把真 id 餵進 prompt（context_serializer）
  ③ few-shot 不再有可被抄走的假 id（assembler）
  ④ 2.6 拿得到 selection_reason 格式教學（sub_phases）
  ⑤ 幻覺 id 的容錯解析＋失敗留 WARNING（tools_manipulation.resolve_section_target）
  ⑥ 落點吸附認得 section 帶：帶內原樣放行、帶外照舊吸附（_snap_into_active_zone）
  ⑦ selection_reason prompt 教「貼進選定區＋cites 雙帶」（text_templates）

寫路徑對稱性防護（swap/tidy/arrange/move fail-loud 等）另見
test_section_symmetry_guards.py。
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.prompts.context_serializer import build_context_description
from app.canvas.tools_manipulation import resolve_section_target
from app.canvas.zones import Bounds

_SEC_ID = "sec_9f1c2a3b"
_SEC_TITLE = "選定區｜要往下做的問題"


class TestPerceptionSurfacesSectionIds:
    """① 感知快照必須帶真實 section id。"""

    @pytest.mark.asyncio
    async def test_snapshot_includes_sections(self) -> None:
        from app.canvas import tools_perception

        pid = uuid4()
        with (
            patch.object(
                tools_perception, "get_canvas_summary",
                new=AsyncMock(return_value={"summary": {"total_notes": 0}}),
            ),
            patch.object(
                tools_perception, "get_spatial_analyzer",
                return_value=_FakeAnalyzer(),
            ),
            patch.object(
                tools_perception, "selection_members", new=AsyncMock(return_value=[])
            ),
            patch.object(
                tools_perception, "list_sections",
                new=AsyncMock(return_value=[{"id": _SEC_ID, "title": _SEC_TITLE}]),
            ),
        ):
            snap = await tools_perception.get_canvas_snapshot(pid)

        assert snap["sections"] == [{"id": _SEC_ID, "title": _SEC_TITLE}]

    @pytest.mark.asyncio
    async def test_sections_unavailable_degrades_to_empty(self) -> None:
        """sections 不可達 → 空清單，不擋整個感知。"""
        from app.canvas import tools_perception

        with (
            patch.object(
                tools_perception, "get_canvas_summary",
                new=AsyncMock(return_value={"summary": {"total_notes": 0}}),
            ),
            patch.object(
                tools_perception, "get_spatial_analyzer",
                return_value=_FakeAnalyzer(),
            ),
            patch.object(
                tools_perception, "selection_members", new=AsyncMock(return_value=[])
            ),
            patch.object(
                tools_perception, "list_sections",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
        ):
            snap = await tools_perception.get_canvas_snapshot(uuid4())

        assert snap["sections"] == []


class TestSerializerFeedsRealId:
    """② 真 id 必須出現在 LLM 讀得到的 prompt 文字裡。"""

    def test_section_block_rendered_with_real_id(self) -> None:
        out = build_context_description({
            "canvas_state": {
                "summary": {"total_notes": 3},
                "sections": [{"id": _SEC_ID, "title": _SEC_TITLE}],
            },
        })
        assert _SEC_ID in out
        assert _SEC_TITLE in out
        assert "不可自己編" in out

    def test_no_sections_no_block(self) -> None:
        out = build_context_description({
            "canvas_state": {"summary": {"total_notes": 3}, "sections": []},
        })
        assert "白板動態區" not in out


class TestFewShotHasNoFakeSectionId:
    """③ few-shot 不得再出現可被原樣抄走的假 id。"""

    def test_assembler_response_format_drops_section_s1(self) -> None:
        from app.agents.prompts.assembler import _RESPONSE_FORMAT_BASE

        assert "section:s1" not in _RESPONSE_FORMAT_BASE

    def test_no_copyable_section_literal_at_all(self) -> None:
        """R1b-re 收緊：原守衛只鎖字面 `section:s1`，任何其他假 id（s2、sec_ 樣
        貌的假 id…）復發都擋不住。`section:` 後只允許佔位符開頭（`【`＝指向
        【白板動態區】、`<`＝角括號佔位）——真 id 樣貌的字面一律禁止。"""
        import re

        from app.agents.prompts.assembler import _RESPONSE_FORMAT_BASE

        # 只抓 id 樣貌（ASCII 英數/底線）的字面：`section:s1`／`section:sec_xxx`
        # 都會中；佔位符（`section:【…】`、`section:<…>`）與散文（`section:）。`）
        # 不會誤傷。
        bad = re.findall(r"section:[A-Za-z0-9_]+", _RESPONSE_FORMAT_BASE)
        assert bad == [], f"few-shot 出現可被抄走的 section id 字面：{bad}"


class TestSectionTargetTolerance:
    """⑤ 幻覺 id 容錯 ＋ 解析失敗必須留 WARNING（不再靜默落錯牆）。"""

    _SECTIONS = {_SEC_ID: Bounds(x=100.0, y=8000.0, w=2400.0, h=700.0)}

    @pytest.mark.asyncio
    async def test_real_id_passes_through(self) -> None:
        got = await resolve_section_target(
            uuid4(), f"section:{_SEC_ID}", self._SECTIONS
        )
        assert got == f"section:{_SEC_ID}"

    @pytest.mark.asyncio
    async def test_title_fragment_resolves(self) -> None:
        """實機幻覺：`section:選定區`（拿中文標題當 id）。"""
        with patch(
            "app.canvas.sections.list_sections",
            new=AsyncMock(return_value=[{"id": _SEC_ID, "title": _SEC_TITLE}]),
        ):
            got = await resolve_section_target(
                uuid4(), "section:選定區", self._SECTIONS
            )
        assert got == f"section:{_SEC_ID}"

    @pytest.mark.asyncio
    async def test_hallucinated_id_falls_back_to_only_section(self) -> None:
        """實機幻覺：`section:s1`（抄 few-shot）→ 全場唯一動態區。"""
        with patch(
            "app.canvas.sections.list_sections",
            new=AsyncMock(return_value=[{"id": _SEC_ID, "title": _SEC_TITLE}]),
        ):
            got = await resolve_section_target(uuid4(), "section:s1", self._SECTIONS)
        assert got == f"section:{_SEC_ID}"

    @pytest.mark.asyncio
    async def test_unresolvable_returns_none_and_warns(self, caplog) -> None:
        """多條 section＋對不上任何標題 → None＋WARNING（不再靜默）。"""
        two = {
            "sec_aaa": Bounds(x=100.0, y=8000.0, w=2400.0, h=700.0),
            "sec_bbb": Bounds(x=100.0, y=8900.0, w=2400.0, h=700.0),
        }
        with (
            patch(
                "app.canvas.sections.list_sections",
                new=AsyncMock(return_value=[
                    {"id": "sec_aaa", "title": "選定區"},
                    {"id": "sec_bbb", "title": "備選區"},
                ]),
            ),
            caplog.at_level(logging.WARNING, logger="app.canvas.tools_manipulation"),
        ):
            got = await resolve_section_target(uuid4(), "section:s1", two)

        assert got is None
        assert any("section target 解析失敗" in r.message for r in caplog.records)


class TestSnapDoesNotYankNotesOutOfSections:
    """⑥ 落點吸附器必須認得動態 section（R1-b 最後一層）。

    實機（房 eda7c8b8）：crew 用 `near:<選定區裡的PS>` 貼選定理由，落點正確算在
    選定區帶內，卻被 `_snap_into_active_zone` 扯回問題定義牆（zone=pov_wall）→
    selection_members 看不到 → 收口閘照樣不過。gate 已接受 section 落點（R1），
    吸附器不對稱就會把 R1 的修復整個抵銷。
    """

    @pytest.mark.asyncio
    async def test_point_inside_section_is_left_alone(self) -> None:
        from app.canvas import tools_manipulation as tm

        pid = uuid4()
        inside = (400.0, 6300.0)  # 選定區帶內
        section = {"id": _SEC_ID, "title": _SEC_TITLE,
                   "x": 100.0, "y": 6169.0, "w": 2400.0, "h": 700.0}

        with patch(
            "app.canvas.sections.list_sections",
            new=AsyncMock(return_value=[section]),
        ):
            got = await tm._snap_into_active_zone(
                inside[0], inside[1], "2.6", pid, engine=object(), notes=[],
            )

        assert got == inside  # 原樣回，不被吸走

    @pytest.mark.asyncio
    async def test_point_outside_any_section_still_snaps(self, monkeypatch) -> None:
        """回歸守衛：不在 section 內的落點，照舊吸進 active zone。"""
        from app.canvas import tools_manipulation as tm

        async def _no_sections(*_a, **_k):
            return []

        async def _no_registry(*_a, **_k):
            return {}

        monkeypatch.setattr("app.canvas.sections.list_sections", _no_sections)
        monkeypatch.setattr(tm, "get_all_zones_for_project", _no_registry)

        class _Engine:
            def _place_in_section(self, b, notes, spacing, forbidden=()):
                return (b.x + 40, b.y + 40)

        got = await tm._snap_into_active_zone(
            99999.0, 99999.0, "2.6", uuid4(), engine=_Engine(), notes=[],
        )
        assert got != (99999.0, 99999.0)  # 被吸進 active zone


class TestSubPhase26TeachesReasonFormat:
    """④ 2.6 是唯一漏掛 templates 的產出關——crew 從沒看過選定理由格式。"""

    def test_2_6_has_selection_reason_template(self) -> None:
        from app.stages.sub_phases import SUB_PHASES

        assert "selection_reason" in SUB_PHASES["2.6"].templates

    def test_2_6_prompt_shows_reason_format(self) -> None:
        from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt

        out = build_sub_phase_prompt("2.6")
        assert "選定" in out and "符合準則" in out


class TestSelectionReasonPromptTeachesPlacement:
    """⑦ selection_reason 的 AI 提示：貼進選定區＋cites 同時帶問題定義與準則 id。

    R1b-re 補守衛——357f979 修法⑦是純 prompt 文字、原本零測試，被改掉不會有任何
    訊號；而 2.6 收口閘的配對判定實際依賴這段教學（cites 雙帶）。"""

    def test_prompt_teaches_section_placement_and_dual_cites(self) -> None:
        from app.canvas.text_templates import TEMPLATES

        p = TEMPLATES["selection_reason"].prompt_zh
        assert "section:" in p           # 教貼進選定區
        assert "問題定義" in p and "準則" in p  # 教 cites 雙帶


class _FakeAnalyzer:
    async def analyze(self, project_id, *, fresh: bool = False):
        import types

        return types.SimpleNamespace(
            notes=[], overlap_pairs=[],
            cluster_state=types.SimpleNamespace(clusters=[]),
        )
