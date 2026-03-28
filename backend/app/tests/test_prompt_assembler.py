"""Tests for PromptAssembler — capability-based Crew prompt assembly.

Covers specs/08-test-strategy.md §3.3.3:
- Supervisor + each stage
- Crew 1-4 + various stages (capability isolation)
- Full AI mode extra prompt
- Context injection
"""
from __future__ import annotations

import pytest

from app.agents.prompts.assembler import PromptAssembler
from app.agents.prompts.base import BASE_PERSONA_PROMPT, FULL_AI_MODE_PROMPT
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
from app.agents.prompts.stages import STAGE_PROMPTS


def _make_context(
    *,
    my_seat: str = "crew_1",
    stage: str = "discover",
    seats: list[dict] | None = None,
) -> dict:
    """Build a minimal context dict for testing."""
    if seats is None:
        seats = [
            {"role": "supervisor", "type": "ai"},
            {"role": "crew_1", "type": "ai"},
            {"role": "crew_2", "type": "ai"},
            {"role": "crew_3", "type": "ai"},
            {"role": "crew_4", "type": "ai"},
        ]
    return {
        "my_seat": my_seat,
        "current_stage": stage,
        "stage_duration_minutes": 5,
        "seats": seats,
        "canvas_state": {"total_notes": 3, "groups": [], "ungrouped": [], "notes": []},
        "recent_chat": [{"sender": "Crew 1", "content": "大家好"}],
        "project_name": "測試專案",
        "project_description": "測試用",
    }


class TestSupervisorAssembly:
    """Supervisor + various stages."""

    def test_supervisor_discover(self) -> None:
        ctx = _make_context(my_seat="supervisor", stage="discover")
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]

        assert BASE_PERSONA_PROMPT in system
        assert SUPERVISOR_ROLE_PROMPT in system
        # Should NOT contain any Crew capability prompt
        assert CREW_ROLE_BASE_PROMPT not in system
        for cap in CREW_CAPABILITY_PROMPTS.values():
            assert cap not in system

    def test_supervisor_define(self) -> None:
        ctx = _make_context(my_seat="supervisor", stage="define")
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]

        assert BASE_PERSONA_PROMPT in system
        assert SUPERVISOR_ROLE_PROMPT in system
        assert STAGE_PROMPTS["define"] in system


class TestCrewCapabilityAssembly:
    """Each Crew gets base + own capability prompt only."""

    @pytest.mark.parametrize(
        ("seat_role", "expected_prompt", "stage"),
        [
            ("crew_1", CREW_EMPATHY_PROMPT, "define"),
            ("crew_2", CREW_STRUCTURE_PROMPT, "discover"),
            ("crew_3", CREW_CREATIVITY_PROMPT, "develop"),
            ("crew_4", CREW_FEASIBILITY_PROMPT, "deliver"),
        ],
        ids=["empathy-define", "structure-discover", "creativity-develop", "feasibility-deliver"],
    )
    def test_crew_gets_own_capability(
        self, seat_role: str, expected_prompt: str, stage: str
    ) -> None:
        ctx = _make_context(my_seat=seat_role, stage=stage)
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]

        # Must contain base persona + crew base + own capability + stage
        assert BASE_PERSONA_PROMPT in system
        assert CREW_ROLE_BASE_PROMPT in system
        assert expected_prompt in system
        assert STAGE_PROMPTS[stage] in system

    @pytest.mark.parametrize(
        ("seat_role", "own_prompt"),
        [
            ("crew_1", CREW_EMPATHY_PROMPT),
            ("crew_2", CREW_STRUCTURE_PROMPT),
            ("crew_3", CREW_CREATIVITY_PROMPT),
            ("crew_4", CREW_FEASIBILITY_PROMPT),
        ],
        ids=["crew_1", "crew_2", "crew_3", "crew_4"],
    )
    def test_crew_does_not_contain_other_capabilities(
        self, seat_role: str, own_prompt: str
    ) -> None:
        """Each Crew must NOT contain other Crews' capability prompts."""
        ctx = _make_context(my_seat=seat_role, stage="discover")
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]

        for role, prompt in CREW_CAPABILITY_PROMPTS.items():
            if role == seat_role:
                assert prompt in system
            else:
                assert prompt not in system, (
                    f"{seat_role} should not contain {role}'s capability prompt"
                )


class TestFullAIMode:
    """When all seats are AI, extra prompt is appended."""

    def test_all_ai_includes_extra_prompt(self) -> None:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        # Default seats are all AI
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        assert FULL_AI_MODE_PROMPT in system

    def test_mixed_mode_excludes_extra_prompt(self) -> None:
        seats = [
            {"role": "supervisor", "type": "ai"},
            {"role": "crew_1", "type": "human"},
            {"role": "crew_2", "type": "ai"},
            {"role": "crew_3", "type": "ai"},
            {"role": "crew_4", "type": "ai"},
        ]
        ctx = _make_context(my_seat="crew_2", stage="discover", seats=seats)
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        assert FULL_AI_MODE_PROMPT not in system


class TestContextInjection:
    """Context buffer is serialized into the user message (Layer 4)."""

    def test_user_message_contains_project_info(self) -> None:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        msgs = PromptAssembler().assemble(ctx)
        user = msgs[1]["content"]
        assert "測試專案" in user
        assert "discover" in user

    def test_user_message_contains_chat(self) -> None:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        msgs = PromptAssembler().assemble(ctx)
        user = msgs[1]["content"]
        assert "大家好" in user

    def test_message_structure(self) -> None:
        ctx = _make_context(my_seat="crew_3", stage="develop")
        msgs = PromptAssembler().assemble(ctx)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"


class TestBlackboardPromptInjection:
    """Blackboard rules and data injection into prompt."""

    def _bb_context(self) -> dict:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        ctx["blackboard"] = {
            "other_agent_intentions": [
                {
                    "seat_role": "crew_2",
                    "next_intent": "add_note",
                    "focus_topic": "支付問題",
                    "viewpoint": "從技術可行性角度",
                    "reasoning_summary": "白板上缺少技術面觀點",
                },
            ],
            "topic_saturation": {
                "stage": "discover",
                "topics": [
                    {
                        "name": "支付問題",
                        "saturation": "medium",
                        "viewpoint_diversity": "low",
                        "missing_angles": ["技術限制", "商業模式"],
                    },
                ],
                "blind_spots": ["可及性", "多語系支援"],
            },
            "coordination": None,
        }
        return ctx

    def test_blackboard_rules_in_system_when_data_present(self) -> None:
        ctx = self._bb_context()
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        assert BLACKBOARD_COORDINATION_RULES in system

    def test_blackboard_rules_absent_when_no_data(self) -> None:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        # No blackboard or empty blackboard
        ctx["blackboard"] = {
            "other_agent_intentions": [],
            "topic_saturation": None,
            "coordination": None,
        }
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        assert BLACKBOARD_COORDINATION_RULES not in system

    def test_blackboard_data_in_user_message(self) -> None:
        ctx = self._bb_context()
        msgs = PromptAssembler().assemble(ctx)
        user = msgs[1]["content"]
        assert "支付問題" in user
        assert "crew_2" in user
        assert "技術可行性" in user
        assert "可及性" in user
        assert "多語系支援" in user

    def test_missing_angles_in_user_message(self) -> None:
        ctx = self._bb_context()
        msgs = PromptAssembler().assemble(ctx)
        user = msgs[1]["content"]
        assert "技術限制" in user
        assert "商業模式" in user

    def test_no_blackboard_section_when_empty(self) -> None:
        ctx = _make_context(my_seat="crew_1", stage="discover")
        msgs = PromptAssembler().assemble(ctx)
        user = msgs[1]["content"]
        assert "Blackboard" not in user


class TestAllCrewAllStages:
    """Ensure all 4 Crews × 4 stages assemble without error."""

    @pytest.mark.parametrize("seat_role", ["crew_1", "crew_2", "crew_3", "crew_4"])
    @pytest.mark.parametrize("stage", ["discover", "define", "develop", "deliver"])
    def test_assembly_succeeds(self, seat_role: str, stage: str) -> None:
        ctx = _make_context(my_seat=seat_role, stage=stage)
        msgs = PromptAssembler().assemble(ctx)
        system = msgs[0]["content"]
        # Basic checks: contains base + crew base + some capability + stage
        assert BASE_PERSONA_PROMPT in system
        assert CREW_ROLE_BASE_PROMPT in system
        assert CREW_CAPABILITY_PROMPTS[seat_role] in system
