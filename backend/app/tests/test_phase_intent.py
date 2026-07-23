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
        # Phase 29 (spec/04-06 §4.10): 3.x / 4.x removed.
        ("1.1", "divergent"),
        ("1.2", "divergent"),
        # Phase 42 C1：舊 1.3 桶移除（未知 → transitional）；2.1 痛點歸類＝收斂、
        # 2.2 桶（問題定義與深掘）混合屬性＝transitional。
        ("2.1", "convergent"),
        ("2.3", "convergent"),
        # transitional / unknown
        ("1.3", "transitional"),
        ("2.2", "transitional"),
        ("3.1", "transitional"),  # removed; falls through to default
        ("3.2", "transitional"),
        ("3.3", "transitional"),
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
        # Phase 29 (spec/04-06 §4.10): 3.x / 4.x sub-phases removed.
        ("1.1a", "divergent"),
        ("1.1b", "divergent"),
        # Phase 42 C1（spec 16 v2.0 §6.5.2 與 27 v3.1 §3.1 已對齊一致）：
        # 1.x 全程 divergent（含 1.1c/1.1d——發現側「只打開不收攏」，輕整理/排序是
        # 便條手法不是宏觀收斂；模擬 §43「別偷偷收斂」）。
        ("1.1c", "divergent"),
        ("1.1d", "divergent"),
        ("1.2", "divergent"),
        ("0.0a", "divergent"),     # 暖場衝量＝發散（護欄強化衝量+去重，不衝突）
        ("2.3", "transitional"),   # threaded 深掘：收斂護欄「優先搬動」與禁搬動互斥
        ("2.4", "transitional"),
        ("2.1", "convergent"),
        ("3.2", "transitional"),    # removed; falls through to default
        ("3.3", "transitional"),
        ("4.3", "transitional"),
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
