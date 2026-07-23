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


# ---------------------------------------------------------------------------
# Phase 42 B2（守則 6，#15）：真人顯示名插值
# ---------------------------------------------------------------------------

from app.agents.prompts.interpolation import (  # noqa: E402
    find_human_display_name,
    interpolate_human_name,
)

_HUMAN_SEATS = [
    {"role": "supervisor", "type": "ai", "display_name": "AI 引導者"},
    {"role": "human_creator", "type": "human", "user_name": "小明"},
]


class TestHumanNameInterpolation:
    def test_find_human_display_name(self) -> None:
        assert find_human_display_name(_HUMAN_SEATS) == "小明"
        assert find_human_display_name([{"role": "crew_1", "type": "ai"}]) == ""
        assert find_human_display_name(None) == ""

    def test_placeholders_replaced(self) -> None:
        text = "例：「@{name}，你怎麼看？」並發含「@{顯示名}」的訊息"
        out = interpolate_human_name(text, _HUMAN_SEATS)
        assert "@小明" in out
        assert "@{name}" not in out and "@{顯示名}" not in out

    def test_taught_placeholder_kept(self) -> None:
        # 守則 6 的教學佔位符「@{對方顯示名}」刻意不插值（指涉對象不限真人）。
        text = "必須直接寫出「@{對方顯示名}」"
        assert interpolate_human_name(text, _HUMAN_SEATS) == text

    def test_system_prompt_keeps_bare_seat_id(self) -> None:
        # system prompt 模式（預設）保留 invited_speaker 機器路由教學。
        text = 'set_directive invited_speaker="human_creator"'
        assert interpolate_human_name(text, _HUMAN_SEATS) == text

    def test_outbound_rewrites_bare_seat_id(self) -> None:
        out = interpolate_human_name(
            "@human_creator 換你了", _HUMAN_SEATS, include_bare_seat_id=True
        )
        assert out == "@小明 換你了"

    def test_outbound_rewrites_cjk_adjacent_seat_id(self) -> None:
        # 中文輸出常無空格——\b 在 CJK 相鄰會失效，須用 ASCII lookaround。
        out = interpolate_human_name(
            "請human_creator回應，@human_creator你覺得呢", _HUMAN_SEATS,
            include_bare_seat_id=True,
        )
        assert "human_creator" not in out
        assert out.count("@小明") == 2

    def test_no_human_placeholder_degrades_to_dajia(self) -> None:
        # Phase 42 補正 R2（稽核 §4.2）：全 AI 房佔位符降級「大家」，
        # 字面「@{顯示名}」不得外漏（修復前原文返回＝直接進聊天記錄）。
        out = interpolate_human_name(
            "@{name} 你先講，@{顯示名}也說說", [{"role": "crew_1", "type": "ai"}]
        )
        assert "@{" not in out
        assert out == "大家 你先講，大家也說說"

    def test_no_human_outbound_seat_id_degrades(self) -> None:
        out = interpolate_human_name(
            "@human_creator 換你了", [{"role": "crew_1", "type": "ai"}],
            include_bare_seat_id=True,
        )
        assert "human_creator" not in out
        assert "大家" in out

    def test_no_human_plain_text_unchanged(self) -> None:
        # 全 AI 房、無佔位符 → 原文不動。
        text = "我們先把牆上的便條看一輪"
        assert interpolate_human_name(text, [{"role": "crew_1", "type": "ai"}]) == text

    def test_backslash_display_name_safe(self) -> None:
        # display name 是使用者輸入——含反斜線不可觸發 re.sub 模板跳脫。
        seats = [{"role": "human_creator", "type": "human", "user_name": "J\\g<0>x\\"}]
        out = interpolate_human_name("@{name} 請說", seats, include_bare_seat_id=True)
        assert out == "@J\\g<0>x\\ 請說"
