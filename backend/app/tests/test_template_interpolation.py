"""Tests for crew name template interpolation (P1-2).

Covers all placeholder patterns: @{crew_N}, @{crew_name}, @{crew_a/b}, @{成員名稱}
"""

from __future__ import annotations

import pytest

from app.agents.prompts.interpolation import interpolate_crew_names


class TestInterpolateCrewNames:
    """Test template pattern replacement."""

    def test_indexed_pattern(self) -> None:
        """@{crew_1} → actual display name."""
        text = "@{crew_1}，先請你分享一次你在大型賣場購物時的體驗。"
        result = interpolate_crew_names(text)
        assert "AI 同理心專家" in result
        assert "@{crew_1}" not in result

    def test_indexed_name_pattern(self) -> None:
        """@{crew_1_name} → actual display name."""
        text = "@{crew_1_name}，你從使用者的角度觀察到什麼？"
        result = interpolate_crew_names(text)
        assert "AI 同理心專家" in result
        assert "@{crew_1_name}" not in result

    def test_all_crew_indices(self) -> None:
        """All crew indices resolve correctly."""
        text = "@{crew_1} @{crew_2} @{crew_3} @{crew_4}"
        result = interpolate_crew_names(text)
        assert "AI 同理心專家" in result
        assert "AI 結構化專家" in result
        assert "AI 創意專家" in result
        assert "AI 可行性專家" in result

    def test_generic_crew_name(self) -> None:
        """@{crew_name} → first crew display name."""
        text = "@{crew_name}，你說的反向思考啟發了我"
        result = interpolate_crew_names(text)
        assert "@{crew_name}" not in result
        assert "AI 同理心專家" in result

    def test_letter_pattern(self) -> None:
        """@{crew_a} and @{crew_b} → crew_1 and crew_2 names."""
        text = "@{crew_a} 和 @{crew_b} 的觀點看起來有張力"
        result = interpolate_crew_names(text)
        assert "@{crew_a}" not in result
        assert "@{crew_b}" not in result

    def test_chinese_pattern(self) -> None:
        """@{成員名稱} → display name."""
        text = "用 @{成員名稱} 開頭直接回應"
        result = interpolate_crew_names(text)
        assert "@{成員名稱}" not in result

    def test_no_match_passthrough(self) -> None:
        """Text without patterns passes through unchanged."""
        text = "這是一段普通的對話文字"
        result = interpolate_crew_names(text)
        assert result == text

    def test_empty_string(self) -> None:
        assert interpolate_crew_names("") == ""

    def test_custom_seats(self) -> None:
        """Custom seat display names override defaults."""
        seats = [
            {"role": "crew_1", "display_name": "小明"},
            {"role": "crew_2", "display_name": "小華"},
        ]
        text = "@{crew_1} 和 @{crew_2}"
        result = interpolate_crew_names(text, seats)
        assert "小明" in result
        assert "小華" in result

    def test_multiple_patterns_same_text(self) -> None:
        """Multiple different patterns in the same text."""
        text = "@{crew_1_name}，剛剛 {crew_name} 提到 X，@{crew_a} 和 @{crew_b} 有張力"
        result = interpolate_crew_names(text)
        assert "@{" not in result
        assert "{crew" not in result
