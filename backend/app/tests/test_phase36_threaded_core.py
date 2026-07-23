"""Phase 36 / Spec 27 (v2.0) — 接話式核心測試（精簡版，無概念演進線）。

涵蓋：
- threaded_reveal comm_mode 註冊 + per-sub-phase 對齊
- must_be_concept content gate（regex tier）
- 去重 _is_duplicate_concept / _normalize_concept（§4.4）
- organic 落點 + concept_group 同對象聚一起（§4.2 / §5）

全為純函式，不需 DB / Redis。
"""
from __future__ import annotations

from app.canvas.content_gate import GATE_MODULES, check_text, describe_module
from app.canvas.layout_engine import (
    _ORGANIC_JITTER_PX,
    _organic_jitter,
    get_layout_engine,
)
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote
from app.canvas.tools_manipulation import (
    _charset_jaccard,
    _group_anchor_in_bounds,
    _is_duplicate_concept,
    _is_threaded_sub_phase,
    _normalize_concept,
)
from app.canvas.zones import Bounds
from app.stages.sub_phases import COMM_MODES, get_sub_phase


def _note(nid: str, text: str, x: float = 0, y: float = 0, group: str | None = None) -> SpatialNote:
    return SpatialNote(
        id=nid, text=text, x=x, y=y, width=200, height=150,
        color="yellow", author_type="ai", created_at="", concept_group_id=group,
    )


class TestThreadedCommMode:
    def test_threaded_reveal_registered(self) -> None:
        assert "threaded_reveal" in COMM_MODES

    def test_threaded_sub_phases(self) -> None:
        # Phase 42 C1（spec 27 v3.0 §3.1）：接話式＝1.2（按利害關係人群）/2.3/2.4。
        for sub_id in ("1.2", "2.3", "2.4"):
            assert "threaded_reveal" in get_sub_phase(sub_id).comm_modes
        assert "threaded_reveal" not in get_sub_phase("1.1a").comm_modes

    def test_1_2_soft_feature_jump_not_interpretation(self) -> None:
        # Phase 42 C1：no_interpretation 全系統移除；1.2 掛「跳功能」軟擋。
        sp = get_sub_phase("1.2")
        assert "no_interpretation" not in sp.gate_modules
        assert "no_feature_jump" in sp.gate_modules

    def test_is_threaded_sub_phase_helper(self) -> None:
        assert _is_threaded_sub_phase("1.1a") is False  # 人本暖場：不分群、非 threaded
        assert _is_threaded_sub_phase("1.2") is True    # 痛點按利害關係人群
        assert _is_threaded_sub_phase("1.1b") is False  # 獨立式（各寫各的）
        assert _is_threaded_sub_phase(None) is False
        assert _is_threaded_sub_phase("nonexistent") is False


class TestMustBeConcept:
    def test_module_registered(self) -> None:
        assert "must_be_concept" in GATE_MODULES
        assert "概念" in describe_module("must_be_concept")

    def test_pure_question_blocked(self) -> None:
        assert check_text("跟哪一家比？", ("must_be_concept",)).passed is False
        assert check_text("為什麼這麼貴？", ("must_be_concept",)).passed is False

    def test_reply_dialogue_blocked(self) -> None:
        assert check_text("他說：隔壁便宜兩成", ("must_be_concept",)).passed is False
        assert check_text("我問：你平常怎麼買", ("must_be_concept",)).passed is False

    def test_filler_blocked(self) -> None:
        for filler in ("嗯嗯", "對啊", "好喔～", "是這樣"):
            assert check_text(filler, ("must_be_concept",)).passed is False, filler

    def test_real_concept_passes(self) -> None:
        for concept in (
            "在意 CP 值，不是單純嫌貴",
            "願意為品質多付一點",
            "補貨動線被購物車擋住",
        ):
            assert check_text(concept, ("must_be_concept",)).passed is True, concept


class TestDedup:
    def test_normalize_strips_punctuation(self) -> None:
        assert _normalize_concept("在意CP值，不是！") == _normalize_concept("在意CP值 不是")

    def test_exact_duplicate_blocked_cross_group(self) -> None:
        notes = [_note("a", "在大型超市找不到調味料", group="顧客")]
        # 完全相同（正規化後）即使指定別群也擋
        assert _is_duplicate_concept("在大型超市找不到調味料！", "店員", notes) == "a"

    def test_same_group_paraphrase_blocked(self) -> None:
        notes = [_note("a", "在意CP值不是單純嫌貴", group="顧客")]
        assert _is_duplicate_concept("其實是在意CP值不是單純嫌貴啦", "顧客", notes) == "a"

    def test_distinct_concept_allowed(self) -> None:
        notes = [_note("a", "在意CP值", group="顧客")]
        assert _is_duplicate_concept("動線被購物車擋住", "顧客", notes) is None

    def test_paraphrase_across_group_not_blocked(self) -> None:
        # 換句話說只在「同群」內擋；跨群的相近（非完全相同）不誤殺
        notes = [_note("a", "在意CP值不是單純嫌貴", group="顧客")]
        assert _is_duplicate_concept("其實在意CP值不是單純嫌貴喔", "店員", notes) is None

    def test_empty_text_allowed(self) -> None:
        assert _is_duplicate_concept("", "顧客", []) is None

    # --- P4: CJK 字集 Jaccard 語意重述偵測（換句話說 / 詞序重排）---

    def test_charset_jaccard_high_for_reordering(self) -> None:
        # 詞序重排 → 字集幾乎相同 → 高 Jaccard
        assert _charset_jaccard("結帳排隊時間太長", "排隊結帳時間很長") >= 0.7
        # 不同概念 → 低 Jaccard
        assert _charset_jaccard("價格太貴", "動線被擋住") < 0.3

    def test_same_group_reordering_blocked(self) -> None:
        notes = [_note("a", "結帳排隊等很久", group="顧客")]
        assert _is_duplicate_concept("排隊結帳等很久", "顧客", notes) == "a"

    def test_same_group_high_reuse_blocked(self) -> None:
        notes = [_note("a", "顧客覺得價格太貴", group="顧客")]
        assert _is_duplicate_concept("顧客覺得價格很貴", "顧客", notes) == "a"

    def test_distinct_same_group_not_overblocked(self) -> None:
        # 同對象、不同概念（價格 vs 服務）不可被 Jaccard 誤併
        notes = [_note("a", "顧客覺得價格太貴", group="顧客")]
        assert _is_duplicate_concept("顧客覺得服務太慢", "顧客", notes) is None

    def test_jaccard_scoped_to_same_group(self) -> None:
        # Jaccard 重述只在同群內擋；跨群（非完全相同）不誤殺
        notes = [_note("a", "結帳排隊等很久", group="顧客")]
        assert _is_duplicate_concept("排隊結帳等很久", "店員", notes) is None


class TestOrganicAndGroupPlacement:
    def test_organic_jitter_deterministic_and_bounded(self) -> None:
        jx, jy = _organic_jitter(7)
        assert _organic_jitter(7) == (jx, jy)  # 可重現
        assert abs(jx) <= _ORGANIC_JITTER_PX and abs(jy) <= _ORGANIC_JITTER_PX

    def test_auto_grid_is_not_rigid(self) -> None:
        # organic 落點不應落在精確網格交點（帶 jitter）
        eng = get_layout_engine()
        x, y = eng.resolve_position(to="region:unknownxyz", notes=[])
        # jitter 讓座標不為整齊格點：至少其一帶小數/偏移
        assert (x, y) != (eng._grid.start_x, eng._grid.start_y)

    def test_concept_group_places_beside_members(self) -> None:
        members = [_note("a", "價格太貴", x=100, y=100, group="顧客")]
        eng = get_layout_engine()
        x, y = eng.resolve_position(to="concept_group:顧客", notes=members)
        # 病根 C-1：新概念緊鄰同群錨點落下、不與成員重疊（緊湊欄，不抹開）。
        assert not eng._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, members)
        # 落點貼近群錨點（同欄往下 或 右側鄰欄），不會飛遠。
        assert abs(x - 100) <= NOTE_WIDTH + 30
        assert 100 <= y <= 100 + (NOTE_HEIGHT + 30) * 6

    def test_concept_group_does_not_smear_right(self) -> None:
        # 病根 C-1：連續加入同群多張，群應緊湊（不隨每次新增無限右移）。
        eng = get_layout_engine()
        notes = [_note("a", "概念0", x=100, y=100, group="顧客")]
        for i in range(5):
            x, y = eng.resolve_position(to="concept_group:顧客", notes=notes)
            assert not eng._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes)
            notes.append(_note(f"n{i}", f"概念{i}", x=x, y=y, group="顧客"))
        # 6 張群的水平跨度應遠小於「每張都往右開欄」的最壞情況（≤2 欄寬）。
        xs = [n.x for n in notes]
        assert max(xs) - min(xs) <= (NOTE_WIDTH + 30) * 2

    def test_concept_group_empty_falls_back(self) -> None:
        eng = get_layout_engine()
        # 該群尚無成員 → 退回 organic（不報錯）
        x, y = eng.resolve_position(to="concept_group:不存在", notes=[])
        assert isinstance(x, float) and isinstance(y, float)


class TestGroupAnchorInBounds:
    """病根 C-3：snap 進 zone 時優先從「同群且在 zone 內成員」的錨點起算（保住群聚）。"""

    _B = Bounds(x=0, y=0, w=1000, h=1000)

    def test_returns_anchor_of_in_zone_members(self) -> None:
        notes = [
            _note("a", "概念1", x=300, y=400, group="顧客"),
            _note("b", "概念2", x=200, y=500, group="顧客"),
            _note("c", "別群", x=100, y=100, group="店員"),
        ]
        assert _group_anchor_in_bounds("顧客", notes, self._B) == (200, 400)

    def test_none_when_no_group(self) -> None:
        notes = [_note("a", "概念1", x=300, y=400, group="顧客")]
        assert _group_anchor_in_bounds(None, notes, self._B) is None

    def test_none_when_members_outside_bounds(self) -> None:
        notes = [_note("a", "概念1", x=5000, y=5000, group="顧客")]
        assert _group_anchor_in_bounds("顧客", notes, self._B) is None

    def test_label_members_ignored(self) -> None:
        # 標籤便條不算群錨來源 → 用 SpatialNote 直接建（本檔 _note 不帶 kind）
        from app.canvas.spatial import SpatialNote
        lbl = SpatialNote(
            id="lbl", text="顧客標籤", x=300, y=400, width=200, height=150,
            color="blue", author_type="ai", created_at="",
            kind="label", concept_group_id="顧客",
        )
        assert _group_anchor_in_bounds("顧客", [lbl], self._B) is None
