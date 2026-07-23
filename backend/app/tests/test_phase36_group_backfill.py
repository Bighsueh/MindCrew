"""Phase 36 / Spec 27 — 病根 B：內容便條 group_id 確定性兜底測試。

LLM 在接話式常漏帶 group_id → 散落不分群。assign_group_id 不依賴 LLM，
依與既有便條的 CJK 字集相似度把缺群便條歸到最相似的既有主題群；不夠相似則
回傳 None（寧缺勿濫）。全為純函式，不需 DB / Redis。
"""
from __future__ import annotations

from app.canvas.group_assignment import assign_group_id
from app.canvas.spatial import SpatialNote


def _note(nid: str, text: str, group: str | None, kind: str = "content") -> SpatialNote:
    return SpatialNote(
        id=nid, text=text, x=0, y=0, width=200, height=150,
        color="yellow", author_type="ai", created_at="",
        kind=kind, concept_group_id=group,
    )


class TestAssignGroupId:
    def test_backfills_most_similar_group(self) -> None:
        notes = [
            _note("a", "顧客覺得價格太貴", "顧客"),
            _note("b", "店員補貨動線被擋住", "店員"),
        ]
        # 與「顧客覺得價格太貴」字集高度重疊 → 歸「顧客」
        assert assign_group_id("顧客覺得價格很貴", notes) == "顧客"

    def test_picks_higher_similarity_among_groups(self) -> None:
        notes = [
            _note("a", "結帳排隊等很久", "顧客"),
            _note("b", "補貨動線被購物車擋住", "店員"),
        ]
        assert assign_group_id("排隊結帳等很久", notes) == "顧客"

    def test_returns_none_when_nothing_similar(self) -> None:
        notes = [_note("a", "顧客覺得價格太貴", "顧客")]
        # 完全不同概念 → 不夠相似 → None（開新群 / 留給週期整理）
        assert assign_group_id("無障礙設施不足", notes) is None

    def test_ignores_label_notes(self) -> None:
        notes = [_note("lbl", "顧客覺得價格太貴", "顧客", kind="label")]
        # 標籤便條不參與兜底比對
        assert assign_group_id("顧客覺得價格很貴", notes) is None

    def test_ignores_notes_without_group(self) -> None:
        notes = [_note("a", "顧客覺得價格太貴", None)]
        assert assign_group_id("顧客覺得價格很貴", notes) is None

    def test_empty_text_returns_none(self) -> None:
        notes = [_note("a", "顧客覺得價格太貴", "顧客")]
        assert assign_group_id("", notes) is None

    def test_no_notes_returns_none(self) -> None:
        assert assign_group_id("顧客覺得價格很貴", []) is None
