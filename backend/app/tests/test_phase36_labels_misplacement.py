"""Phase 36 / Spec 27 (v2.0) — 標籤便條 + 明顯錯置偵測測試。

涵蓋：
- detect_misplaced_notes（§6/§7）保守偵測：被別群包圍才標、<2 群不標、label 不算、cap
- note_posting_rules prompt 片段存在且為 v2.0（無概念演進線 / derived_from_id 措辭）

全為純函式，不需 DB / Redis。
"""
from __future__ import annotations

from app.agents.prompts import note_posting_rules as npr
from app.canvas.misplacement_detector import detect_misplaced_notes
from app.canvas.spatial import SpatialNote


def _note(
    nid: str, x: float, y: float, group: str | None, kind: str = "content"
) -> SpatialNote:
    return SpatialNote(
        id=nid, text=f"note-{nid}", x=x, y=y, width=200, height=150,
        color="yellow", author_type="ai", created_at="",
        kind=kind, concept_group_id=group,
    )


def _two_groups_with_misplaced() -> list[SpatialNote]:
    # 顧客群聚在原點附近 + 一張顧客便條 m 明顯跑到店員群裡
    kehu = [
        _note("a", 0, 0, "顧客"),
        _note("b", 80, 0, "顧客"),
        _note("c", 0, 80, "顧客"),
        _note("d", 80, 80, "顧客"),
        _note("m", 2030, 2030, "顧客"),  # 錯置：被店員包圍
    ]
    dianyuan = [
        _note("e", 2000, 2000, "店員"),
        _note("f", 2100, 2000, "店員"),
        _note("g", 2000, 2100, "店員"),
        _note("h", 2100, 2100, "店員"),
    ]
    return kehu + dianyuan


class TestMisplacementDetector:
    def test_flags_surrounded_note(self) -> None:
        flagged = detect_misplaced_notes(_two_groups_with_misplaced())
        ids = {f["note_id"] for f in flagged}
        assert "m" in ids
        m = next(f for f in flagged if f["note_id"] == "m")
        assert m["current_group"] == "顧客"
        assert m["near_group"] == "店員"

    def test_well_placed_not_flagged(self) -> None:
        notes = [
            _note("a", 0, 0, "顧客"), _note("b", 80, 0, "顧客"), _note("c", 0, 80, "顧客"),
            _note("e", 2000, 2000, "店員"), _note("f", 2100, 2000, "店員"),
            _note("g", 2000, 2100, "店員"),
        ]
        assert detect_misplaced_notes(notes) == []

    def test_single_group_returns_empty(self) -> None:
        notes = [_note("a", 0, 0, "顧客"), _note("b", 2000, 2000, "顧客")]
        assert detect_misplaced_notes(notes) == []

    def test_label_notes_ignored(self) -> None:
        # 標籤便條（kind=label）不參與錯置判定
        notes = _two_groups_with_misplaced()
        notes.append(_note("lbl", 9000, 9000, "顧客", kind="label"))
        flagged = detect_misplaced_notes(notes)
        assert all(f["note_id"] != "lbl" for f in flagged)

    def test_notes_without_group_ignored(self) -> None:
        notes = [_note("a", 0, 0, None), _note("b", 2000, 2000, None)]
        assert detect_misplaced_notes(notes) == []

    def test_max_flags_cap(self) -> None:
        flagged = detect_misplaced_notes(_two_groups_with_misplaced(), max_flags=1)
        assert len(flagged) <= 1


class TestNotePostingRulesPrompt:
    def test_constants_present(self) -> None:
        # Phase 42 C1：WARMUP_CONCEPT_EXTRACTION_RULE 隨已廢 0.1/0.2 注入路徑移除
        # （0.0a 暖場由 warmup_game.py 完整承載）。
        assert npr.SUPERVISOR_LABEL_AND_MISPLACEMENT_RULE
        assert npr.SUPERVISOR_MOVE_AND_SWITCH_RULE
        assert not hasattr(npr, "WARMUP_CONCEPT_EXTRACTION_RULE")

    def test_label_rule_mentions_label_kind(self) -> None:
        assert "label" in npr.SUPERVISOR_LABEL_AND_MISPLACEMENT_RULE

    def test_v2_no_evolution_line_wording(self) -> None:
        # v2.0：rule 內文不得再提 derived_from_id / 概念演進線（已移除連線）
        for text in (
            npr.SUPERVISOR_LABEL_AND_MISPLACEMENT_RULE,
            npr.SUPERVISOR_MOVE_AND_SWITCH_RULE,
        ):
            assert "derived_from_id" not in text
            assert "演進線" not in text
