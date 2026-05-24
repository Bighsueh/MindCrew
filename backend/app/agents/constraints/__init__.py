"""Phase 27: Constraint Suggester.

Open Brief 原則下，使用者只填任務名稱與描述，限制條件是「建議方向」。
此模組讓 AI 根據 title + description 動態列出可能的限制（預算量級、可能族群、
可能場域、其他約束），由前端以 chip 採納（不可預勾、不可覆寫使用者輸入）。

見 ``specs/17-dynamic-persona-system.md`` §3.0.2 與 §11 Open Brief 原則。
"""
from app.agents.constraints.models import ConstraintSuggestions
from app.agents.constraints.suggester import (
    ConstraintSuggestionError,
    ConstraintSuggester,
)

__all__ = [
    "ConstraintSuggestions",
    "ConstraintSuggester",
    "ConstraintSuggestionError",
]
