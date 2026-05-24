"""ConstraintSuggester — Phase 27 LLM-driven 限制條件建議。

接 ``POST /api/projects/draft/suggest-constraints`` 端點（見 ``specs/06`` §2.3）。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.agents.constraints.models import ConstraintSuggestions
from app.agents.constraints.prompts import (
    CONSTRAINT_SUGGESTION_SYSTEM_PROMPT,
    build_constraint_suggestion_user_prompt,
)
from app.chinese.converter import chinese_converter
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json

logger = logging.getLogger(__name__)


class ConstraintSuggestionError(RuntimeError):
    """Raised when the LLM cannot produce parseable constraint suggestions."""


class ConstraintSuggester:
    """LLM-driven open-brief constraint hints."""

    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm = llm_service or LLMProviderFactory.get_service()

    async def suggest(
        self,
        *,
        title: str,
        description: str | None,
        owning_user_id: UUID,
    ) -> ConstraintSuggestions:
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")

        messages = [
            {"role": "system", "content": CONSTRAINT_SUGGESTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_constraint_suggestion_user_prompt(
                    title=title, description=description
                ),
            },
        ]
        try:
            response = await self._llm.chat_completion(
                messages=messages,
                temperature=0.6,
                max_tokens=800,
                caller="constraint_suggestion",
                owning_user_id=owning_user_id,
            )
        except Exception as exc:
            logger.warning("Constraint suggestion LLM call failed: %s", exc)
            raise ConstraintSuggestionError(str(exc)) from exc

        parsed = parse_llm_json(response.content) or {}
        if not isinstance(parsed, dict):
            raise ConstraintSuggestionError(
                "LLM did not return a JSON object"
            )

        converted: dict[str, list[str]] = {}
        for key in (
            "budget_hints",
            "audience_hints",
            "venue_hints",
            "other_hints",
        ):
            raw_list = parsed.get(key) or []
            if not isinstance(raw_list, list):
                converted[key] = []
                continue
            cleaned: list[str] = []
            for item in raw_list:
                text = chinese_converter.convert(str(item).strip())
                if text:
                    cleaned.append(text)
            converted[key] = cleaned

        suggestions = ConstraintSuggestions.from_dict(converted)
        if suggestions.is_empty():
            raise ConstraintSuggestionError(
                "Constraint suggester returned an empty result"
            )
        return suggestions


__all__ = ["ConstraintSuggester", "ConstraintSuggestionError"]
