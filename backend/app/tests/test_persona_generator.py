"""Persona generator unit tests (mocked LLM)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.agents.personas.generator import (
    PersonaGenerationError,
    PersonaGenerator,
)


@dataclass
class _StubResponse:
    content: str


class _StubLLM:
    """Records calls and returns canned responses in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> _StubResponse:
        self.calls.append(
            {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        if not self._responses:
            raise RuntimeError("No more stub responses")
        return _StubResponse(content=self._responses.pop(0))


_STAGE1_REPLY = json.dumps(
    {
        "categories": [
            {
                "category": "獨居長者",
                "rationale": "主要受影響者",
                "lens_bias": "empathy",
            },
            {
                "category": "社區里長",
                "rationale": "在地組織者",
                "lens_bias": "structure",
            },
            {
                "category": "智慧家電工程師",
                "rationale": "技術視角",
                "lens_bias": "feasibility",
            },
            {
                "category": "策展人",
                "rationale": "跨界類比",
                "lens_bias": "creativity",
            },
        ]
    },
    ensure_ascii=False,
)

_STAGE2_REPLY = json.dumps(
    {
        "personas": [
            {
                "name": "阿英",
                "role": "獨居 78 歲長者",
                "expertise": "社區人脈、日常照護需求、生活節奏",
                "personality_axis": "supportive",
                "personality_desc": "用故事帶大家進入她的真實生活",
                "backstory": "退休護理師，丈夫過世後一個人住",
                "lens_affinities": {
                    "empathy": 0.95,
                    "structure": 0.3,
                    "creativity": 0.4,
                    "feasibility": 0.5,
                },
            },
            {
                "name": "林志強",
                "role": "里長辦公室幹事",
                "expertise": "社區資源盤點、政策對接、活動組織",
                "personality_axis": "balanced",
                "personality_desc": "把人脈和規則綁在一起",
                "backstory": "做了 8 年里長幹事，熟悉每戶情況",
                "lens_affinities": {
                    "empathy": 0.5,
                    "structure": 0.85,
                    "creativity": 0.4,
                    "feasibility": 0.6,
                },
            },
            {
                "name": "Wei Chen",
                "role": "資深 IoT 韌體工程師",
                "expertise": "感測器整合、低功耗藍牙、家用網路",
                "personality_axis": "contrarian",
                "personality_desc": "會直接戳穿不可行的想法",
                "backstory": "曾在新創失敗兩次後轉去做老人科技",
                "lens_affinities": {
                    "empathy": 0.3,
                    "structure": 0.5,
                    "creativity": 0.3,
                    "feasibility": 0.95,
                },
            },
            {
                "name": "Mia Hsu",
                "role": "獨立策展人",
                "expertise": "故事設計、互動體驗、文化轉譯",
                "personality_axis": "balanced",
                "personality_desc": "用比喻幫團隊看到新視角",
                "backstory": "從美術館跨界做社區型策展",
                "lens_affinities": {
                    "empathy": 0.6,
                    "structure": 0.4,
                    "creativity": 0.95,
                    "feasibility": 0.3,
                },
            },
        ]
    },
    ensure_ascii=False,
)


@pytest.mark.asyncio
async def test_generator_produces_four_personas_from_two_stage_calls() -> None:
    llm = _StubLLM([_STAGE1_REPLY, _STAGE2_REPLY])
    generator = PersonaGenerator(llm_service=llm)
    personas = await generator.generate(
        title="老人科技導入",
        description="協助獨居長者使用智慧家電",
        constraints="預算極低且使用者多為 70 歲以上",
        num_personas=4,
    )
    assert len(personas) == 4
    assert llm.calls and len(llm.calls) == 2
    # System prompts for the two stages differ
    stage1_sys = llm.calls[0]["messages"][0]["content"]
    stage2_sys = llm.calls[1]["messages"][0]["content"]
    assert "利害關係人" in stage1_sys
    assert "人物設計師" in stage2_sys
    # Persona names round-tripped
    names = {p.name for p in personas}
    assert "阿英" in names
    assert "林志強" in names
    # Dominant lens of "阿英" is empathy
    ah_ying = next(p for p in personas if p.name == "阿英")
    assert ah_ying.dominant_lens().value == "empathy"


@pytest.mark.asyncio
async def test_generator_raises_on_no_personas() -> None:
    bad_stage2 = json.dumps({"personas": []})
    llm = _StubLLM([_STAGE1_REPLY, bad_stage2])
    generator = PersonaGenerator(llm_service=llm)
    with pytest.raises(PersonaGenerationError):
        await generator.generate(
            title="x",
            description=None,
            constraints=None,
            num_personas=4,
        )


@pytest.mark.asyncio
async def test_generator_requires_title() -> None:
    llm = _StubLLM([])
    generator = PersonaGenerator(llm_service=llm)
    with pytest.raises(ValueError):
        await generator.generate(
            title="  ",
            description=None,
            constraints=None,
            num_personas=4,
        )


@pytest.mark.asyncio
async def test_generator_recovers_from_empty_stage1() -> None:
    """If stakeholder mapping fails, stage 2 should still be attempted."""
    llm = _StubLLM(["{ not valid json }", _STAGE2_REPLY])
    generator = PersonaGenerator(llm_service=llm)
    personas = await generator.generate(
        title="x", description=None, constraints=None, num_personas=4
    )
    assert len(personas) == 4


# ---------------------------------------------------------------------------
# Streaming pipeline (spec §17.3.1.2)
# ---------------------------------------------------------------------------


class _StubStreamLLM(_StubLLM):
    """Extends _StubLLM with a streaming method that yields the reply in slices."""

    def __init__(self, sync_replies: list[str], stream_chunks: list[str]) -> None:
        super().__init__(sync_replies)
        self._chunks = list(stream_chunks)

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
        )
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_generate_stream_emits_stage_and_persona_events() -> None:
    # Slice the stage-2 JSON so the extractor must reassemble two objects.
    chunks = [
        _STAGE2_REPLY[:120],
        _STAGE2_REPLY[120:240],
        _STAGE2_REPLY[240:380],
        _STAGE2_REPLY[380:],
    ]
    llm = _StubStreamLLM([_STAGE1_REPLY], chunks)
    generator = PersonaGenerator(llm_service=llm)

    events = [
        ev
        async for ev in generator.generate_stream(
            title="x",
            description=None,
            constraints=None,
            num_personas=4,
        )
    ]
    types = [ev["type"] for ev in events]
    assert types[0] == "stage" and events[0]["status"] == "start"
    assert any(ev["type"] == "persona" for ev in events)
    assert types[-1] == "done"

    persona_events = [ev for ev in events if ev["type"] == "persona"]
    assert len(persona_events) == 4
    # Indices are zero-based and contiguous.
    assert [ev["index"] for ev in persona_events] == [0, 1, 2, 3]
    # The first persona payload should have a name from the canned stage-2 reply.
    assert persona_events[0]["persona"]["name"] == "阿英"


@pytest.mark.asyncio
async def test_generate_stream_errors_on_empty_title() -> None:
    llm = _StubStreamLLM([], [])
    generator = PersonaGenerator(llm_service=llm)
    events = [
        ev
        async for ev in generator.generate_stream(
            title="  ",
            description=None,
            constraints=None,
            num_personas=4,
        )
    ]
    assert events == [{"type": "error", "detail": "title is required"}]
