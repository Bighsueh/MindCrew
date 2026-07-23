from __future__ import annotations

import logging

from app.agents.prompts.base import BASE_PERSONA_PROMPT, FULL_AI_MODE_PROMPT
from app.agents.prompts.blackboard_rules import (
    BLACKBOARD_COORDINATION_RULES,
    SUPERVISOR_DIRECTIVE_PROMPT,
    SUPERVISOR_INVITE_HUMAN_FACILITATOR,
    SUPERVISOR_INVITE_HUMAN_PARTICIPANT,
)
from app.agents.prompts.comm_goal import COMM_GOAL_PROMPTS
from app.agents.prompts.context_serializer import build_context_description
from app.agents.prompts.progression_rules import SUPERVISOR_PROGRESSION_PROMPT
from app.agents.prompts.discover_subphase import (
    DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS,
    determine_discover_subphase,
)
from app.agents.prompts.roles import (
    CREW_CAPABILITY_PROMPTS,
    CREW_CONDUCT_RULES,
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
  "reasoning": "一句話思考（≤20字）",
  "focus_topic": "聚焦主題（≤10字）",
  "viewpoint": "切入角度（≤10字，如：UX角度／技術角度）",
  "actions": [
    {"type": "chat_message", "content": "你要在聊天室說的話"},
    {"type": "create_note", "text": "簡潔洞察（≤25字）", "group_id": "顧客"},
    {"type": "create_note", "text": "顧客（主題群）", "kind": "label", "position": "group:顧客", "group_id": "顧客"},
    {"type": "create_note", "text": "通勤族 需要 出門不用想就帶到袋子，因為 想到時已在店裡", "cites": ["n12","n7"]},
    {"type": "create_note", "text": "我們可以怎麼讓袋子在出門那一刻自己出現在手邊？", "position": "section:【白板動態區】列的實際區id", "cites": ["n12"]},
    {"type": "move_note", "note_id": "n4", "to": "group:顧客", "group_id": "顧客", "reason": "把這張搬到顧客群，因為它其實在講同一件事"},
    {"type": "arrange_notes", "note_ids": ["n1","n3","n7"], "label": "主題名", "group_id": "痛點群A", "reason": "這三張是同一類痛點，聚成一群"},
    {"type": "tidy_area", "scope": "group", "target": "痛點群A", "reason": "把這一群收攏對齊，讓大家看得清楚"}
  ]
}

【白板工具】
感知工具（白板資訊已自動注入，需要更多細節時可呼叫）：
- get_canvas_summary：取得白板概況（叢集、有序度、空閒區域）
- get_canvas_snapshot：取得白板完整狀態（含每張便條紙詳細資訊）
- get_note_detail(note_id)：查看單張便條紙的詳細資訊

操作工具（位置參數＝語意意圖，實際座標、避開重疊一律由系統計算——**永遠不要自己輸出任何座標數字**）：
- create_note(text, position?, group_id?, kind?, cites?)：新增便條紙。position 只有三種："group:<群名>"（貼進某主題群）/ "near:<便條id>"（貼在某張旁邊）/ "section:<區id>"（貼進某個區——**區id 一定要從【白板動態區】那段複製那串以 `sec_` 開頭的實際 id，不可自己編、不可拿區的中文標題當 id**）；**不確定就不要填 position，系統會自動放到目前這面牆的空位**。group_id：接話式時同一個對象/主題的概念帶同一個群名（系統自動把同群擺一起）。kind："label" 為分類標籤便條（下標題，通常 Supervisor 貼），其餘為 content。cites：引用的便條 id 清單（問題定義引用痛點、設計題目引用問題定義、選定理由引用準則等）——id 從上面白板狀態的「[n..]」複製；系統在背後記引用關聯（不顯示給使用者）。
- move_note(note_id, to, direction?, spacing?, group_id?)：移動便條紙。to 格式同 position（group:/near:/section:）。group_id：搬到哪個主題群就帶哪個群名（事後歸群，讓你下次讀到正確分群）。
- arrange_notes(note_ids, label?, group_id?)：把幾張便條紙併成一群（可附群標籤；排法與位置由系統就地計算）。group_id：整批歸到同一主題群時帶上群名。
- swap_notes(note_id_a, note_id_b)：交換兩張便條紙位置
- tidy_area(scope, target?)：收攏對齊。scope 用 "group"（單一主題群，target=群名）——一次只整理一小撮，不要整面重排

共通規則：
- 如果最近聊天中有人問你問題，你的 chat_message 必須直接回答那個問題
- 如果 Supervisor/主持人要求停止貼便條紙或整理白板，你必須服從，只回 chat_message
- 便條紙的顏色由系統依作者自動決定，**不要指定顏色**。
- 【Spec 27 接話式】若在接話式（threaded）模式，create_note **必須帶** `group_id`（同一個對象/主題同一群，如顧客一群、店員一群）。**先看上面白板狀態裡每張便條標的「群 X」：講同一個對象就沿用那個既有 group_id，只有新對象才開新群名**——千萬別同一對象用兩個不同群名。便條只放沉澱後的「概念」，不是逐字對白或問句，也**不要重複貼同一個概念**。
- 【Spec 27 先說再做】要 move_note / arrange_notes / tidy_area 時，請在同一批 actions 裡**先放一個 chat_message 用白話說明原因**，再放搬動動作（教學透明）；只在收斂階段才整理便條，沒把握就先不要搬。
- 支援的 action types：chat_message、create_note、move_note、edit_note、delete_note、arrange_notes、swap_notes、tidy_area、no_action
- reasoning / focus_topic / viewpoint 都務必精簡（各一句以內），把 token 留給 actions；不要長篇推理
- 只回應 JSON，不要包含任何其他文字。\
"""

_RESPONSE_RULES_DIVERGE = """\
行為規則（發散階段）：
- 便條紙是核心產出。每次回應必須包含至少一個 create_note
- 便條紙內容必須簡潔，不超過 25 個字。寫洞察，不寫句子
  好的範例：「老年顧客彎腰取購物籃時腰痛」「店員補貨時購物車擋住走道」
  壞的範例：「crew_1 在設計大賣場的購物車專案中遇到顧客在擺放商品時找不到支架，感覺無助」
- chat_message 是輔助，簡短說明你的想法即可（1-2 句）
- 你的便條紙內容必須來自你的角色專長視角，而非只是回應聊天內容
- 先看白板上已有的便條紙和叢集資訊，如果已有類似觀點，你必須換一個完全不同的使用者角色或場景
- 禁止只是附和或微幅延伸已有觀點——帶入全新的面向
- 貼便條紙不用管位置——想掛在某個主題群就帶 group_id，其他情況不填 position，系統會放到目前這面牆的空位\
"""

_RESPONSE_RULES_CONVERGE = """\
行為規則（收斂階段）：
- 每次回應必須包含至少一個 chat_message
- chat_message 應回應最近聊天中的討論，推動共識或提出結構化建議
- 不要新增大量便條紙，專注在 move_note、arrange_notes、edit_note 操作
- 先看白板上已有的便條紙和叢集內容避免重複
- 白板有序度低時，考慮使用 arrange_notes 或 tidy_area 整理\
"""

_DIVERGE_STAGES = frozenset(("discover",))


def _get_response_format(context: dict) -> str:
    """Return the response format instruction with phase-appropriate rules."""
    from app.stages.phase_intent import get_phase_intent
    micro_phase = context.get("current_micro_phase")
    stage = context.get("current_stage", "discover")

    if micro_phase and get_phase_intent(micro_phase) == "divergent":
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


def _has_human_seat(context: dict) -> bool:
    """Phase 28：判斷專案內是否有人類成員席位（type=human / occupant_type=human）。

    用於 supervisor 邀請人類成員 prompt fragment 的條件注入：
    無人類席位則整個 invite-human 段不需出現（避免 LLM 對著空對象嘗試 cue）。
    """
    for s in context.get("seats") or []:
        occ = (s.get("type") or s.get("occupant_type") or "").lower()
        if occ == "human":
            return True
    return False


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
            # Spec 14: 若 supervisor persona router 已決定 A/B persona，
            # 用 persona base + intervention templates 取代既有 mode rules
            persona_invocation = context.get("_supervisor_persona_invocation")
            if persona_invocation:
                system_parts.append(persona_invocation.base_prompt)
                if persona_invocation.interventions_block:
                    system_parts.append(
                        "## 本回合觸發的介入：\n"
                        + persona_invocation.interventions_block
                    )
            else:
                # Fall through: 既有 supervisor_mode（facilitator/participant/silent）
                system_parts.append(SUPERVISOR_ROLE_PROMPT)
                if phase_strategy:
                    sup_mode = phase_strategy.get("supervisor_mode", "participant")
                    if sup_mode == "facilitator":
                        system_parts.append(SUPERVISOR_FACILITATOR_RULES)
                    elif sup_mode == "silent":
                        system_parts.append(SUPERVISOR_SILENT_RULES)
                    else:  # "participant" (default)
                        system_parts.append(SUPERVISOR_DISCUSSION_RULES)
            # Spec 27 (Phase 36)：標籤/糾錯 + 整理先說再做（兩條 persona 路徑共用）
            from app.agents.prompts.note_posting_rules import (
                SUPERVISOR_LABEL_AND_MISPLACEMENT_RULE,
                SUPERVISOR_MOVE_AND_SWITCH_RULE,
            )
            _sub = str(context.get("current_sub_phase") or "")
            # Phase 42 B2 裁定：0.0a 暖場不分群、不整理——spec 27 的標籤/搬移指令
            # 在暖場是雜訊（與「不分群」矛盾），跳過注入。
            if _sub != "0.0a":
                system_parts.append(SUPERVISOR_LABEL_AND_MISPLACEMENT_RULE)
                system_parts.append(SUPERVISOR_MOVE_AND_SWITCH_RULE)
            # Phase 38 (spec/28)：暖場 0.0a → 組長 MC 主持目標導向破冰遊戲。
            # （Phase 42 C1：舊 0.1/0.2 入口的向下相容注入隨格移除——migration 已
            #   把停在 0.x 的舊專案 backfill 到 1.1a，spec 22 v2.0 §11.1。）
            if _sub == "0.0a":
                from app.agents.prompts.warmup_game import (
                    pick_item,
                    render_warmup_mc_prompt,
                )

                _item = pick_item(context.get("project_id") or "")
                system_parts.append(render_warmup_mc_prompt(_item))
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
                # Spec 17 §5（v2.2）：legacy fallback 路徑同樣附加行為規範段——
                # 行為契約不因資料新舊而豁免（persona 路徑由 render_persona_prompt 內建）。
                system_parts.append(CREW_CONDUCT_RULES)
            # Phase 38 (spec/28)：暖場 0.0a → AI 隊友當「樂隊」有節制接話（被邀才接、最妙留給人）。
            if str(context.get("current_sub_phase") or "") == "0.0a":
                from app.agents.prompts.warmup_game import (
                    pick_item,
                    render_warmup_band_prompt,
                )

                _item = pick_item(context.get("project_id") or "")
                system_parts.append(render_warmup_band_prompt(_item))

        # Phase 28：在 Layer 2 (role) 結束、Layer 3 (stage) 開始前，注入當前
        # turn-taking policy 的中文段落，告知 LLM 本回合的輪流規則。
        # controller 在 base_agent._decision_cycle 內塞入 context["_turn_controller"]。
        turn_controller = context.get("_turn_controller")
        if turn_controller is not None:
            try:
                # 傳 context：讓 cued 對「本回合已開放發言的 crew」給主動分享許可、
                # 而非一律沉默（crew-silence 修，盲測 2026-06-09）。
                system_parts.append(turn_controller.system_prompt_fragment(context))
            except Exception:
                pass

        # Layer 3 — stage strategy
        # Spec 13: sub_phase 優先；無 sub_phase 時 fallback 到 micro_phase
        # ⚠️ Phase 42 D4：current_sub_phase（5＋7，sub_phase_prompts）為 canonical 真理；
        # 下方 micro_phase 分支為 LEGACY 粗粒度安全網（舊 6 桶，含 Persona/HMW 舊概念），
        # 正常運作 sub_phase 恆有值不會走到。詳見 micro_phase_prompts.py 模組 docstring。
        sub_phase = context.get("current_sub_phase")
        _stage_prompt_already_appended = False
        if sub_phase:
            from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt
            # Phase 42 B2（spec 04-03 §3）：分角色注入——組長拿共用守則＋進場語，
            # crew 拿行為要點。
            stage_prompt = build_sub_phase_prompt(
                sub_phase, role="supervisor" if is_supervisor else "crew"
            )
            system_parts.append(stage_prompt)
            _stage_prompt_already_appended = True
            micro_phase = None
        else:
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
            # Phase-specific note creation strategy + time pressure overlay
            from app.stages.phase_intent import get_phase_intent
            phase_intent_value = get_phase_intent(micro_phase)
            if phase_intent_value == "divergent":
                stage_prompt += (
                    "\n\n注意：本步驟的核心產出是便條紙。每次發言時盡量搭配一張便條紙，"
                    "把想法具體化到白板上。聊天是輔助，便條紙才是成果。"
                )
            elif phase_intent_value == "convergent":
                stage_prompt += (
                    "\n\n注意：本步驟以整理和分群為主。不要新增大量便條紙，"
                    "專注在 move_note 和 arrange_notes 操作。"
                )

            # ：tight / critical 等級時，
            # 不論本來 protagonist_lens 是誰，都強制注入收斂/取捨 directive。
            # Phase 35 (spec/16 §6.5.4)：僅 divergent 階段注入，避免 convergent /
            # transitional 階段與既有收斂 stage_prompt 形成雙重壓力。
            pressure_level = context.get("time_pressure_level")
            if pressure_level in ("tight", "critical") and phase_intent_value == "divergent":
                from app.timer.pressure import pressure_directive
                directive = pressure_directive(pressure_level, phase_intent_value)
                if directive:
                    stage_prompt += f"\n\n【時間壓力指令】{directive}"
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
        if not _stage_prompt_already_appended:
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

        # Phase 42 A1（spec 04-03 §3.0.5）：組長推進迴路——supervisor 恆注入
        # （不受 turn policy / blackboard 有無影響）；crew 不注入。
        if is_supervisor:
            system_parts.append(SUPERVISOR_PROGRESSION_PROMPT)
            # Phase 42 A3（spec 04-03 §3.0.7，#34）：便條指認高亮——同樣恆注入。
            from app.agents.prompts.user_signals import (
                SUPERVISOR_NOTE_HIGHLIGHT_PROMPT,
            )

            system_parts.append(SUPERVISOR_NOTE_HIGHLIGHT_PROMPT)

        # Supervisor-only: set_directive capability prompt
        # Phase 28：非 Cued 模式不教 supervisor 用 set_directive，避免引導出
        # 會被 act.py 直接 reject 的 directive 動作 (浪費 token + 製造混亂)。
        from app.agents.turn_controller import TurnPolicy as _TurnPolicy
        _controller = context.get("_turn_controller")
        _is_cued = _controller is None or _controller.policy == _TurnPolicy.CUED
        # Phase 42（1.1a 隊友沉默修復）：1.1a 是「逐一邀請」關，組長一開場就要用
        # set_directive 點名隊友分享；但此時 blackboard 常還空（無 intentions/saturation）
        # → has_blackboard=False → 過去不注入 directive 能力 prompt、組長不知道能
        # set_directive（@-mention 雖有 cued_mention_override fallback 仍較弱）。故 1.1a
        # 不論 blackboard 有無都注入。0.0a 已有自己的 MC 腳本、不在此放寬。
        _invite_loop_phase = context.get("current_sub_phase") == "1.1a"
        if is_supervisor and _is_cued and (has_blackboard or _invite_loop_phase):
            system_parts.append(SUPERVISOR_DIRECTIVE_PROMPT)
            # B5：依 supervisor_mode 條件追加邀請人類 fragment
            # silent mode 完全不附加（spec 15 §4.1：維持靜默語意，學生需 raise-hand）
            if _has_human_seat(context):
                mode = (context.get("supervisor_mode") or "facilitator").lower()
                if mode == "facilitator":
                    system_parts.append(SUPERVISOR_INVITE_HUMAN_FACILITATOR)
                elif mode == "participant":
                    system_parts.append(SUPERVISOR_INVITE_HUMAN_PARTICIPANT)

        # Full AI mode appendix
        if _is_all_ai(context):
            system_parts.append(FULL_AI_MODE_PROMPT)

        # Response format instruction (diverge vs converge aware)
        system_parts.append(_get_response_format(context))

        system_message = "\n\n".join(system_parts)

        # Interpolate crew name placeholders with actual display names
        from app.agents.prompts.interpolation import (
            interpolate_crew_names,
            interpolate_human_name,
        )
        seats = context.get("seats", [])
        system_message = interpolate_crew_names(system_message, seats)
        # Phase 42 B2（守則 6，#15）：@{name}/@{顯示名} → 真人顯示名，讓邀請範例帶真名。
        # 不開 include_bare_seat_id——system prompt 裡的 human_creator 是 invited_speaker
        # 機器路由教學，必須保留 seat id。
        system_message = interpolate_human_name(system_message, seats)

        # Layer 4 — context buffer as user message
        context_description = build_context_description(context)
        user_message = (
            f"以下是目前的工作坊狀態，請根據這些資訊決定你的下一步行動：\n\n"
            f"{context_description}"
        )

        # Force canvas organization when Rule X triggers (Phase 15)
        # spec 27 §7 鐵律：永不整面重排——只教「挑一群、收一群」的逐撮整理。
        if context.get("_force_canvas_organize"):
            user_message = (
                "注意：系統偵測到白板凌亂度過高，你必須優先整理白板（一小撮一小撮，"
                "不要整面重排）。\n"
                "請依照以下步驟行動：\n"
                "1. 先發一條 chat_message 用白話說明你要整理哪一群、為什麼\n"
                "2. 挑最亂的一個主題群，執行 tidy_area(scope=\"group\", target=\"該群名\") 收攏它\n"
                "3. 如果有幾張明顯同類但未分群的便條紙，用 arrange_notes 把那幾張併成一群\n"
                "禁止只發 chat_message 而不執行整理工具。\n\n"
                + user_message
            )

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
