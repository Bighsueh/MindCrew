"""Phase 31 (spec/23 §3): TemplateSuggester.

Asks the LLM to draft a sticky-note content matching a given template_id's
regex. On validation failure retries once with a stronger reminder.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.agents.template_suggest.prompts import (
    TEMPLATE_SUGGEST_SYSTEM_PROMPT,
    build_user_prompt,
)
from app.canvas.text_templates import TEMPLATES, validate_template
from app.chinese.converter import chinese_converter
from app.llm.factory import LLMProviderFactory

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1
_MAX_TOKENS = 400


class TemplateSuggestError(RuntimeError):
    """Raised when the suggester cannot produce a valid draft."""


class TemplateSuggester:
    """LLM-driven sticky-note content drafter for first-diamond templates."""

    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm = llm_service or LLMProviderFactory.get_service()

    async def suggest(
        self,
        *,
        template_id: str,
        context: dict[str, Any],
        owning_user_id: UUID,
        project_id: UUID | None = None,
    ) -> str:
        """Return suggested content for the given template.

        Raises TemplateSuggestError if template is unknown or LLM fails after retry.
        """
        if template_id not in TEMPLATES:
            raise TemplateSuggestError(
                f"unknown template_id: {template_id!r}"
            )

        user_prompt = build_user_prompt(template_id, context)

        for attempt in range(_MAX_RETRIES + 1):
            messages: list[dict[str, str]] = [
                {"role": "system", "content": TEMPLATE_SUGGEST_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            if attempt > 0:
                # On retry, add a corrective hint
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "⚠️ 上一次回覆不符合模板格式。請嚴格按照上述句型/欄位重寫，"
                            "不要省略任何分隔符號（｜:：）或關鍵字（例：背景：/ 因為 / from:）。"
                        ),
                    }
                )

            try:
                response = await self._llm.chat_completion(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=_MAX_TOKENS,
                    caller="template_suggest",
                    owning_user_id=owning_user_id,
                    project_id=project_id,
                )
            except Exception as exc:
                logger.warning(
                    "Template suggest LLM call failed (template=%s, attempt=%d): %s",
                    template_id,
                    attempt,
                    exc,
                )
                raise TemplateSuggestError(str(exc)) from exc

            content = chinese_converter.convert(
                (response.content or "").strip().strip("`").strip()
            )
            if not content:
                continue

            validation = validate_template(content, template_id)
            if validation.passed:
                return content

            logger.info(
                "Template suggest validation failed (template=%s, attempt=%d, reason=%s)",
                template_id,
                attempt,
                validation.reason_zh,
            )

        raise TemplateSuggestError(
            f"LLM failed to produce a valid {template_id} after {_MAX_RETRIES + 1} attempts"
        )
