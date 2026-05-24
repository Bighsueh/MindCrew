"""Phase 27: Constraint Suggester unit tests (mocked LLM)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.agents.constraints import (
    ConstraintSuggester,
    ConstraintSuggestionError,
    ConstraintSuggestions,
)


@dataclass
class _StubResponse:
    content: str


class _StubLLM:
    """Lenient stub accepting any kwargs the real factory passes."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> _StubResponse:
        self.calls.append({"messages": messages, **kwargs})
        if not self._responses:
            raise RuntimeError("No more stub responses")
        return _StubResponse(content=self._responses.pop(0))


_VALID_REPLY = json.dumps(
    {
        "budget_hints": ["微型 < NT$1k", "小型 NT$1k-10k"],
        "audience_hints": ["重度推車使用者", "行動不便的長者"],
        "venue_hints": ["大型量販店", "社區型超市"],
        "other_hints": ["3 個月內 MVP", "無需電源"],
    },
    ensure_ascii=False,
)


@pytest.mark.asyncio
async def test_suggester_returns_four_categories() -> None:
    suggester = ConstraintSuggester(llm_service=_StubLLM([_VALID_REPLY]))
    result = await suggester.suggest(
        title="重新設計大賣場購物車",
        description="協助使用者快速結帳",
        owning_user_id=uuid4(),
    )
    assert isinstance(result, ConstraintSuggestions)
    assert "微型 < NT$1k" in result.budget_hints
    assert "重度推車使用者" in result.audience_hints
    assert "大型量販店" in result.venue_hints
    assert "3 個月內 MVP" in result.other_hints


@pytest.mark.asyncio
async def test_suggester_rejects_empty_response() -> None:
    empty = json.dumps(
        {
            "budget_hints": [],
            "audience_hints": [],
            "venue_hints": [],
            "other_hints": [],
        }
    )
    suggester = ConstraintSuggester(llm_service=_StubLLM([empty]))
    with pytest.raises(ConstraintSuggestionError):
        await suggester.suggest(
            title="x",
            description=None,
            owning_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_suggester_requires_title() -> None:
    suggester = ConstraintSuggester(llm_service=_StubLLM([]))
    with pytest.raises(ValueError):
        await suggester.suggest(
            title="  ",
            description="anything",
            owning_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_suggester_filters_nonlist_entries() -> None:
    """Defensive: LLM may emit non-list values for a key."""
    bad = json.dumps(
        {
            "budget_hints": "not a list",  # should be silently dropped
            "audience_hints": ["valid item"],
            "venue_hints": None,
            "other_hints": [],
        }
    )
    suggester = ConstraintSuggester(llm_service=_StubLLM([bad]))
    result = await suggester.suggest(
        title="x",
        description=None,
        owning_user_id=uuid4(),
    )
    assert result.budget_hints == ()
    assert result.audience_hints == ("valid item",)
    assert result.venue_hints == ()


@pytest.mark.asyncio
async def test_suggester_propagates_llm_failure_as_error() -> None:
    class _Crashing:
        async def chat_completion(self, *_a, **_kw):
            raise TimeoutError("boom")

    suggester = ConstraintSuggester(llm_service=_Crashing())
    with pytest.raises(ConstraintSuggestionError):
        await suggester.suggest(
            title="x", description=None, owning_user_id=uuid4()
        )
