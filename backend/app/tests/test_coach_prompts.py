"""Unit tests for DT 教練 prompt 組合（認知師徒制改寫版）。

驗證重點：
  - system prompt 必須包含使用者名稱、stage、micro_phase、group/canvas 兩段摘要。
  - 空摘要會被替換為「（暫無）」（不留空行）。
  - personal_history 依 created_at 由舊到新排序，user/assistant 正確對應。
  - 最末必為當前 user message。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.coach.prompts import DT_COACH_SYSTEM_PROMPT, build_messages


def _msg(
    content: str,
    sender_type: str = "human",
    minutes_ago: int = 0,
) -> SimpleNamespace:
    """產生 build_messages 期望的 Message-like 物件（duck typed）。"""
    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return SimpleNamespace(
        content=content,
        sender_type=sender_type,
        created_at=now,
    )


@pytest.mark.unit
def test_system_prompt_includes_all_summary_fields() -> None:
    messages = build_messages(
        stage="discover",
        micro_phase="empathy_map",
        user_display_name="小華",
        group_summary_text="- 小明：在討論 persona\n- 小美：問訪談對象",
        canvas_summary_text="- 總覽：便條紙 8 張、分群 2 群、整齊度 0.7",
        personal_history=[],
        current_user_message="我卡在 POV 怎麼寫",
    )

    assert messages[0]["role"] == "system"
    system = messages[0]["content"]
    assert "小華" in system
    assert "discover" in system
    assert "empathy_map" in system
    assert "小明" in system
    assert "便條紙 8 張" in system
    # 認知師徒制核心字眼必須出現。
    assert "Modeling" in system
    assert "Cognitive Apprenticeship" in system or "認知師徒制" in system


@pytest.mark.unit
def test_empty_summaries_fall_back_to_placeholder() -> None:
    messages = build_messages(
        stage="discover",
        micro_phase="empathy_map",
        user_display_name="小華",
        group_summary_text="",
        canvas_summary_text="   ",  # 只有空白也算空
        personal_history=[],
        current_user_message="hi",
    )
    system = messages[0]["content"]
    assert system.count("（暫無）") == 2


@pytest.mark.unit
def test_history_sorted_and_roles_mapped() -> None:
    history = [
        _msg("第三句 user", "human", minutes_ago=1),
        _msg("第一句 user", "human", minutes_ago=10),
        _msg("第二句 coach", "ai", minutes_ago=5),
    ]
    messages = build_messages(
        stage="discover",
        micro_phase="empathy_map",
        user_display_name="小華",
        group_summary_text="x",
        canvas_summary_text="y",
        personal_history=history,
        current_user_message="這一輪的問題",
    )

    # 預期：[system, user(第一), assistant(第二), user(第三), user(current)]
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user", "user"]
    assert messages[1]["content"] == "第一句 user"
    assert messages[2]["content"] == "第二句 coach"
    assert messages[3]["content"] == "第三句 user"
    assert messages[-1]["content"] == "這一輪的問題"


@pytest.mark.unit
def test_template_contains_six_stage_cycle() -> None:
    # 守護回歸：六階段表必須完整。
    for stage in (
        "Modeling",
        "Coaching",
        "Scaffolding",
        "Articulation",
        "Reflection",
        "Exploration",
    ):
        assert stage in DT_COACH_SYSTEM_PROMPT, f"missing stage marker: {stage}"
