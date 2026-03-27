from __future__ import annotations

import json
import logging

from app.agents.prompts.base import BASE_PERSONA_PROMPT, FULL_AI_MODE_PROMPT
from app.agents.prompts.discover_subphase import (
    DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS,
    determine_discover_subphase,
)
from app.agents.prompts.roles import CREW_ROLE_PROMPT, SUPERVISOR_ROLE_PROMPT
from app.agents.prompts.stages import STAGE_PROMPTS

logger = logging.getLogger(__name__)

_RESPONSE_FORMAT_INSTRUCTION = """\
請以 JSON 格式回應，格式如下：
{
  "reasoning": "簡短思考（1-2句）",
  "actions": [
    {"type": "chat_message", "content": "你要在聊天室說的話"},
    {"type": "add_note", "content": "便條紙內容", "color": "yellow"}
  ]
}

重要規則：
- 每次回應必須包含至少一個 chat_message
- chat_message 必須回應最近聊天中某人的發言（引用對方的觀點）
- 不要每次都貼便條紙！只在你有新的、白板上還沒有的想法時才 add_note
- 貼之前先看白板上已有的便條紙，避免重複
- 如果 Supervisor/主持人要求停止貼便條紙或整理白板，你必須服從，只回 chat_message
- add_note 的 color 可選：yellow、blue、green、red、orange、violet
- 支援的 action types：chat_message、add_note、move_note、edit_note、delete_note、group_notes、no_action
- reasoning 請簡短，把 token 留給 actions
- 只回應 JSON，不要包含任何其他文字。\
"""


def _is_all_ai(context: dict) -> bool:
    """Return True if every seat is occupied by an AI (no humans present)."""
    seats: list[dict] = context.get("seats", [])
    if not seats:
        return False
    return all(s.get("type") == "ai" for s in seats)


def _build_context_description(context: dict) -> str:
    """Serialise the context buffer dict into a natural language description."""
    parts: list[str] = []

    stage = context.get("current_stage", "unknown")
    duration = context.get("stage_duration_minutes", 0)
    parts.append(f"【目前狀態】當前階段：{stage}，已進行 {duration} 分鐘。")

    # Inject Discover sub-phase info
    if stage == "discover":
        canvas_for_subphase = context.get("canvas_state", {})
        chat_for_subphase = context.get("recent_chat", [])
        subphase = determine_discover_subphase(canvas_for_subphase, chat_for_subphase, duration)
        subphase_labels = {"early": "前期（暖身）", "mid": "中期（活躍討論）", "late": "後期（接近飽和）"}
        parts.append(f"【發散子階段】{subphase_labels.get(subphase.value, subphase.value)}")

    # Canvas state — show summary + last few notes (avoid token bloat)
    canvas = context.get("canvas_state", {})
    total_notes = canvas.get("total_notes", 0)
    groups: list[dict] = canvas.get("groups", [])
    ungrouped: list[str] = canvas.get("ungrouped", [])
    parts.append(
        f"【白板狀態】共 {total_notes} 張便條紙，"
        f"已分成 {len(groups)} 個群組，"
        f"未分群 {len(ungrouped)} 張。"
    )

    if groups:
        group_summary = "；".join(
            f"{g.get('name', '未命名')}（{len(g.get('notes', []))} 張）"
            for g in groups
        )
        parts.append(f"群組：{group_summary}。")

    notes: list[dict] = canvas.get("notes", [])
    if notes:
        # Show only last 10 notes to save tokens; show all content
        recent_notes = notes[-10:]
        note_lines = [
            f"  - [{n.get('id', '?')}] {n.get('content', '')}"
            for n in recent_notes
        ]
        if len(notes) > 10:
            parts.append(f"便條紙（最近 10 張，共 {len(notes)} 張）：\n" + "\n".join(note_lines))
        else:
            parts.append("便條紙列表：\n" + "\n".join(note_lines))
        parts.append("⚠️ 貼新便條紙前，先檢查白板上是否已有類似內容，避免重複。")

    # Chat — mark supervisor messages with ⭐ and human messages with 👤
    recent_chat: list[dict] = context.get("recent_chat", [])
    if recent_chat:
        # Only show last 8 to save tokens
        recent_msgs = recent_chat[-8:]
        chat_lines = []
        for m in recent_msgs:
            sender = m.get("sender", "?")
            prefix = ""
            if "supervisor" in sender.lower() or "主持人" in sender:
                prefix = "⭐[主持人] "
            elif "human" in sender.lower() or "(human)" in sender:
                prefix = "👤[人類] "
            chat_lines.append(
                f"  {prefix}{sender}：{m.get('content', '')}"
            )
        parts.append(
            "【最近聊天（你必須回應其中一則，不可以各說各話）】\n"
            + "\n".join(chat_lines)
        )
    else:
        parts.append("【最近聊天】目前沒有聊天記錄。")

    seats: list[dict] = context.get("seats", [])
    if seats:
        seat_lines = [
            f"  - {s.get('role', '?')}：{s.get('type', '?')}"
            + (f"（{s.get('user_name', s.get('agent_id', ''))}）" if s.get("user_name") or s.get("agent_id") else "")
            for s in seats
        ]
        parts.append("【席位狀態】\n" + "\n".join(seat_lines))

    my_seat = context.get("my_seat", "unknown")
    parts.append(f"【我的席位】{my_seat}")

    my_actions: list[dict] = context.get("my_recent_actions", [])
    if my_actions:
        action_lines = [
            f"  - [{a.get('time', '?')}] {a.get('type', '?')}：{a.get('content', '')}"
            for a in my_actions
        ]
        parts.append("【我最近的行動】\n" + "\n".join(action_lines))
    else:
        parts.append("【我最近的行動】目前還沒有行動記錄。")

    return "\n".join(parts)


class PromptAssembler:
    """Assemble a 4-layer prompt for the Think phase.

    Layers:
    1. Base persona (fixed)
    2. Role (supervisor / crew)
    3. Stage strategy
    4. Context buffer (natural language)
    """

    def assemble(self, context: dict) -> list[dict]:
        """Return a list of OpenAI-style message dicts."""
        role = context.get("my_seat", "crew")
        is_supervisor = str(role).lower().startswith("supervisor")
        stage = context.get("current_stage", "discover")

        # Layer 1 — base persona
        system_parts = [BASE_PERSONA_PROMPT]

        # Layer 2 — role
        system_parts.append(
            SUPERVISOR_ROLE_PROMPT if is_supervisor else CREW_ROLE_PROMPT
        )

        # Layer 3 — stage strategy (Supervisor gets sub-phase prompts in Discover)
        if stage == "discover" and is_supervisor:
            canvas = context.get("canvas_state", {})
            chat = context.get("recent_chat", [])
            duration = context.get("stage_duration_minutes", 0)
            subphase = determine_discover_subphase(canvas, chat, duration)
            stage_prompt = DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS[subphase]
        else:
            stage_prompt = STAGE_PROMPTS.get(stage, STAGE_PROMPTS["discover"])
        system_parts.append(stage_prompt)

        # Full AI mode appendix
        if _is_all_ai(context):
            system_parts.append(FULL_AI_MODE_PROMPT)

        # Response format instruction
        system_parts.append(_RESPONSE_FORMAT_INSTRUCTION)

        system_message = "\n\n".join(system_parts)

        # Layer 4 — context buffer as user message
        context_description = _build_context_description(context)
        user_message = (
            f"以下是目前的工作坊狀態，請根據這些資訊決定你的下一步行動：\n\n"
            f"{context_description}"
        )

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
