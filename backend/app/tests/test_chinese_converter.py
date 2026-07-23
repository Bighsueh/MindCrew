"""Tests for ChineseConverter（含 Phase 42 B2 保護片語機制）。"""

from __future__ import annotations

import pytest

from app.chinese.converter import chinese_converter


@pytest.mark.unit
class TestProtectedPhrases:
    def test_canonical_label_not_mangled(self) -> None:
        # B2 live 抓到：s2twp TWPhrases 把「打開」改成「開啟」，
        # 毀掉 canonical 標題便條固定文案（spec 04-03 §3.2）。
        text = "發現階段｜把問題打開、先不做決定"
        assert chinese_converter.convert(text) == text

    def test_colloquial_phrase_not_mangled(self) -> None:
        text = "量沒到沒關係，腦袋有打開比較重要"
        assert chinese_converter.convert(text) == text

    def test_legit_kaiqi_untouched(self) -> None:
        # 正當的「開啟」用法不受保護機制影響。
        assert chinese_converter.convert("開啟檔案") == "開啟檔案"

    def test_no_sentinel_leak(self) -> None:
        out = chinese_converter.convert("打開之後再打開一次")
        assert "" not in out and "" not in out
        assert out == "打開之後再打開一次"


@pytest.mark.unit
class TestBaseline:
    def test_simplified_to_taiwan(self) -> None:
        assert chinese_converter.convert("用户的数据") == "使用者的資料"

    def test_empty(self) -> None:
        assert chinese_converter.convert("") == ""
