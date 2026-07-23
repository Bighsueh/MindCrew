"""2026-05-25 hot-fix — suggest_stakeholders retries on LLM hiccups.

UI 觀察:CreateProjectDialog 進到 StakeholdersStep 時打 /api/projects/draft/
suggest-stakeholders 偶爾 502，因為 LLM 回 empty body / 截斷 JSON / 不足
spec 規定的 6 位。

修正:在 generator 層加 application-level retry loop（最多 3 次），對單一
LLM hiccup 不直接 502。若所有重試都不足、但至少拿到一些 stakeholder，
回 best-effort list 讓使用者仍可作業（前端有「再請 AI 建議幾位」按鈕可
手動補）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.agents.personas.generator import (
    PersonaGenerationError,
    PersonaGenerator,
)


_TEST_UID = uuid4()


@dataclass
class _StubResponse:
    content: str


def _build_suggestions(n: int) -> str:
    """Helper: build a JSON string with N synthetic suggestions."""
    items = [
        {
            "name": f"姓名{i}",
            "role": f"角色 {i}",
            "relevance": f"關聯說明 {i}",
        }
        for i in range(n)
    ]
    return json.dumps({"suggestions": items}, ensure_ascii=False)


class _SequencedLLM:
    """Returns canned responses in order. Records call count."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses: list[str | Exception] = list(responses)
        self.calls = 0

    async def chat_completion(
        self, messages: list[dict], **kwargs: Any
    ) -> _StubResponse:
        self.calls += 1
        if not self._responses:
            raise RuntimeError("Stub exhausted; test under-specified")
        next_resp = self._responses.pop(0)
        if isinstance(next_resp, Exception):
            raise next_resp
        return _StubResponse(content=next_resp)


# ---------------------------------------------------------------------------
# Happy path:第 1 次就成功 → 不重試
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_attempt_succeeds_no_retry() -> None:
    llm = _SequencedLLM([_build_suggestions(7)])
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="長者科技導入",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    assert len(result) == 7
    assert llm.calls == 1, "Happy path should not trigger retries"


# ---------------------------------------------------------------------------
# Empty body:第 1 次空 → 第 2 次成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_response_triggers_retry_then_succeeds() -> None:
    llm = _SequencedLLM(["", _build_suggestions(6)])
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="x",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    assert len(result) == 6
    assert llm.calls == 2, "Should retry once after empty response"


# ---------------------------------------------------------------------------
# Malformed JSON:第 1 次截斷 → 第 2 次成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_truncated_json_triggers_retry_then_succeeds() -> None:
    truncated = '{"suggestions": [{"name": "張伯', # cut off mid-string
    llm = _SequencedLLM([truncated[0], _build_suggestions(7)])
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="x",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    assert len(result) == 7
    assert llm.calls == 2


# ---------------------------------------------------------------------------
# Insufficient count:第 1 次 1 個 → 第 2 次 6 個
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insufficient_items_triggers_retry_then_succeeds() -> None:
    llm = _SequencedLLM([_build_suggestions(1), _build_suggestions(6)])
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="x",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    assert len(result) == 6
    assert llm.calls == 2


# ---------------------------------------------------------------------------
# Exception from provider:retry 也要吃下去
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_exception_triggers_retry_then_succeeds() -> None:
    llm = _SequencedLLM(
        [RuntimeError("all providers down"), _build_suggestions(6)]
    )
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="x",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    assert len(result) == 6
    assert llm.calls == 2


# ---------------------------------------------------------------------------
# 全部失敗:3 次都空 → 503 (raise PersonaGenerationError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_attempts_empty_raises_error() -> None:
    llm = _SequencedLLM(["", "", ""])
    gen = PersonaGenerator(llm_service=llm)
    with pytest.raises(PersonaGenerationError) as excinfo:
        await gen.suggest_stakeholders(
            title="x",
            description=None,
            constraints=None,
            owning_user_id=_TEST_UID,
        )
    assert "after 3 attempts" in str(excinfo.value)
    assert llm.calls == 3


# ---------------------------------------------------------------------------
# 部分成功:3 次都不足但有 items → best-effort 回傳,不 raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_attempts_insufficient_returns_best_effort() -> None:
    """若三次都拿到 1-3 個 stakeholder,寧可給使用者半成品也比 502 好。

    前端 StakeholdersStep 有「再請 AI 建議幾位」按鈕可以手動補。
    """
    llm = _SequencedLLM(
        [_build_suggestions(2), _build_suggestions(3), _build_suggestions(2)]
    )
    gen = PersonaGenerator(llm_service=llm)
    result = await gen.suggest_stakeholders(
        title="x",
        description=None,
        constraints=None,
        owning_user_id=_TEST_UID,
    )
    # 最後一次有 2 個 stakeholder — best-effort 回傳那批
    assert len(result) == 2
    assert llm.calls == 3
    # 確認 results 是有效的 StakeholderSuggestion
    assert all(s.name and s.role for s in result)


# ---------------------------------------------------------------------------
# 不接受空 title — 仍是 ValueError 而非 retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_title_short_circuits_no_llm_call() -> None:
    llm = _SequencedLLM([])
    gen = PersonaGenerator(llm_service=llm)
    with pytest.raises(ValueError, match="title is required"):
        await gen.suggest_stakeholders(
            title="   ",
            description=None,
            constraints=None,
            owning_user_id=_TEST_UID,
        )
    assert llm.calls == 0
