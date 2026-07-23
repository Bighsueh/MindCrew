"""ConstraintSuggestions data structure.

See `` §3.0.2.

Note on immutability: fields are ``tuple[str, ...]`` (not list) so that
``frozen=True`` provides full deep immutability — preventing the trap
where a caller could ``result.budget_hints.append(...)`` and silently
mutate shared state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConstraintSuggestions:
    """AI 建議的限制條件分類。前端以可採納 chip 呈現，不可預勾。"""

    budget_hints: tuple[str, ...] = field(default_factory=tuple)
    audience_hints: tuple[str, ...] = field(default_factory=tuple)
    venue_hints: tuple[str, ...] = field(default_factory=tuple)
    other_hints: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "budget_hints": list(self.budget_hints),
            "audience_hints": list(self.audience_hints),
            "venue_hints": list(self.venue_hints),
            "other_hints": list(self.other_hints),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConstraintSuggestions":
        if not isinstance(data, dict):
            return cls()

        def _tuple(key: str) -> tuple[str, ...]:
            raw = data.get(key) or []
            if not isinstance(raw, list):
                return ()
            return tuple(str(x).strip() for x in raw if str(x).strip())

        return cls(
            budget_hints=_tuple("budget_hints"),
            audience_hints=_tuple("audience_hints"),
            venue_hints=_tuple("venue_hints"),
            other_hints=_tuple("other_hints"),
        )

    def is_empty(self) -> bool:
        return not any(
            (
                self.budget_hints,
                self.audience_hints,
                self.venue_hints,
                self.other_hints,
            )
        )


__all__ = ["ConstraintSuggestions"]
