"""Integration tests for Blackboard + Capability-based Crew — end-to-end flow.

Covers Step 7.9:
- Each Crew gets its own capability Prompt (not others')
- Agent Think writes intention to Blackboard (with viewpoint)
- Context Buffer returns blackboard field
- Supervisor evaluation writes topic_saturation
- Human takeover marks intention inactive
- TTL switching between all-AI and mixed modes
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import (
    AgentIntention,
    TopicEntry,
    TopicSaturation,
)
from app.agents.prompts.assembler import PromptAssembler
from app.agents.prompts.base import BASE_PERSONA_PROMPT
from app.agents.prompts.blackboard_rules import BLACKBOARD_COORDINATION_RULES
from app.agents.prompts.roles import (
    CREW_CAPABILITY_PROMPTS,
    CREW_CREATIVITY_PROMPT,
    CREW_EMPATHY_PROMPT,
    CREW_FEASIBILITY_PROMPT,
    CREW_ROLE_BASE_PROMPT,
    CREW_STRUCTURE_PROMPT,
    SUPERVISOR_ROLE_PROMPT,
)

PROJECT_ID = uuid4()


def _seat_event(role: str, seat_type: str = "ai") -> str:
    return json.dumps({
        "role": role,
        "type": seat_type,
        "agent_id": f"agent_{role}" if seat_type == "ai" else "",
    })


async def _seed_all_ai_seats(mgr: BlackboardManager) -> None:
    r = await mgr._get_redis()
    key = f"project:{PROJECT_ID}:seat_events"
    await r.delete(key)
    for role in ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]:
        await r.rpush(key, _seat_event(role, "ai"))


async def _cleanup(mgr: BlackboardManager) -> None:
    r = await mgr._get_redis()
    for pattern in [f"blackboard:{PROJECT_ID}:*", f"project:{PROJECT_ID}:*"]:
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    await r.aclose()


# ---------------------------------------------------------------------------
# Test: Each Crew gets its own capability Prompt
# ---------------------------------------------------------------------------


class TestCrewCapabilityIsolation:
    """Verify that each Crew only gets its own capability prompt."""

    CAPABILITY_MAP = {
        "crew_1": CREW_EMPATHY_PROMPT,
        "crew_2": CREW_STRUCTURE_PROMPT,
        "crew_3": CREW_CREATIVITY_PROMPT,
        "crew_4": CREW_FEASIBILITY_PROMPT,
    }

    @pytest.mark.parametrize("seat_role", ["crew_1", "crew_2", "crew_3", "crew_4"])
    def test_each_crew_isolated(self, seat_role: str) -> None:
        ctx = {
            "my_seat": seat_role,
            "current_stage": "discover",
            "stage_duration_minutes": 5,
            "seats": [{"role": r, "type": "ai"} for r in
                      ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]],
            "canvas_state": {"total_notes": 0, "groups": [], "ungrouped": [], "notes": []},
            "recent_chat": [],
        }
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]

        # Must contain own capability
        assert self.CAPABILITY_MAP[seat_role] in system

        # Must NOT contain others
        for role, prompt in self.CAPABILITY_MAP.items():
            if role != seat_role:
                assert prompt not in system


# ---------------------------------------------------------------------------
# Test: Blackboard write/read full cycle
# ---------------------------------------------------------------------------


class TestBlackboardFullCycle:
    """Simulate the full write → read → inactive cycle."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.crew1 = BlackboardManager(PROJECT_ID, "agent_crew_1", "crew_1")
        self.crew2 = BlackboardManager(PROJECT_ID, "agent_crew_2", "crew_2")
        self.supervisor = BlackboardManager(PROJECT_ID, "agent_supervisor", "supervisor")
        await _seed_all_ai_seats(self.crew1)
        yield
        await _cleanup(self.crew1)

    @pytest.mark.asyncio
    async def test_intention_write_and_cross_read(self) -> None:
        """crew_1 writes intention → crew_2 reads it with viewpoint."""
        intention = AgentIntention(
            agent_id="agent_crew_1",
            seat_role="crew_1",
            reasoning_summary="使用者痛點尚未充分討論",
            next_intent="add_note",
            focus_topic="支付問題",
            viewpoint="從使用者體驗角度",
            confidence=0.8,
            stage="discover",
        )
        await self.crew1.write_intention(intention)

        others = await self.crew2.read_other_intentions()
        assert len(others) >= 1
        crew1_intention = next(
            (i for i in others if i.agent_id == "agent_crew_1"), None
        )
        assert crew1_intention is not None
        assert crew1_intention.viewpoint == "從使用者體驗角度"
        assert crew1_intention.focus_topic == "支付問題"

    @pytest.mark.asyncio
    async def test_supervisor_writes_topic_saturation(self) -> None:
        """Supervisor writes topic saturation → all agents can read."""
        sat = TopicSaturation(
            stage="discover",
            topics=[
                TopicEntry(
                    name="支付問題",
                    note_count=5,
                    contributors=["crew_1", "crew_2", "crew_3"],
                    viewpoint_diversity="low",
                    existing_angles=["使用者體驗", "使用者抱怨"],
                    missing_angles=["技術限制", "商業模式"],
                    saturation="medium",
                ),
            ],
            blind_spots=["可及性", "多語系支援"],
        )
        await self.supervisor.write_topic_saturation(sat)

        # crew_1 reads
        result = await self.crew1.read_topic_saturation()
        assert result is not None
        assert len(result.topics) == 1
        assert result.topics[0].missing_angles == ["技術限制", "商業模式"]
        assert result.blind_spots == ["可及性", "多語系支援"]

    @pytest.mark.asyncio
    async def test_human_takeover_marks_inactive(self) -> None:
        """Human takes crew_1's seat → crew_2 can no longer see crew_1's intention."""
        intention = AgentIntention(
            agent_id="agent_crew_1",
            seat_role="crew_1",
            reasoning_summary="test",
            next_intent="chat_message",
            stage="discover",
        )
        await self.crew1.write_intention(intention)

        # Before: crew_2 sees it
        others_before = await self.crew2.read_other_intentions()
        assert any(i.agent_id == "agent_crew_1" for i in others_before)

        # Human takes over
        await self.crew1.mark_inactive()

        # After: crew_2 does NOT see it
        others_after = await self.crew2.read_other_intentions()
        assert not any(i.agent_id == "agent_crew_1" for i in others_after)

    @pytest.mark.asyncio
    async def test_stage_clear(self) -> None:
        """Stage change clears topic_saturation."""
        sat = TopicSaturation(stage="discover", topics=[], blind_spots=[])
        await self.supervisor.write_topic_saturation(sat)
        assert await self.crew1.read_topic_saturation() is not None

        await self.supervisor.clear_stage("define")
        assert await self.crew1.read_topic_saturation() is None


# ---------------------------------------------------------------------------
# Test: Context Buffer blackboard field + Prompt injection
# ---------------------------------------------------------------------------


class TestContextBufferBlackboardField:
    """Verify that Blackboard data flows into PromptAssembler correctly."""

    def test_prompt_includes_blackboard_when_present(self) -> None:
        ctx = {
            "my_seat": "crew_2",
            "current_stage": "discover",
            "stage_duration_minutes": 10,
            "seats": [{"role": r, "type": "ai"} for r in
                      ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]],
            "canvas_state": {"total_notes": 5, "groups": [], "ungrouped": [], "notes": []},
            "recent_chat": [{"sender": "Crew 1", "content": "使用者很痛苦"}],
            "blackboard": {
                "other_agent_intentions": [
                    {
                        "seat_role": "crew_1",
                        "next_intent": "add_note",
                        "focus_topic": "使用者痛點",
                        "viewpoint": "從同理心角度",
                        "reasoning_summary": "需要更多使用者觀點",
                    },
                ],
                "topic_saturation": {
                    "stage": "discover",
                    "topics": [
                        {
                            "name": "使用者痛點",
                            "saturation": "medium",
                            "viewpoint_diversity": "low",
                            "missing_angles": ["技術面", "商業面"],
                        },
                    ],
                    "blind_spots": ["效能問題"],
                },
                "coordination": None,
            },
        }
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        user = msgs[1]["content"]

        # System should include blackboard rules
        assert BLACKBOARD_COORDINATION_RULES in system
        # User message should include blackboard data
        assert "crew_1" in user
        assert "使用者痛點" in user
        assert "同理心" in user
        assert "效能問題" in user

    def test_prompt_excludes_blackboard_when_absent(self) -> None:
        ctx = {
            "my_seat": "crew_2",
            "current_stage": "discover",
            "stage_duration_minutes": 5,
            "seats": [{"role": "crew_2", "type": "ai"}],
            "canvas_state": {"total_notes": 0, "groups": [], "ungrouped": [], "notes": []},
            "recent_chat": [],
        }
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        assert BLACKBOARD_COORDINATION_RULES not in system


# ---------------------------------------------------------------------------
# Test: TTL switching
# ---------------------------------------------------------------------------


class TestTTLSwitching:
    """Verify TTL changes between all-AI and mixed modes."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.mgr = BlackboardManager(PROJECT_ID, "agent_crew_1", "crew_1")
        await _seed_all_ai_seats(self.mgr)
        yield
        await _cleanup(self.mgr)

    @pytest.mark.asyncio
    async def test_all_ai_short_ttl(self) -> None:
        ttl = await self.mgr._intention_ttl()
        assert ttl == 30

        coord_ttl = await self.mgr._coordination_ttl()
        assert coord_ttl == 15

    @pytest.mark.asyncio
    async def test_mixed_mode_long_ttl(self) -> None:
        # Add a human seat
        r = await self.mgr._get_redis()
        key = f"project:{PROJECT_ID}:seat_events"
        await r.rpush(key, _seat_event("crew_1", "human"))

        ttl = await self.mgr._intention_ttl()
        assert ttl == 120

        coord_ttl = await self.mgr._coordination_ttl()
        assert coord_ttl == 60
