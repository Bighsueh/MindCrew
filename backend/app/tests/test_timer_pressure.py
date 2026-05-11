"""Unit tests for app.timer.pressure — 五階壓力等級 + 行為導向。"""

from __future__ import annotations

import pytest

from app.timer.pressure import (
    compute_pressure_level,
    get_pressure_label_zh,
    pressure_directive,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "used_pct,expected",
    [
        (0.0, "calm"),
        (49.99, "calm"),
        (50.0, "halfway"),
        (66.99, "halfway"),
        (67.0, "two_thirds"),
        (74.99, "two_thirds"),
        (75.0, "tight"),
        (89.99, "tight"),
        (90.0, "critical"),
        (100.0, "critical"),
        (150.0, "critical"),  # overtime 仍歸 critical
    ],
)
def test_compute_pressure_level_boundaries(used_pct: float, expected: str) -> None:
    assert compute_pressure_level(used_pct) == expected


@pytest.mark.unit
def test_pressure_level_handles_none() -> None:
    # 防呆：None / 異常值不該炸
    assert compute_pressure_level(None) == "calm"  # type: ignore[arg-type]


@pytest.mark.unit
def test_pressure_label_all_levels() -> None:
    for level in ("calm", "halfway", "two_thirds", "tight", "critical"):
        label = get_pressure_label_zh(level)  # type: ignore[arg-type]
        assert isinstance(label, str) and label, f"{level} should have non-empty label"


@pytest.mark.unit
def test_pressure_directive_calm_returns_empty() -> None:
    # calm 階段不該主動干擾
    for intent in ("divergent", "convergent", "transitional"):
        assert pressure_directive("calm", intent) == ""  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    "level,intent",
    [
        ("halfway", "divergent"),
        ("halfway", "convergent"),
        ("halfway", "transitional"),
        ("two_thirds", "divergent"),
        ("two_thirds", "convergent"),
        ("two_thirds", "transitional"),
        ("tight", "divergent"),
        ("tight", "convergent"),
        ("tight", "transitional"),
        ("critical", "divergent"),
        ("critical", "convergent"),
        ("critical", "transitional"),
    ],
)
def test_pressure_directive_non_calm_has_content(level: str, intent: str) -> None:
    text = pressure_directive(level, intent)  # type: ignore[arg-type]
    assert text and isinstance(text, str), f"({level}, {intent}) should have directive"
    # tight / critical 應帶有「收斂 / 推進 / 決策」類關鍵語
    if level in ("tight", "critical"):
        assert any(
            kw in text
            for kw in (
                "收斂", "決", "投票", "整理", "停止", "挑出",
                "取捨", "推進", "做出", "共識", "強制", "時間到",
            )
        )
