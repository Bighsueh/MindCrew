"""Tests for BlackboardManager — Redis read/write layer.

Covers:
- write_intention / read_other_intentions
- TTL expiry behavior
- mark_inactive (human takeover)
- clear_stage
- topic_saturation read/write
- coordination read
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import (
    AgentIntention,
    Coordination,
    TopicEntry,
    TopicSaturation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()


def _make_intention(
    agent_id: str = "agent_crew_1",
    seat_role: str = "crew_1",
    **overrides: object,
) -> AgentIntention:
    defaults = {
        "agent_id": agent_id,
        "seat_role": seat_role,
        "reasoning_summary": "白板上需要更多使用者觀點",
        "next_intent": "add_note",
        "focus_topic": "支付問題",
        "viewpoint": "從使用者體驗角度",
        "confidence": 0.8,
        "stage": "discover",
    }
    defaults.update(overrides)
    return AgentIntention(**defaults)  # type: ignore[arg-type]


def _seat_event(role: str, seat_type: str = "ai") -> str:
    agent_id = f"agent_{role}" if seat_type == "ai" else ""
    return json.dumps({
        "role": role,
        "type": seat_type,
        "agent_id": agent_id,
    })


async def _seed_seats(
    mgr: BlackboardManager,
    seats: list[tuple[str, str]] | None = None,
) -> None:
    """Push seat events into Redis so BlackboardManager can discover agents."""
    if seats is None:
        seats = [
            ("supervisor", "ai"),
            ("crew_1", "ai"),
            ("crew_2", "ai"),
            ("crew_3", "ai"),
            ("crew_4", "ai"),
        ]
    r = await mgr._get_redis()
    key = f"project:{PROJECT_ID}:seat_events"
    await r.delete(key)
    for role, stype in seats:
        await r.rpush(key, _seat_event(role, stype))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
async def mgr_crew1():
    m = BlackboardManager(PROJECT_ID, "agent_crew_1", "crew_1")
    await _seed_seats(m)
    yield m
    # cleanup
    r = await m._get_redis()
    keys = await r.keys(f"blackboard:{PROJECT_ID}:*")
    if keys:
        await r.delete(*keys)
    seat_key = f"project:{PROJECT_ID}:seat_events"
    await r.delete(seat_key)
    await r.aclose()


@pytest.fixture()
async def mgr_crew2():
    m = BlackboardManager(PROJECT_ID, "agent_crew_2", "crew_2")
    yield m
    r = await m._get_redis()
    await r.aclose()


class TestWriteReadIntention:
    """Write and read intentions between agents."""

    @pytest.mark.asyncio
    async def test_write_and_read(self, mgr_crew1, mgr_crew2) -> None:
        intention = _make_intention()
        await mgr_crew1.write_intention(intention)

        # crew_2 should see crew_1's intention
        others = await mgr_crew2.read_other_intentions()
        assert len(others) == 1
        assert others[0].agent_id == "agent_crew_1"
        assert others[0].focus_topic == "支付問題"
        assert others[0].viewpoint == "從使用者體驗角度"

    @pytest.mark.asyncio
    async def test_self_excluded(self, mgr_crew1) -> None:
        intention = _make_intention()
        await mgr_crew1.write_intention(intention)

        # crew_1 reading should NOT see its own intention
        others = await mgr_crew1.read_other_intentions()
        assert len(others) == 0

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, mgr_crew1, mgr_crew2) -> None:
        intention = _make_intention()
        await mgr_crew1.write_intention(intention)

        r = await mgr_crew1._get_redis()
        key = f"blackboard:{PROJECT_ID}:agent:agent_crew_1:intention"
        ttl = await r.ttl(key)
        # All-AI mode: TTL should be 30s
        assert 0 < ttl <= 30

    @pytest.mark.asyncio
    async def test_mixed_mode_ttl(self, mgr_crew1) -> None:
        # Add a human seat
        r = await mgr_crew1._get_redis()
        seat_key = f"project:{PROJECT_ID}:seat_events"
        await r.rpush(seat_key, _seat_event("crew_1", "human"))

        intention = _make_intention()
        await mgr_crew1.write_intention(intention)

        key = f"blackboard:{PROJECT_ID}:agent:agent_crew_1:intention"
        ttl = await r.ttl(key)
        # Mixed mode: TTL should be 120s
        assert ttl > 30
        assert ttl <= 120


class TestMarkInactive:
    """Human takeover — mark intention inactive."""

    @pytest.mark.asyncio
    async def test_mark_inactive(self, mgr_crew1, mgr_crew2) -> None:
        intention = _make_intention()
        await mgr_crew1.write_intention(intention)

        # Mark crew_1 inactive
        await mgr_crew1.mark_inactive()

        # crew_2 should not see inactive intention
        others = await mgr_crew2.read_other_intentions()
        assert len(others) == 0

    @pytest.mark.asyncio
    async def test_mark_inactive_no_intention(self, mgr_crew1) -> None:
        # Should not raise even if no intention exists
        await mgr_crew1.mark_inactive()


class TestTopicSaturation:
    """Topic saturation read/write."""

    @pytest.mark.asyncio
    async def test_write_and_read(self, mgr_crew1) -> None:
        sat = TopicSaturation(
            stage="discover",
            topics=[
                TopicEntry(
                    name="支付問題",
                    note_count=5,
                    contributors=["crew_1", "crew_2"],
                    viewpoint_diversity="low",
                    existing_angles=["使用者體驗"],
                    missing_angles=["技術限制", "商業模式"],
                    saturation="medium",
                ),
            ],
            blind_spots=["可及性", "多語系支援"],
        )
        await mgr_crew1.write_topic_saturation(sat)

        result = await mgr_crew1.read_topic_saturation()
        assert result is not None
        assert len(result.topics) == 1
        assert result.topics[0].name == "支付問題"
        assert result.topics[0].viewpoint_diversity == "low"
        assert result.blind_spots == ["可及性", "多語系支援"]

    @pytest.mark.asyncio
    async def test_read_empty(self, mgr_crew1) -> None:
        result = await mgr_crew1.read_topic_saturation()
        assert result is None


class TestClearStage:
    """Stage transition clears topic_saturation."""

    @pytest.mark.asyncio
    async def test_clear_stage(self, mgr_crew1) -> None:
        sat = TopicSaturation(stage="discover", topics=[], blind_spots=[])
        await mgr_crew1.write_topic_saturation(sat)

        # Should exist
        assert await mgr_crew1.read_topic_saturation() is not None

        # Clear
        await mgr_crew1.clear_stage("define")

        # Should be gone
        assert await mgr_crew1.read_topic_saturation() is None


class TestCoordination:
    """Coordination read (write is done externally)."""

    @pytest.mark.asyncio
    async def test_read_coordination(self, mgr_crew1) -> None:
        coord = Coordination(
            round=3,
            claimed_topics={"agent_crew_2": "支付問題"},
            recently_covered=["註冊體驗"],
        )
        # Write directly via Redis (Coordination write is external)
        r = await mgr_crew1._get_redis()
        key = f"blackboard:{PROJECT_ID}:coordination"
        await r.set(key, coord.model_dump_json(), ex=60)

        result = await mgr_crew1.read_coordination()
        assert result is not None
        assert result.round == 3
        assert result.claimed_topics == {"agent_crew_2": "支付問題"}

    @pytest.mark.asyncio
    async def test_read_empty_coordination(self, mgr_crew1) -> None:
        result = await mgr_crew1.read_coordination()
        assert result is None


class TestSchemas:
    """Blackboard schema validation."""

    def test_agent_intention_defaults(self) -> None:
        intention = AgentIntention(
            agent_id="test",
            seat_role="crew_1",
            reasoning_summary="test",
            next_intent="chat_message",
        )
        assert intention.focus_topic is None
        assert intention.viewpoint is None
        assert intention.confidence == 0.5
        assert intention.inactive is False

    def test_topic_entry_defaults(self) -> None:
        entry = TopicEntry(name="test")
        assert entry.note_count == 0
        assert entry.viewpoint_diversity == "low"
        assert entry.saturation == "low"

    def test_topic_saturation_serialization(self) -> None:
        sat = TopicSaturation(
            stage="discover",
            topics=[TopicEntry(name="x", note_count=3)],
            blind_spots=["a"],
        )
        raw = sat.model_dump_json()
        restored = TopicSaturation.model_validate_json(raw)
        assert restored.topics[0].name == "x"
        assert restored.blind_spots == ["a"]

    def test_coordination_serialization(self) -> None:
        coord = Coordination(round=5, claimed_topics={"a": "b"})
        raw = coord.model_dump_json()
        restored = Coordination.model_validate_json(raw)
        assert restored.round == 5
