"""Phase 27: PersonaGenerator.suggest_stakeholders unit tests."""
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
from app.agents.personas.models import StakeholderSuggestion


@dataclass
class _StubResponse:
    content: str


class _StubLLM:
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


def _seven_stakeholders_json() -> str:
    return json.dumps(
        {
            "suggestions": [
                {"name": "林阿嬤", "role": "獨居山區 78 歲農婦", "relevance": "直接使用者"},
                {"name": "陳組長", "role": "連鎖賣場儲位規劃 12 年", "relevance": "提供者視角"},
                {"name": "黃議員", "role": "市議會交通建設委員", "relevance": "政策決定者"},
                {"name": "Mia 老師", "role": "通用設計研究教授", "relevance": "外部觀察者"},
                {"name": "阿宏", "role": "機場行李推車租賃業者", "relevance": "跨界類比"},
                {"name": "周媽媽", "role": "推娃娃車的職業婦女", "relevance": "另一族群"},
                {"name": "李大哥", "role": "輪椅使用者", "relevance": "邊緣需求"},
            ]
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_suggest_stakeholders_returns_concrete_people() -> None:
    llm = _StubLLM([_seven_stakeholders_json()])
    gen = PersonaGenerator(llm_service=llm)
    results = await gen.suggest_stakeholders(
        title="重新設計大賣場購物車",
        description=None,
        constraints=None,
        owning_user_id=uuid4(),
    )
    assert 6 <= len(results) <= 10
    assert all(isinstance(s, StakeholderSuggestion) for s in results)
    names = {s.name for s in results}
    assert "林阿嬤" in names
    # Each has a uuid id assigned by the generator (LLM doesn't return ids).
    assert all(len(s.id) > 0 for s in results)


@pytest.mark.asyncio
async def test_suggest_stakeholders_dedupes_by_name_role() -> None:
    payload = {
        "suggestions": [
            {"name": "A", "role": "R1", "relevance": "x"},
            {"name": "A", "role": "R1", "relevance": "y"},  # dupe
            {"name": "B", "role": "R2", "relevance": "z"},
            {"name": "C", "role": "R3", "relevance": "z"},
            {"name": "D", "role": "R4", "relevance": "z"},
            {"name": "E", "role": "R5", "relevance": "z"},
            {"name": "F", "role": "R6", "relevance": "z"},
        ]
    }
    llm = _StubLLM([json.dumps(payload, ensure_ascii=False)])
    gen = PersonaGenerator(llm_service=llm)
    results = await gen.suggest_stakeholders(
        title="x", description=None, constraints=None, owning_user_id=uuid4()
    )
    names = [s.name for s in results]
    assert names.count("A") == 1
    assert len(results) == 6


@pytest.mark.asyncio
async def test_suggest_stakeholders_raises_on_too_few() -> None:
    payload = {
        "suggestions": [
            {"name": "A", "role": "R1", "relevance": "x"},
            {"name": "B", "role": "R2", "relevance": "y"},
        ]
    }
    llm = _StubLLM([json.dumps(payload, ensure_ascii=False)])
    gen = PersonaGenerator(llm_service=llm)
    with pytest.raises(PersonaGenerationError):
        await gen.suggest_stakeholders(
            title="x",
            description=None,
            constraints=None,
            owning_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_generate_with_picked_stakeholders_skips_stage1() -> None:
    """Phase 27：當 caller 帶 stakeholders 時，generator 必須跳過 mapping。"""
    # Only stage 2 response should be consumed.
    stage2 = json.dumps(
        {
            "personas": [
                {
                    "name": "林阿嬤",
                    "role": "獨居山區 78 歲農婦",
                    "expertise": "務農經驗、地形熟悉",
                    "personality_axis": "supportive",
                    "personality_desc": "溫和、節省、念舊",
                    "backstory": "獨居山區十年",
                    "lens_affinities": {
                        "empathy": 0.9,
                        "structure": 0.3,
                        "creativity": 0.2,
                        "feasibility": 0.4,
                    },
                },
                {
                    "name": "陳組長",
                    "role": "連鎖賣場儲位規劃",
                    "expertise": "通路動線、客流分析",
                    "personality_axis": "balanced",
                    "personality_desc": "務實、數字導向",
                    "backstory": "12 年資深",
                    "lens_affinities": {
                        "empathy": 0.4,
                        "structure": 0.8,
                        "creativity": 0.3,
                        "feasibility": 0.7,
                    },
                },
            ]
        },
        ensure_ascii=False,
    )
    llm = _StubLLM([stage2])
    gen = PersonaGenerator(llm_service=llm)
    picked = [
        StakeholderSuggestion(
            id="id1",
            name="林阿嬤",
            role="獨居山區 78 歲農婦",
            relevance="直接使用者",
        ),
        StakeholderSuggestion(
            id="id2",
            name="陳組長",
            role="連鎖賣場儲位規劃",
            relevance="提供者",
        ),
    ]
    personas = await gen.generate(
        title="重新設計購物車",
        description=None,
        constraints=None,
        num_personas=2,
        owning_user_id=uuid4(),
        stakeholders=picked,
    )
    # Only one LLM call (stage 2)
    assert len(llm.calls) == 1
    assert {p.name for p in personas} == {"林阿嬤", "陳組長"}


@pytest.mark.asyncio
async def test_generate_stream_with_stakeholders_emits_synthetic_mapping_done() -> None:
    """generate_stream with stakeholders must still emit stage events."""

    class _StubStream:
        def __init__(self, sync_replies: list[str], stream_chunks: list[str]) -> None:
            self._sync = list(sync_replies)
            self._chunks = list(stream_chunks)
            self.calls: list[dict[str, Any]] = []

        async def chat_completion(self, messages, **kwargs):
            self.calls.append({"sync": True})
            return _StubResponse(content=self._sync.pop(0))

        async def chat_completion_stream(self, messages, **kwargs):
            self.calls.append({"stream": True, "messages": messages})
            for chunk in self._chunks:
                yield chunk

    stage2 = json.dumps(
        {
            "personas": [
                {
                    "name": "林阿嬤",
                    "role": "獨居農婦",
                    "expertise": "務農、地形",
                    "personality_axis": "supportive",
                    "personality_desc": "溫和、節省",
                    "backstory": "獨居十年",
                    "lens_affinities": {
                        "empathy": 0.9,
                        "structure": 0.3,
                        "creativity": 0.2,
                        "feasibility": 0.4,
                    },
                }
            ]
        },
        ensure_ascii=False,
    )
    llm = _StubStream([], [stage2])
    gen = PersonaGenerator(llm_service=llm)
    picked = [
        StakeholderSuggestion(
            id="id1", name="林阿嬤", role="獨居農婦", relevance="直接使用者"
        )
    ]
    events = [
        ev
        async for ev in gen.generate_stream(
            title="x",
            description=None,
            constraints=None,
            num_personas=1,
            owning_user_id=uuid4(),
            stakeholders=picked,
        )
    ]
    # Should not call the sync stage-1 LLM endpoint.
    assert all(c.get("stream") for c in llm.calls)
    types = [ev["type"] for ev in events]
    assert types[0] == "stage" and events[0]["status"] == "start"
    # Second event is mapping done with category_count=1
    assert events[1]["stage"] == "stakeholder_mapping"
    assert events[1]["status"] == "done"
    assert events[1]["category_count"] == 1
    assert any(ev["type"] == "persona" for ev in events)
