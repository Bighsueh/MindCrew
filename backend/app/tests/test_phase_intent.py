"""Unit tests for app.stages.phase_intent — 發散/收斂單一真實來源。"""

from __future__ import annotations

import pytest

from app.stages.phase_intent import (
    get_phase_intent,
    get_phase_intent_by_sub_phase,
    get_phase_intent_label_zh,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mp,expected",
    [
        ("1.1", "divergent"),
        ("1.2", "divergent"),
        ("3.1", "divergent"),
        ("1.3", "convergent"),
        ("2.3", "convergent"),
        ("3.2", "convergent"),
        ("3.3", "convergent"),
        # transitional / unknown
        ("2.1", "transitional"),
        ("2.2", "transitional"),
        ("4.1", "transitional"),
        ("4.2", "transitional"),
        ("4.3", "transitional"),
        ("99.9", "transitional"),
        (None, "transitional"),
        ("", "transitional"),
    ],
)
def test_get_phase_intent_by_micro_phase(mp: str | None, expected: str) -> None:
    assert get_phase_intent(mp) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sp,expected",
    [
        ("1.1a", "divergent"),
        ("1.1b", "divergent"),
        ("1.1c", "convergent"),  # sub-phase 收斂雖然 micro_phase 1.1 是發散
        ("1.1d", "convergent"),
        ("4.3", "convergent"),
        ("3.2", "divergent"),    # sub-phase 3.2 視為發散（與 micro 3.2 收斂不同）
        ("3.3", "divergent"),    # 同上
        ("99.9x", "transitional"),
        (None, "transitional"),
        ("", "transitional"),
    ],
)
def test_get_phase_intent_by_sub_phase(sp: str | None, expected: str) -> None:
    assert get_phase_intent_by_sub_phase(sp) == expected


@pytest.mark.unit
def test_intent_label_zh() -> None:
    assert get_phase_intent_label_zh("divergent") == "發散"
    assert get_phase_intent_label_zh("convergent") == "收斂"
    assert get_phase_intent_label_zh("transitional") == "過渡"
