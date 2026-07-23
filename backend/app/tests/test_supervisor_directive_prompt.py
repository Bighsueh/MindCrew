"""Tests for Phase 28 supervisor invite-human prompt fragment injection.

驗證 PromptAssembler 對 supervisor 注入 SUPERVISOR_DIRECTIVE_PROMPT 之外，
依 supervisor_mode + has_human_seat 條件追加邀請人類成員 fragment。
"""

from __future__ import annotations

import pytest

from app.agents.prompts.assembler import PromptAssembler
from app.agents.prompts.blackboard_rules import (
    SUPERVISOR_DIRECTIVE_PROMPT,
    SUPERVISOR_INVITE_HUMAN_FACILITATOR,
    SUPERVISOR_INVITE_HUMAN_PARTICIPANT,
)
from app.agents.prompts.interpolation import interpolate_human_name
from app.agents.turn_controller import OpenFloorPolicy, RoundRobinPolicy


def _make_supervisor_context(
    *,
    supervisor_mode: str = "facilitator",
    has_human: bool = True,
    turn_controller=None,
) -> dict:
    """Build a supervisor context with blackboard data + optional human seat."""
    seats = [
        {"role": "supervisor", "type": "ai"},
        {"role": "crew_1", "type": "ai"},
        {"role": "crew_2", "type": "ai"},
    ]
    if has_human:
        seats.append({"role": "crew_3", "type": "human", "user_name": "Alice"})
    return {
        "my_seat": "supervisor",
        "current_stage": "discover",
        "stage_duration_minutes": 5,
        "seats": seats,
        "supervisor_mode": supervisor_mode,
        "blackboard": {
            "other_agent_intentions": [
                {
                    "seat_role": "crew_1",
                    "next_intent": "add_note",
                    "focus_topic": "支付",
                    "viewpoint": "從技術角度",
                    "reasoning_summary": "缺技術觀點",
                },
            ],
            "topic_saturation": {
                "stage": "discover",
                "topics": [],
                "blind_spots": [],
            },
            "coordination": None,
        },
        "canvas_state": {"total_notes": 3, "groups": [], "ungrouped": [], "notes": []},
        "recent_chat": [],
        "project_name": "Test",
        "project_description": "Test",
        "_turn_controller": turn_controller,
    }


def _build_system_prompt(ctx: dict) -> str:
    """組裝 supervisor 的完整 system prompt（取 first message content）。"""
    msgs = PromptAssembler().assemble(ctx)
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _interp(constant: str, ctx: dict) -> str:
    """Phase 42 B2（守則 6，#15）：有真人席時 @{name}/@{顯示名} 會被插值成真人顯示名，
    斷言改用插值後形式（assembler 行為）。"""
    return interpolate_human_name(constant, ctx["seats"])


@pytest.mark.unit
def test_facilitator_with_human_appends_invite_fragment() -> None:
    ctx = _make_supervisor_context(supervisor_mode="facilitator", has_human=True)
    prompt = _build_system_prompt(ctx)
    assert _interp(SUPERVISOR_DIRECTIVE_PROMPT, ctx) in prompt
    assert _interp(SUPERVISOR_INVITE_HUMAN_FACILITATOR, ctx) in prompt
    assert _interp(SUPERVISOR_INVITE_HUMAN_PARTICIPANT, ctx) not in prompt
    # 守則 6 行為保證：邀請範例帶真人顯示名、原始佔位符不殘留。
    assert "@Alice" in prompt
    assert "@{name}" not in prompt


@pytest.mark.unit
def test_participant_with_human_appends_invite_fragment() -> None:
    ctx = _make_supervisor_context(supervisor_mode="participant", has_human=True)
    prompt = _build_system_prompt(ctx)
    assert _interp(SUPERVISOR_DIRECTIVE_PROMPT, ctx) in prompt
    assert _interp(SUPERVISOR_INVITE_HUMAN_PARTICIPANT, ctx) in prompt
    assert _interp(SUPERVISOR_INVITE_HUMAN_FACILITATOR, ctx) not in prompt
    assert "@Alice" in prompt


@pytest.mark.unit
def test_silent_with_human_does_not_append_invite_fragment() -> None:
    ctx = _make_supervisor_context(supervisor_mode="silent", has_human=True)
    prompt = _build_system_prompt(ctx)
    assert _interp(SUPERVISOR_DIRECTIVE_PROMPT, ctx) in prompt
    # silent mode: 完全不附加邀請人類段（不依賴 LLM 自我約束）
    assert _interp(SUPERVISOR_INVITE_HUMAN_FACILITATOR, ctx) not in prompt
    assert _interp(SUPERVISOR_INVITE_HUMAN_PARTICIPANT, ctx) not in prompt


@pytest.mark.unit
def test_no_human_seat_does_not_append_invite_fragment() -> None:
    # all-AI 場景：facilitator mode 也不該附加（沒邀請對象）。
    # Phase 42 補正 R2：全 AI 房 prompt 內佔位符降級「大家」（洩漏源頭在 LLM
    # 照抄例句），故 directive prompt 以「降級後」的形式出現、全文不得殘留 @{。
    ctx = _make_supervisor_context(supervisor_mode="facilitator", has_human=False)
    prompt = _build_system_prompt(ctx)
    degraded = SUPERVISOR_DIRECTIVE_PROMPT.replace("@{顯示名}", "大家").replace(
        "@{name}", "大家"
    )
    assert degraded in prompt
    assert "@{name}" not in prompt and "@{顯示名}" not in prompt
    assert SUPERVISOR_INVITE_HUMAN_FACILITATOR not in prompt
    assert SUPERVISOR_INVITE_HUMAN_PARTICIPANT not in prompt


@pytest.mark.unit
def test_non_cued_policy_skips_directive_prompt_entirely() -> None:
    # 既有 guard：非 cued policy 連 SUPERVISOR_DIRECTIVE_PROMPT 都不附加
    # → 也不該附加 invite-human fragment（regression guard）
    from uuid import uuid4

    rr = RoundRobinPolicy(uuid4())
    ctx_rr = _make_supervisor_context(
        supervisor_mode="facilitator", has_human=True, turn_controller=rr
    )
    prompt = _build_system_prompt(ctx_rr)
    assert SUPERVISOR_DIRECTIVE_PROMPT not in prompt
    assert SUPERVISOR_INVITE_HUMAN_FACILITATOR not in prompt

    of = OpenFloorPolicy(uuid4())
    ctx_of = _make_supervisor_context(
        supervisor_mode="facilitator", has_human=True, turn_controller=of
    )
    prompt2 = _build_system_prompt(ctx_of)
    assert SUPERVISOR_DIRECTIVE_PROMPT not in prompt2
    assert SUPERVISOR_INVITE_HUMAN_FACILITATOR not in prompt2


@pytest.mark.unit
def test_facilitator_and_participant_prompts_differ() -> None:
    """確認兩個 fragment 內容實質不同（避免複製貼上錯誤）。"""
    assert SUPERVISOR_INVITE_HUMAN_FACILITATOR != SUPERVISOR_INVITE_HUMAN_PARTICIPANT
    assert "Facilitator" in SUPERVISOR_INVITE_HUMAN_FACILITATOR
    assert "Participant" in SUPERVISOR_INVITE_HUMAN_PARTICIPANT
    # 兩者都該提到 pass 與溫和語氣
    for fragment in (
        SUPERVISOR_INVITE_HUMAN_FACILITATOR,
        SUPERVISOR_INVITE_HUMAN_PARTICIPANT,
    ):
        assert "pass" in fragment
        assert "溫和" in fragment


@pytest.mark.unit
def test_directive_prompt_rules_6_and_7() -> None:
    """Phase 42 B2（spec 04-03 §2.3.2.1）：守則 6 點名 @顯示名、守則 7 tag 紀律。"""
    # 守則 6：點名一律 @顯示名，與 invited_speaker 對齊（#15）
    assert "點名一律 @顯示名" in SUPERVISOR_DIRECTIVE_PROMPT
    assert "@{對方顯示名}" in SUPERVISOR_DIRECTIVE_PROMPT
    assert "「換你」" in SUPERVISOR_DIRECTIVE_PROMPT  # 禁模糊指代
    # 守則 7：tag=邀請必等／推進不 tag／crew 聊完不可越過真人（#16）
    assert "邀請就要等、推進就不 tag" in SUPERVISOR_DIRECTIVE_PROMPT
    assert "不可越過真人" in SUPERVISOR_DIRECTIVE_PROMPT
    # 守則 8（A3 先行落地）仍在
    assert "set_user_task" in SUPERVISOR_DIRECTIVE_PROMPT
