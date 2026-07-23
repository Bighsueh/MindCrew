"""Phase 27 fix — stream persona generation falls back to sync on empty/fail.

`PersonaGenerator.generate_stream` is wired through `LLMProviderFactory
.chat_completion_stream`, which has NO mid-stream tier fallback. When the
primary streaming provider returns empty/garbage, the stream yields zero
personas. Without a safety net, the SSE consumer sees a generic error.

This module verifies the new fallback: when streaming produces 0 personas,
the generator retries via `chat_completion` (which DOES have tier fallback)
and emits regular `persona` events to the caller, so the user-facing UX is
"progress pauses briefly, then persona cards appear" instead of an error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest

from app.agents.personas.generator import PersonaGenerator
from app.agents.personas.models import StakeholderSuggestion


_TEST_UID = uuid4()


@dataclass
class _StubResponse:
    content: str


class _StreamEmptyThenSyncOK:
    """Streaming yields nothing; sync chat_completion returns a valid response.

    Used to exercise the fallback path. Records both streaming and sync calls
    so tests can assert which one(s) were used.
    """

    def __init__(self, sync_reply: str) -> None:
        self._sync_reply = sync_reply
        self.stream_calls = 0
        self.sync_calls: list[dict[str, Any]] = []

    async def chat_completion_stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        self.stream_calls += 1
        # Simulate primary provider returning an empty body.
        if False:
            yield ""  # pragma: no cover - need this to satisfy AsyncIterator type
        return

    async def chat_completion(
        self, messages: list[dict], **kwargs: Any
    ) -> _StubResponse:
        self.sync_calls.append({"messages": messages, **kwargs})
        return _StubResponse(content=self._sync_reply)


class _StreamRaisesSyncOK(_StreamEmptyThenSyncOK):
    """Streaming raises an exception; sync still works (tier-fallback path)."""

    async def chat_completion_stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        self.stream_calls += 1
        raise RuntimeError("primary stream exploded")
        if False:  # pragma: no cover
            yield ""


class _BothFail:
    """Both stream and sync fail — must surface a friendly error event."""

    def __init__(self) -> None:
        self.stream_calls = 0
        self.sync_calls = 0

    async def chat_completion_stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        self.stream_calls += 1
        return
        if False:  # pragma: no cover
            yield ""

    async def chat_completion(
        self, messages: list[dict], **kwargs: Any
    ) -> _StubResponse:
        self.sync_calls += 1
        raise RuntimeError("all providers down")


_VALID_PERSONA_JSON = json.dumps(
    {
        "personas": [
            {
                "name": "阿英",
                "role": "獨居長者",
                "expertise": "社區人脈",
                "personality_axis": "supportive",
                "personality_desc": "細膩、傾聽優先",
                "backstory": "退休護理師",
                "lens_affinities": {
                    "empathy": 0.9,
                    "structure": 0.3,
                    "creativity": 0.4,
                    "feasibility": 0.5,
                },
            },
            {
                "name": "Wei",
                "role": "工程師",
                "expertise": "IoT",
                "personality_axis": "contrarian",
                "personality_desc": "敢挑戰前提",
                "backstory": "新創失敗轉行",
                "lens_affinities": {
                    "empathy": 0.3,
                    "structure": 0.5,
                    "creativity": 0.4,
                    "feasibility": 0.9,
                },
            },
        ]
    },
    ensure_ascii=False,
)


def _picked_stakeholders() -> list[StakeholderSuggestion]:
    return [
        StakeholderSuggestion(id="s1", name="阿英", role="78 歲獨居長者", relevance="主要使用者"),
        StakeholderSuggestion(id="s2", name="Wei", role="IoT 工程師", relevance="技術視角"),
    ]


async def _collect(generator: PersonaGenerator, **kwargs: Any) -> list[dict]:
    events: list[dict] = []
    async for event in generator.generate_stream(**kwargs):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_stream_empty_triggers_sync_fallback_and_emits_personas() -> None:
    """主要場景:streaming primary 拉空 → 走非串流 fallback → personas 出來。"""
    llm = _StreamEmptyThenSyncOK(_VALID_PERSONA_JSON)
    generator = PersonaGenerator(llm_service=llm)

    events = await _collect(
        generator,
        title="老人科技",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=_TEST_UID,
        stakeholders=_picked_stakeholders(),
    )

    # 必須真的試過 streaming(就算是空的)
    assert llm.stream_calls == 1, "Should have attempted streaming before falling back"
    # 必須 fall back 到 sync 拿到 personas
    assert len(llm.sync_calls) == 1, "Should fall back to non-stream chat_completion exactly once"
    # 必須產出 N 個 persona event + 1 個 done(無 error)
    persona_events = [e for e in events if e.get("type") == "persona"]
    done_events = [e for e in events if e.get("type") == "done"]
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(persona_events) == 2
    assert len(done_events) == 1
    assert done_events[0]["count"] == 2
    assert error_events == []

    # Persona 內容對得起 LLM 回應(name 沒搞混)
    names = [e["persona"]["name"] for e in persona_events]
    assert "阿英" in names and "Wei" in names


@pytest.mark.asyncio
async def test_stream_exception_triggers_sync_fallback() -> None:
    """streaming 直接 raise(連 0 個都沒 yield)→ 仍走 fallback,不漏網。"""
    llm = _StreamRaisesSyncOK(_VALID_PERSONA_JSON)
    generator = PersonaGenerator(llm_service=llm)

    events = await _collect(
        generator,
        title="老人科技",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=_TEST_UID,
        stakeholders=_picked_stakeholders(),
    )

    assert llm.stream_calls == 1
    assert len(llm.sync_calls) == 1
    assert any(e.get("type") == "done" for e in events)
    assert not any(e.get("type") == "error" for e in events)


@pytest.mark.asyncio
async def test_stream_works_first_time_skips_sync_fallback() -> None:
    """Happy path 不要每次都跑 fallback — streaming 成功時 sync 不該被呼叫。"""

    class _StreamWorksOK:
        """單一物件就拼接出完整 JSON,模擬正常 streaming。"""

        def __init__(self) -> None:
            self.stream_calls = 0
            self.sync_calls = 0

        async def chat_completion_stream(
            self, messages: list[dict], **kwargs: Any
        ) -> AsyncIterator[str]:
            self.stream_calls += 1
            # 一次給完整 JSON,extractor 應能解析 2 個物件
            yield _VALID_PERSONA_JSON

        async def chat_completion(
            self, messages: list[dict], **kwargs: Any
        ) -> _StubResponse:  # pragma: no cover - should not be called
            self.sync_calls += 1
            return _StubResponse(content=_VALID_PERSONA_JSON)

    llm = _StreamWorksOK()
    generator = PersonaGenerator(llm_service=llm)

    events = await _collect(
        generator,
        title="老人科技",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=_TEST_UID,
        stakeholders=_picked_stakeholders(),
    )

    assert llm.stream_calls == 1
    assert llm.sync_calls == 0, "Sync fallback must NOT run when streaming succeeds"
    persona_events = [e for e in events if e.get("type") == "persona"]
    assert len(persona_events) == 2


@pytest.mark.asyncio
async def test_both_paths_fail_emits_friendly_error_event() -> None:
    """streaming + sync 都 fail → 必須 yield error event,不可拋 raw exception 給 caller。"""
    llm = _BothFail()
    generator = PersonaGenerator(llm_service=llm)

    events = await _collect(
        generator,
        title="老人科技",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=_TEST_UID,
        stakeholders=_picked_stakeholders(),
    )

    assert llm.stream_calls == 1
    assert llm.sync_calls == 1
    errors = [e for e in events if e.get("type") == "error"]
    assert errors, "Must emit an error event when both paths fail"
    assert "AI 人設生成失敗" in errors[-1]["detail"]
    # 不應該有任何 done event
    assert not any(e.get("type") == "done" for e in events)


@pytest.mark.asyncio
async def test_stream_empty_no_stakeholders_falls_back_to_instantiation() -> None:
    """v1.x 路徑(沒帶 stakeholders)也要有 fallback — 走 _run_persona_instantiation。"""

    stage1_categories = json.dumps(
        {
            "categories": [
                {"category": "獨居長者", "rationale": "主要受影響者", "lens_bias": "empathy"},
                {"category": "工程師", "rationale": "技術視角", "lens_bias": "feasibility"},
            ]
        },
        ensure_ascii=False,
    )

    class _StubV1:
        """Stage 1 sync 成功、Stage 2 stream 空、Stage 2 sync 成功。

        chat_completion 會被呼叫兩次:第一次是 Stage 1 (mapping),第二次是 fallback。
        """

        def __init__(self) -> None:
            self.stream_calls = 0
            self.sync_calls: list[str] = []  # caller 紀錄

        async def chat_completion_stream(
            self, messages: list[dict], **kwargs: Any
        ) -> AsyncIterator[str]:
            self.stream_calls += 1
            return
            if False:  # pragma: no cover
                yield ""

        async def chat_completion(
            self, messages: list[dict], **kwargs: Any
        ) -> _StubResponse:
            caller = str(kwargs.get("caller") or "")
            self.sync_calls.append(caller)
            if caller == "persona_stakeholders":
                return _StubResponse(content=stage1_categories)
            return _StubResponse(content=_VALID_PERSONA_JSON)

    llm = _StubV1()
    generator = PersonaGenerator(llm_service=llm)

    events = await _collect(
        generator,
        title="老人科技",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=_TEST_UID,
        stakeholders=None,  # v1.x — no user-picked stakeholders
    )

    # Stage 1 sync 拿 categories;stream 嘗試;fallback 走 _run_persona_instantiation。
    assert llm.stream_calls == 1
    assert "persona_stakeholders" in llm.sync_calls
    assert "persona_generation" in llm.sync_calls
    persona_events = [e for e in events if e.get("type") == "persona"]
    assert len(persona_events) == 2
    assert not any(e.get("type") == "error" for e in events)
