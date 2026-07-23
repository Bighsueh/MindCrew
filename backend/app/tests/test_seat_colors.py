"""每個角色一個固定專屬色：``color_for_role`` / ``seed_seat_colors`` 的決定性與唯一性。

純函式測試（不需 DB）：驗證角色 → 色為全站固定、跨呼叫一致、6 角色兩兩相異，
且不覆寫已鎖色的席位。
"""
from __future__ import annotations

from app.db.models.seat import (
    SEAT_ROLE_HUMAN_CREATOR,
    SEAT_ROLE_SUPERVISOR,
    Seat,
)
from app.seats.colors import (
    ROLE_COLOR_MAP,
    color_for_role,
    seed_seat_colors,
)


_ALL_ROLES = [
    SEAT_ROLE_SUPERVISOR,
    SEAT_ROLE_HUMAN_CREATOR,
    "crew_1",
    "crew_2",
    "crew_3",
    "crew_4",
]


def _seat(role: str, color: str | None = None) -> Seat:
    return Seat(seat_role=role, sticky_color=color)


def test_color_for_role_matches_map() -> None:
    assert color_for_role(SEAT_ROLE_SUPERVISOR) == "red"  # 陶土＝組長識別
    assert color_for_role(SEAT_ROLE_HUMAN_CREATOR) == "blue"
    assert color_for_role("crew_1") == "yellow"
    assert color_for_role("crew_2") == "green"
    assert color_for_role("crew_3") == "violet"
    assert color_for_role("crew_4") == "orange"


def test_color_for_role_unknown_returns_stable_fallback() -> None:
    # 未知角色不丟例外，回傳決定性 fallback。
    assert color_for_role("crew_99") == color_for_role("crew_99")
    assert color_for_role("crew_99") not in {"red", "blue", "yellow", "green", "violet", "orange"}


def test_seed_assigns_canonical_color_per_role() -> None:
    seats = [_seat(role) for role in _ALL_ROLES]
    seed_seat_colors(seats)
    assigned = {s.seat_role: s.sticky_color for s in seats}
    assert assigned == {role: ROLE_COLOR_MAP[role] for role in _ALL_ROLES}


def test_seed_colors_all_distinct() -> None:
    seats = [_seat(role) for role in _ALL_ROLES]
    seed_seat_colors(seats)
    colors = [s.sticky_color for s in seats]
    assert len(colors) == len(set(colors))  # 6 角色兩兩相異


def test_seed_is_deterministic_across_projects() -> None:
    seats_a = [_seat(role) for role in _ALL_ROLES]
    seats_b = [_seat(role) for role in _ALL_ROLES]
    seed_seat_colors(seats_a)
    seed_seat_colors(seats_b)
    assert [s.sticky_color for s in seats_a] == [s.sticky_color for s in seats_b]


def test_seed_does_not_overwrite_locked_color() -> None:
    seat = _seat("crew_1", color="orange")  # 已鎖色（非 canonical）
    seed_seat_colors([seat])
    assert seat.sticky_color == "orange"
