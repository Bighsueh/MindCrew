"""Artifact gate contract tests（spec 25 v2.0，Phase 42 C2）.

新計數語意：
- stakeholder／pain_point＝牆面計數（zone 內 kind != label；spec 25 §2.3）
- 1.2 結構附加條件：每個高優先群 ≥1 張痛點（reasons_zh 大白話）
- 2.1 主題群數＝痛點牆內掛痛點的相異 group_id；2.2 problem_statement 計入需 cites≥2
- 特殊鍵 selection_pairing（2.6）／hmw_pairing（2.7）＝C2 落地（§3.2/§3.3）
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.canvas.artifact_gate import (
    SPECIAL_KEYS,
    ArtifactGateResult,
    _aggregate_template_counts,
    _classify_text,
    _evaluate_hmw_pairing,
    _evaluate_selection_pairing,
    _high_priority_group_reasons,
    check_artifact_gate,
    format_gate_rejection_zh,
)
from app.canvas.zones import Bounds

pytestmark = pytest.mark.asyncio


# RC1 帶模型預設 bounds：stakeholder_public=(100,1620,2000,800)、pain_wall=(100,2540,2200,1000)。
_STAKEHOLDER_XY = (200.0, 1700.0)
_PAIN_XY = (200.0, 2700.0)
_NOWHERE_XY = (5000.0, 9500.0)
# 選定 section（動態帶）測試座標——開在所有靜態帶（最深至 y=6720）之下。
_SELECTION_BOUNDS = Bounds(x=100.0, y=7000.0, w=2400.0, h=700.0)
_SELECTION_XY = (300.0, 7200.0)

# 合法 problem_statement 文字（需求句，過 spec 23 v2.0 模板）。
_PS_TEXT = "通勤族 需要 出門時不用特別想也能帶到袋子，因為 想到時人已經在店裡了"


@dataclass
class FakeNote:
    text: str
    x: float = 200.0
    y: float = 200.0
    kind: str = "content"
    concept_group_id: str | None = None
    metadata: dict = field(default_factory=dict)
    id: str = ""
    cites: tuple[str, ...] = ()
    time_box_forced: bool = False


def _stakeholder(name: str, *, group: str | None = None) -> FakeNote:
    return FakeNote(text=name, x=_STAKEHOLDER_XY[0], y=_STAKEHOLDER_XY[1],
                    concept_group_id=group)


def _pain(text: str, *, group: str | None = None) -> FakeNote:
    return FakeNote(text=text, x=_PAIN_XY[0], y=_PAIN_XY[1], concept_group_id=group)


def _high_label(group: str) -> FakeNote:
    return FakeNote(text="高", x=_STAKEHOLDER_XY[0], y=_STAKEHOLDER_XY[1],
                    kind="label", concept_group_id=group)


def _sel_ps(note_id: str, *, cites: tuple[str, ...] = ()) -> FakeNote:
    return FakeNote(text=_PS_TEXT, x=_SELECTION_XY[0], y=_SELECTION_XY[1],
                    id=note_id, cites=cites)


def _sel_reason(note_id: str, *, cites: tuple[str, ...], forced: bool = False) -> FakeNote:
    text = "時間到了，先選這張" if forced else "選定｜符合準則：影響範圍——最多人卡住"
    return FakeNote(text=text, x=_SELECTION_XY[0] + 250, y=_SELECTION_XY[1],
                    id=note_id, cites=cites, time_box_forced=forced)


def _criterion(name: str = "影響範圍", note_id: str = "crit1") -> FakeNote:
    """2.5 準則便條（準則區座標，選定區外）——準則指名判定的比對母集。"""
    return FakeNote(text=f"準則：{name}｜衡量方式：卡住人數多寡", x=200.0, y=5800.0,
                    id=note_id)


def _hmw(note_id: str, *, cites: tuple[str, ...]) -> FakeNote:
    return FakeNote(text="我們可以怎麼讓袋子自己出現在手邊？", x=400.0, y=5000.0,
                    id=note_id, cites=cites)


def _patched_gate(notes: list[FakeNote]):
    fake_analysis = MagicMock(notes=notes)
    fake_analyzer = MagicMock()
    fake_analyzer.analyze = AsyncMock(return_value=fake_analysis)
    return patch(
        "app.canvas.analyzer.get_spatial_analyzer",
        return_value=fake_analyzer,
    )


@contextlib.contextmanager
def _patched_gate_with_section(notes: list[FakeNote], *, with_section: bool = True):
    """同 _patched_gate，並 mock 動態 section bounds（選定區成員查詢用）。"""
    bounds_map = {"sec_test": _SELECTION_BOUNDS} if with_section else {}
    with _patched_gate(notes), patch(
        "app.canvas.sections.get_section_bounds_map",
        new=AsyncMock(return_value=bounds_map),
    ):
        yield


class TestClassifyText:
    def test_matches_problem_statement(self) -> None:
        text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒，"
            "因為視力退化，因此需要不依賴文字的方式。"
        )
        assert _classify_text(text) == "problem_statement"

    def test_matches_criteria(self) -> None:
        assert _classify_text("準則：影響範圍｜衡量方式：每天有多少人遇到") == "criteria"

    def test_short_text_not_classified(self) -> None:
        # 短文字模板（stakeholder/problem_candidate）不入候選——
        # 純文字分類不可靠，以牆面＋kind 界定（spec 23 v2.0 §2.0）。
        assert _classify_text("超市收銀員") is None

    def test_empty_returns_none(self) -> None:
        assert _classify_text("") is None
        assert _classify_text("   ") is None


class TestAggregateTemplateCounts:
    def test_empty(self) -> None:
        assert _aggregate_template_counts([]) == {}

    def test_counts_problem_statements(self) -> None:
        # 五要件句（現行 problem_statement regex；需求句雙句型＝spec 23 v2.0 regex
        # 改寫，批次 C2）。
        ps = (
            "對於通勤族而言，在結帳時，他常遇到想不起袋子的情況，"
            "因為腦子還掛在工作上，因此需要更顯眼的提醒。"
        )
        notes = [FakeNote(text=ps), FakeNote(text=ps), FakeNote(text="這是雜訊")]
        counts = _aggregate_template_counts(notes)
        assert counts["problem_statement"] == 2


class TestStakeholderWallCount:
    async def test_1_1b_blocks_below_8(self) -> None:
        notes = [_stakeholder(f"角色{i}") for i in range(5)]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.1b")
        assert result.passed is False
        assert result.counts["stakeholder"] == 5
        assert result.missing["stakeholder"] == 3

    async def test_1_1b_passes_at_8(self) -> None:
        notes = [_stakeholder(f"角色{i}") for i in range(8)]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.1b")
        assert result.passed is True
        assert result.counts["stakeholder"] == 8

    async def test_labels_and_outside_notes_not_counted(self) -> None:
        notes = [_stakeholder(f"角色{i}") for i in range(8)]
        # 群標籤（kind=label）與牆外便條都不計。
        notes.append(_high_label("g1"))
        notes.append(FakeNote(text="牆外", x=_NOWHERE_XY[0], y=_NOWHERE_XY[1]))
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.1b")
        assert result.counts["stakeholder"] == 8

    async def test_name_only_notes_count(self) -> None:
        # spec 23 v2.0：便條只寫名字——短名（2 字）照算（牆面計數不走 regex）。
        notes = [_stakeholder(n) for n in
                 ("學生", "店員", "家長", "老師", "司機", "房東", "客人", "醫生")]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.1b")
        assert result.passed is True


class TestPainWallGate:
    async def test_1_2_blocks_below_6(self) -> None:
        notes = [_pain(f"具體卡住情境{i}") for i in range(4)]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.2")
        assert result.passed is False
        assert result.missing["pain_point"] == 2

    async def test_1_2_passes_at_6_without_high_groups(self) -> None:
        notes = [_pain(f"具體卡住情境{i}") for i in range(6)]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.2")
        assert result.passed is True
        assert result.reasons_zh == ()

    async def test_1_2_high_priority_group_uncovered_blocks(self) -> None:
        # 高優先群 g1 沒有任何痛點 → 結構違規（即使張數達標）。
        notes = [_pain(f"具體卡住情境{i}", group="g2") for i in range(6)]
        notes.append(_high_label("g1"))
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.2")
        assert result.passed is False
        assert result.missing == {}  # 張數沒缺，缺的是覆蓋
        assert len(result.reasons_zh) == 1
        # 大白話、不講機制名（#29）。
        assert "群" in result.reasons_zh[0]
        for banned in ("gate", "pain_point", "group_id"):
            assert banned not in result.reasons_zh[0]

    async def test_1_2_high_priority_group_covered_passes(self) -> None:
        notes = [_pain(f"具體卡住情境{i}", group="g2") for i in range(5)]
        notes.append(_pain("g1 的具體卡住情境", group="g1"))
        notes.append(_high_label("g1"))
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "1.2")
        assert result.passed is True

    def test_high_label_without_group_is_vacuous(self) -> None:
        # 「高」label 沒帶群關聯 → 無從歸屬，不計入條件（寬鬆不誤卡）。
        notes = [FakeNote(text="高", kind="label")]
        assert _high_priority_group_reasons(notes) == []

    def test_high_label_text_variants(self) -> None:
        # 「高優先」算；「高雄人」(>4字? no, 3字) — 守門靠 kind=label，
        # content 便條永不誤判。
        notes = [
            FakeNote(text="高優先", kind="label", concept_group_id="g1"),
            _pain("沒掛 g1 的痛點", group="g2"),
        ]
        assert len(_high_priority_group_reasons(notes)) == 1


class TestCheckArtifactGateGeneral:
    async def test_soft_cells_pass(self) -> None:
        # 2.6/2.7 已有硬閘（selection_pairing/hmw_pairing），不再列為軟格。
        for soft in ("1.1a", "1.1c", "1.1d", "2.3", "2.4", "2.5"):
            result = await check_artifact_gate(uuid4(), soft)
            assert result.passed is True, soft

    async def test_unknown_sub_phase_passes(self) -> None:
        result = await check_artifact_gate(uuid4(), "99.99")
        assert result.passed is True

    async def test_analyzer_failure_passes_gracefully(self) -> None:
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "app.canvas.analyzer.get_spatial_analyzer",
            return_value=fake_analyzer,
        ):
            result = await check_artifact_gate(uuid4(), "1.1b")
        assert result.passed is True  # graceful degradation


class TestProblemCandidateGroups:
    """2.1 主題群數＝痛點牆內掛痛點的相異 group_id（spec 23 v2.0 §2.3 / 25 §2.3）。"""

    async def test_blocks_below_3_groups(self) -> None:
        notes = [_pain(f"卡點{i}", group="g1") for i in range(3)]  # 只有 1 群
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "2.1")
        assert result.passed is False
        assert result.counts["problem_candidate"] == 1
        assert result.missing["problem_candidate"] == 2

    async def test_passes_at_3_groups(self) -> None:
        notes = [
            _pain("卡點a", group="g1"),
            _pain("卡點b", group="g2"),
            _pain("卡點c", group="g3"),
        ]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "2.1")
        assert result.passed is True
        assert result.counts["problem_candidate"] == 3

    async def test_ungrouped_and_labels_not_counted(self) -> None:
        notes = [
            _pain("卡點a", group="g1"),
            _pain("卡點b", group="g2"),
            _pain("沒掛群的卡點"),  # group=None → 不計
            FakeNote(text="出門前就忘了帶", x=_PAIN_XY[0], y=_PAIN_XY[1],
                     kind="label", concept_group_id="g3"),  # label 不計
        ]
        with _patched_gate(notes):
            result = await check_artifact_gate(uuid4(), "2.1")
        assert result.counts["problem_candidate"] == 2  # g1, g2


class TestProblemStatementCites:
    """2.2 problem_statement 計入需 cites≥2 筆痛點便條關聯（spec 25 v2.0 §2.3）。"""

    async def test_only_ps_with_2plus_cites_count(self) -> None:
        pains = [
            _pain("卡點1"), _pain("卡點2"), _pain("卡點3"),
        ]
        for i, p in enumerate(pains):
            p.id = f"pain{i}"
        ps_ok = FakeNote(text=_PS_TEXT, id="ps_ok", cites=("pain0", "pain1"))
        ps_one = FakeNote(text=_PS_TEXT, id="ps_one", cites=("pain0",))  # 只 1 cite
        ps_none = FakeNote(text=_PS_TEXT, id="ps_none")  # 無 cites
        with _patched_gate(pains + [ps_ok, ps_one, ps_none]):
            result = await check_artifact_gate(uuid4(), "2.2")
        assert result.counts["problem_statement"] == 1  # 只有 ps_ok
        assert result.passed is False  # 需 3

    async def test_passes_with_3_well_cited(self) -> None:
        pains = [_pain(f"卡點{i}") for i in range(2)]
        pains[0].id, pains[1].id = "pa", "pb"
        ps = [
            FakeNote(text=_PS_TEXT, id=f"ps{i}", cites=("pa", "pb"))
            for i in range(3)
        ]
        with _patched_gate(pains + ps):
            result = await check_artifact_gate(uuid4(), "2.2")
        assert result.passed is True
        assert result.counts["problem_statement"] == 3


class TestSelectionPairing:
    """2.6 收口閘 selection_pairing（spec 25 v2.0 §3.2）。

    Phase 42 補正 R1（P1-1）：理由必須**指到現存準則**（名稱比對，cites 輔助）——
    helper 簽名改 (members, notes)，notes 供準則便條母集。
    """

    def test_helper_paired_passes(self) -> None:
        cnt, reasons = _evaluate_selection_pairing(
            [_sel_ps("p1"), _sel_reason("r1", cites=("p1",))],
            [_criterion("影響範圍")],
        )
        assert cnt == 1 and not reasons

    def test_helper_forced_reason_valid(self) -> None:
        # time_box_forced 豁免準則指名要求——牆上完全沒有準則便條也算合格配對。
        cnt, reasons = _evaluate_selection_pairing(
            [_sel_ps("p1"), _sel_reason("r1", cites=("p1",), forced=True)],
            [],
        )
        assert cnt == 1 and not reasons

    def test_helper_unpaired_blocks(self) -> None:
        cnt, reasons = _evaluate_selection_pairing([_sel_ps("p1")], [])
        assert cnt == 0 and reasons

    def test_helper_over_three_blocks(self) -> None:
        members = []
        for i in range(4):
            members.append(_sel_ps(f"p{i}"))
            members.append(_sel_reason(f"r{i}", cites=(f"p{i}",)))
        cnt, reasons = _evaluate_selection_pairing(members, [_criterion("影響範圍")])
        assert cnt == 4
        assert any("三張" in r or "太多" in r for r in reasons)

    def test_fabricated_criterion_name_blocks(self) -> None:
        """編造的準則名（牆上只有「時間可行性」，理由卻寫「影響範圍」）不再過閘（P1-1）。"""
        cnt, reasons = _evaluate_selection_pairing(
            [_sel_ps("p1"), _sel_reason("r1", cites=("p1",))],
            [_criterion("時間可行性")],
        )
        assert cnt == 0
        assert any("對不起來" in r for r in reasons)

    def test_no_criteria_on_wall_blocks(self) -> None:
        """牆上根本沒有準則便條 → 指名必然落空、非 forced 理由不合格。"""
        cnt, reasons = _evaluate_selection_pairing(
            [_sel_ps("p1"), _sel_reason("r1", cites=("p1",))],
            [],
        )
        assert cnt == 0 and reasons

    def test_cites_fallback_qualifies(self) -> None:
        """名稱對不上但 cites 指向真準則便條 → 走 cites 輔助判定合格。"""
        reason = _sel_reason("r1", cites=("p1", "critX"))
        cnt, reasons = _evaluate_selection_pairing(
            [_sel_ps("p1"), reason],
            [_criterion("時間可行性", note_id="critX")],
        )
        assert cnt == 1 and not reasons

    async def test_gate_passes_with_section(self) -> None:
        notes = [_sel_ps("p1"), _sel_reason("r1", cites=("p1",)), _criterion("影響範圍")]
        with _patched_gate_with_section(notes):
            result = await check_artifact_gate(uuid4(), "2.6")
        assert result.passed is True

    async def test_gate_blocks_empty_selection(self) -> None:
        with _patched_gate_with_section([], with_section=True):
            result = await check_artifact_gate(uuid4(), "2.6")
        assert result.passed is False
        # 特殊鍵機器名不漏進 format（§4.4）。
        out = format_gate_rejection_zh(result)
        assert "selection_pairing" not in out
        assert out  # 有大白話 reasons_zh


class TestHmwPairing:
    """2.7 配對閘 hmw_pairing（spec 25 v2.0 §3.3）。"""

    def test_helper_paired_passes(self) -> None:
        members = [_sel_ps("p1")]
        notes = members + [_hmw("h1", cites=("p1",))]
        cnt, reasons = _evaluate_hmw_pairing(members, notes)
        assert cnt == 1 and not reasons

    def test_helper_unpaired_blocks(self) -> None:
        members = [_sel_ps("p1")]
        cnt, reasons = _evaluate_hmw_pairing(members, members)
        assert cnt == 0 and reasons

    async def test_gate_passes_with_section(self) -> None:
        notes = [_sel_ps("p1"), _hmw("h1", cites=("p1",))]
        with _patched_gate_with_section(notes):
            result = await check_artifact_gate(uuid4(), "2.7")
        assert result.passed is True

    async def test_gate_blocks_missing_design_question(self) -> None:
        notes = [_sel_ps("p1")]  # 選定 1 張但無設計題目
        with _patched_gate_with_section(notes):
            result = await check_artifact_gate(uuid4(), "2.7")
        assert result.passed is False
        assert "hmw_pairing" not in format_gate_rejection_zh(result)


class TestFormatGateRejection:
    """spec 25 v2.0 §6 canonical（Phase 42 補正 R2／P1-2＋G11）。

    修復前的舊斷言把違規措辭（raw 鍵名＋「推進條件未達成：」）鎖成回歸基準
    ——本 class 改鎖 §6 硬規則：中文標籤、canonical 開頭、未知鍵不漏鍵名。
    """

    def test_empty_when_no_missing(self) -> None:
        out = format_gate_rejection_zh(ArtifactGateResult(passed=True))
        assert out == ""

    def test_uses_zh_labels_and_canonical_header(self) -> None:
        result = ArtifactGateResult(
            passed=False,
            missing={"stakeholder": 2, "pain_point": 3},
            requirements={"stakeholder": 8, "pain_point": 6},
            counts={"stakeholder": 6, "pain_point": 3},
        )
        out = format_gate_rejection_zh(result)
        # §6 硬規則 1/3：無機器鍵名、canonical 開頭。
        assert "stakeholder" not in out
        assert "pain_point" not in out
        assert "推進條件未達成" not in out
        assert out.startswith("還差一點才能往下")
        assert "利害關係人便條還不夠：目前 6 張，至少要 8 張。" in out
        assert "痛點便條還不夠：目前 3 張，至少要 6 張。" in out

    def test_unknown_key_fallback_no_leak(self) -> None:
        # §6 硬規則 4：未知鍵不印鍵名，合併一句 fallback。
        result = ArtifactGateResult(
            passed=False,
            missing={"mystery_key_x": 1},
            requirements={"mystery_key_x": 2},
            counts={"mystery_key_x": 1},
        )
        out = format_gate_rejection_zh(result)
        assert "mystery_key_x" not in out
        assert "這一關需要的便條還不夠。" in out

    def test_includes_structural_reasons(self) -> None:
        result = ArtifactGateResult(
            passed=False,
            reasons_zh=("排在優先的那幾群裡，還有 1 群連一條具體的卡住情況都沒有。",),
        )
        out = format_gate_rejection_zh(result)
        assert "優先" in out

    def test_missing_formatter_shares_material(self) -> None:
        # G11：format_gate_missing_zh 與 rejection 版共用單一素材源。
        from app.progression.advance_router import format_gate_missing_zh

        result = ArtifactGateResult(
            passed=False,
            missing={"criteria": 2},
            requirements={"criteria": 3},
            counts={"criteria": 1},
        )
        out = format_gate_missing_zh(result)
        assert "criteria" not in out
        assert "準則便條還不夠：目前 1 張，至少要 3 張" in out


class TestEventContract:
    def test_rejected_event_removed(self) -> None:
        """ArtifactGateRejectedEvent 已廢除（spec 25 v2.1 §4）——死事件不得復活。"""
        import app.events.types as event_types

        assert not hasattr(event_types, "ArtifactGateRejectedEvent")


class TestModuleContract:
    def test_special_keys_c2(self) -> None:
        # spec 25 v2.0 §3：persona_complete 移除（§3.1）；C2 加回 selection_pairing/hmw_pairing。
        assert "persona_complete" not in SPECIAL_KEYS
        assert SPECIAL_KEYS == frozenset({"selection_pairing", "hmw_pairing"})
