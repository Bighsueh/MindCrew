from __future__ import annotations

import logging

from app.agents.prompts.base import BASE_PERSONA_PROMPT, FULL_AI_MODE_PROMPT
from app.agents.prompts.blackboard_rules import (
    BLACKBOARD_COORDINATION_RULES,
    SUPERVISOR_DIRECTIVE_PROMPT,
)
from app.agents.prompts.comm_goal import COMM_GOAL_PROMPTS
from app.agents.prompts.context_serializer import build_context_description
from app.agents.prompts.discover_subphase import (
    DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS,
    determine_discover_subphase,
)
from app.agents.prompts.roles import (
    CREW_CAPABILITY_PROMPTS,
    CREW_ROLE_BASE_PROMPT,
    PEER_INTERACTION_PROMPT,
    SUPERVISOR_DISCUSSION_RULES,
    SUPERVISOR_FACILITATOR_RULES,
    SUPERVISOR_ROLE_PROMPT,
    SUPERVISOR_SILENT_RULES,
    render_persona_prompt,
)
from app.agents.personas.models import persona_from_dict
from app.agents.prompts.stages import STAGE_PROMPTS

logger = logging.getLogger(__name__)

_RESPONSE_FORMAT_BASE = """\
請以 JSON 格式回應，格式如下：
{
  "reasoning": "簡短思考（1-2句）",
  "focus_topic": "你目前聚焦的主題（簡短描述）",
  "viewpoint": "你的切入角度（例如：從使用者體驗角度、從技術可行性角度）",
  "actions": [
    {"type": "chat_message", "content": "你要在聊天室說的話"},
    {"type": "create_note", "text": "簡潔洞察（≤25字）", "color": "yellow", "position": "cluster:c1"},
    {"type": "move_note", "note_id": "n4", "to": "cluster:c2"},
    {"type": "arrange_notes", "note_ids": ["n1","n3","n7"], "layout": "grid", "target_region": "top-left", "label": "主題名"},
    {"type": "tidy_area", "scope": "all", "strategy": "align_grid"}
  ]
}

【白板工具】
感知工具（白板資訊已自動注入，需要更多細節時可呼叫）：
- get_canvas_summary：取得白板概況（叢集、有序度、空閒區域）
- get_canvas_snapshot：取得白板完整狀態（含每張便條紙詳細資訊）
- get_note_detail(note_id)：查看單張便條紙的詳細資訊

操作工具：
- create_note(text, color?, position)：新增便條紙。position 格式："near:n7" / "grid:3,1" / "region:bottom-right" / "cluster:c2"
- move_note(note_id, to, direction?, spacing?)：移動便條紙。to 格式同 position
- arrange_notes(note_ids, layout, target_region, columns?, spacing?, label?)：批次整理。layout: grid/horizontal/vertical/circular
- swap_notes(note_id_a, note_id_b)：交換兩張便條紙位置
- tidy_area(scope, target?, strategy?)：局部/全域清理。scope: cluster/region/all，strategy: align_grid/spread_even/compact

共通規則：
- 如果最近聊天中有人問你問題，你的 chat_message 必須直接回答那個問題
- 如果 Supervisor/主持人要求停止貼便條紙或整理白板，你必須服從，只回 chat_message
- create_note 的 color 可選：yellow、blue、green、red、orange、violet
- 支援的 action types：chat_message、create_note、move_note、edit_note、delete_note、arrange_notes、swap_notes、tidy_area、no_action
- reasoning 請簡短，把 token 留給 actions
- 只回應 JSON，不要包含任何其他文字。\
"""

_RESPONSE_RULES_DIVERGE = """\
行為規則（發散階段）：
- 便條紙是核心產出。每次回應必須包含至少一個 create_note
- 便條紙內容必須簡潔，不超過 25 個字。寫洞察，不寫句子
  ✓ 好的範例：「老年顧客彎腰取購物籃時腰痛」「店員補貨時購物車擋住走道」
  ✗ 壞的範例：「crew_1 在設計大賣場的購物車專案中遇到顧客在擺放商品時找不到支架，感覺無助」
- chat_message 是輔助，簡短說明你的想法即可（1-2 句）
- 你的便條紙內容必須來自你的角色專長視角，而非只是回應聊天內容
- 先看白板上已有的便條紙和叢集資訊，如果已有類似觀點，你必須換一個完全不同的使用者角色或場景
- 禁止只是附和或微幅延伸已有觀點——帶入全新的面向
- 貼便條紙時參考白板的空閒區域和叢集位置，用 position 參數指定合理位置\
"""

_RESPONSE_RULES_CONVERGE = """\
行為規則（收斂階段）：
- 每次回應必須包含至少一個 chat_message
- chat_message 應回應最近聊天中的討論，推動共識或提出結構化建議
- 不要新增大量便條紙，專注在 move_note、arrange_notes、edit_note 操作
- 先看白板上已有的便條紙和叢集內容避免重複
- 白板有序度低時，考慮使用 arrange_notes 或 tidy_area 整理\
"""

_DIVERGE_PHASES = frozenset(("1.1", "1.2", "3.1"))
_DIVERGE_STAGES = frozenset(("discover", "develop"))


def _get_response_format(context: dict) -> str:
    """Return the response format instruction with phase-appropriate rules."""
    micro_phase = context.get("current_micro_phase")
    stage = context.get("current_stage", "discover")

    if micro_phase and micro_phase in _DIVERGE_PHASES:
        is_diverge = True
    elif not micro_phase and stage in _DIVERGE_STAGES:
        is_diverge = True
    else:
        is_diverge = False

    rules = _RESPONSE_RULES_DIVERGE if is_diverge else _RESPONSE_RULES_CONVERGE
    return f"{_RESPONSE_FORMAT_BASE}\n\n{rules}"


def _is_all_ai(context: dict) -> bool:
    """Return True if every seat is occupied by an AI (no humans present)."""
    seats: list[dict] = context.get("seats", [])
    if not seats:
        return False
    return all(s.get("type") == "ai" for s in seats)


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

        # Layer 2 — role (Crew gets base + capability prompt based on seat_role)
        phase_strategy = context.get("phase_strategy")
        if is_supervisor:
            system_parts.append(SUPERVISOR_ROLE_PROMPT)
            # Supervisor mode prompt based on phase_strategy
            if phase_strategy:
                sup_mode = phase_strategy.get("supervisor_mode", "participant")
                if sup_mode == "facilitator":
                    system_parts.append(SUPERVISOR_FACILITATOR_RULES)
                elif sup_mode == "silent":
                    system_parts.append(SUPERVISOR_SILENT_RULES)
                else:  # "participant" (default)
                    system_parts.append(SUPERVISOR_DISCUSSION_RULES)
        else:
            seat_role = str(role).lower()
            system_parts.append(CREW_ROLE_BASE_PROMPT)
            # Phase 19: prefer per-project persona prompt over legacy capability
            my_persona_payload = context.get("my_persona")
            persona_prompt = render_persona_prompt(my_persona_payload)
            if persona_prompt:
                system_parts.append(persona_prompt)
            else:
                capability_prompt = CREW_CAPABILITY_PROMPTS.get(seat_role)
                if capability_prompt:
                    system_parts.append(capability_prompt)

        # Layer 3 — stage strategy (micro-phase aware v2.0)
        micro_phase = context.get("current_micro_phase")
        if micro_phase:
            from app.agents.prompts.micro_phase_prompts import (
                MICRO_PHASE_SUPERVISOR_PROMPTS,
                MICRO_PHASE_LENS_OVERRIDES,
                MICRO_PHASE_CREW_OVERRIDES,
                ARTIFACT_CONSTRUCTION_GUIDES,
                PROTAGONIST_BOOST,
                SUPPRESSED_CONSTRAINT,
            )
            # Base direction (same for supervisor and crew)
            stage_prompt = MICRO_PHASE_SUPERVISOR_PROMPTS.get(micro_phase, "")
            # Lens-specific override (Phase 19): resolved via persona dominant lens
            seat_role = context.get("my_seat", "")
            crew_override = ""
            my_persona = (
                persona_from_dict(context.get("my_persona"))
                if not is_supervisor
                else None
            )
            if my_persona is not None:
                lens_value = my_persona.dominant_lens().value
                crew_override = MICRO_PHASE_LENS_OVERRIDES.get(
                    micro_phase, {}
                ).get(lens_value, "")
            if not crew_override:
                # Legacy fallback: look up by crew_X seat_role
                crew_override = MICRO_PHASE_CREW_OVERRIDES.get(
                    micro_phase, {}
                ).get(seat_role, "")
            if crew_override:
                stage_prompt += f"\n\n你的本步驟職責：{crew_override}"
            # Artifact guide
            artifact_guide = ARTIFACT_CONSTRUCTION_GUIDES.get(micro_phase, "")
            if artifact_guide:
                stage_prompt += f"\n\n{artifact_guide}"
            # Role dynamics overlay
            role_status = context.get("my_role_status", "normal")
            if role_status == "protagonist":
                stage_prompt += f"\n\n{PROTAGONIST_BOOST}"
            elif role_status == "suppressed":
                stage_prompt += f"\n\n{SUPPRESSED_CONSTRAINT.format(forbidden_behaviors=crew_override)}"
            # Phase-specific note creation strategy
            _DIVERGE_PHASES = frozenset(("1.1", "1.2", "3.1"))
            _CONVERGE_PHASES = frozenset(("1.3", "2.3", "3.2", "3.3"))
            if micro_phase in _DIVERGE_PHASES:
                stage_prompt += (
                    "\n\n⚠️ 本步驟的核心產出是便條紙。每次發言時盡量搭配一張便條紙，"
                    "把想法具體化到白板上。聊天是輔助，便條紙才是成果。"
                )
            elif micro_phase in _CONVERGE_PHASES:
                stage_prompt += (
                    "\n\n⚠️ 本步驟以整理和分群為主。不要新增大量便條紙，"
                    "專注在 move_note 和 arrange_notes 操作。"
                )
        else:
            from app.agents.prompts.stages import STAGE_PROMPTS as _STAGE_PROMPTS_FALLBACK
            # Fallback: old discover sub-phase prompts for supervisor, generic for crew
            if stage == "discover" and is_supervisor:
                canvas = context.get("canvas_state", {})
                chat = context.get("recent_chat", [])
                duration = context.get("stage_duration_minutes", 0)
                subphase = determine_discover_subphase(canvas, chat, duration)
                stage_prompt = DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS[subphase]
            else:
                stage_prompt = _STAGE_PROMPTS_FALLBACK.get(stage, _STAGE_PROMPTS_FALLBACK["discover"])
        system_parts.append(stage_prompt)

        # Communication goal prompt (Phase 13)
        if phase_strategy:
            comm_goal = phase_strategy.get("comm_goal", "")
            comm_goal_prompt = COMM_GOAL_PROMPTS.get(comm_goal)
            if comm_goal_prompt:
                system_parts.append(comm_goal_prompt)
            # Peer interaction prompt — for all agents (including Supervisor)
            system_parts.append(PEER_INTERACTION_PROMPT)

        # Blackboard coordination rules (only when data available)
        blackboard = context.get("blackboard", {})
        has_blackboard = (
            blackboard
            and (
                blackboard.get("other_agent_intentions")
                or blackboard.get("topic_saturation")
            )
        )
        if has_blackboard:
            system_parts.append(BLACKBOARD_COORDINATION_RULES)

        # Supervisor-only: set_directive capability prompt
        if is_supervisor and has_blackboard:
            system_parts.append(SUPERVISOR_DIRECTIVE_PROMPT)

        # Full AI mode appendix
        if _is_all_ai(context):
            system_parts.append(FULL_AI_MODE_PROMPT)

        # Response format instruction (diverge vs converge aware)
        system_parts.append(_get_response_format(context))

        system_message = "\n\n".join(system_parts)

        # Interpolate crew name placeholders with actual display names
        from app.agents.prompts.interpolation import interpolate_crew_names
        seats = context.get("seats", [])
        system_message = interpolate_crew_names(system_message, seats)

        # Layer 4 — context buffer as user message
        context_description = build_context_description(context)
        user_message = (
            f"以下是目前的工作坊狀態，請根據這些資訊決定你的下一步行動：\n\n"
            f"{context_description}"
        )

        # Force canvas organization when Rule X triggers (Phase 15)
        if context.get("_force_canvas_organize"):
            user_message = (
                "⚠️ 系統偵測到白板凌亂度過高，你必須優先執行白板整理。\n"
                "請依照以下步驟行動：\n"
                "1. 先發一條 chat_message 告知團隊你要整理白板\n"
                "2. 執行 tidy_area(scope=\"all\", strategy=\"align_grid\") 消除重疊\n"
                "3. 如果有未分群的便條紙，執行 arrange_notes 分群\n"
                "禁止只發 chat_message 而不執行整理工具。\n\n"
                + user_message
            )

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
