from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.agents.turn_controller import TurnController, TurnPolicy
from app.chinese.converter import chinese_converter
from app.db.models.agent_decision_trace import AgentDecisionTrace
from app.db.models.message import Message
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent, CueEvent, TurnStateEvent

logger = logging.getLogger(__name__)

# Action types that crew agents are forbidden to execute
# Phase 42 A1：advance_sub_phase＝組長宣布推進（spec 04-06 §5.8；handler 在
# act_progression.py）。advance_stage 為舊白名單殘項（無 handler），保留擋 crew。
_SUPERVISOR_ONLY_ACTIONS = {
    "advance_stage", "set_directive", "advance_sub_phase",
    # Phase 42 A3（WP7）：任務提示與便條指認高亮——組長專屬（handler 在 act_signals.py）。
    "set_user_task", "note_highlight",
    # Phase 42 C0（spec 10 v2.0 §5.9）：動態開區是組長的進場／引導行為（#32）。
    "open_section",
}

# Phase 42 A2：純協調動作不計入回合鎖的「crew 實質輸出」ledger（spec 20 §11.2）。
# 其餘（chat_message / create_note / move_note 等內容貢獻）每 crew 每回合計 1 次。
_NON_SUBSTANTIVE_ROUND_TYPES = frozenset({
    "no_action", "set_directive", "advance_sub_phase", "advance_stage",
    "advance_micro_phase", "pass", "set_user_task", "note_highlight",
    # Phase 42 C0：開區是版面協調動作，非內容貢獻（C0 裁定，spec 20 §11.2 精神）。
    "open_section",
})


def _is_human_seat(seats: list[dict] | None, seat_role: str) -> bool:
    """檢查 seats context 中 seat_role 對應的席位是否為人類佔據。

    Phase 28 cue-human：set_directive 寫入 invited_speaker=human 時，
    act.py 需據此判斷是否啟動 cue_timeout_watcher（B4）。
    """
    if not seats or not seat_role:
        return False
    target = seat_role.lower()
    for s in seats:
        role = (s.get("role") or s.get("seat_role") or "").lower()
        if role != target:
            continue
        occ = (s.get("type") or s.get("occupant_type") or "").lower()
        return occ == "human"
    return False


async def _is_in_cooldown(project_id: UUID, seat_role: str) -> bool:
    """B7：檢查 (project, seat) 是否在 abandon 後的 cooldown 期內。"""
    try:
        import redis.asyncio as aioredis

        from app.agents.cue_timeout_watcher import _cue_cooldown_key
        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            value = await r.get(_cue_cooldown_key(project_id, seat_role))
        finally:
            await r.aclose()
        return value is not None
    except Exception:
        logger.debug("_is_in_cooldown check failed", exc_info=True)
        return False


async def _revert_invited_speaker(project_id: UUID, from_seat_role: str) -> None:
    """B7：cooldown guard 觸發後，把已寫入的 invited_speaker 清掉。"""
    try:
        from app.agents.blackboard import BlackboardManager
        from app.agents.blackboard_schemas import CoordinationDirective

        bb = BlackboardManager(
            project_id=project_id,
            agent_id=from_seat_role,
            seat_role=from_seat_role,
        )
        existing = await bb.read_coordination_directive()
        if existing is None:
            return
        cleared = CoordinationDirective(
            round_type=existing.round_type,
            focus_topic=existing.focus_topic,
            invited_speaker=None,
            instruction=existing.instruction,
        )
        await bb.write_coordination_directive(cleared)
    except Exception:
        logger.debug("_revert_invited_speaker failed", exc_info=True)


async def _load_cue_params(project_id: UUID) -> tuple[int, int]:
    """讀取 project.cue_timeout_seconds / cue_max_retries。

    回傳 (timeout_seconds, max_retries)；project 不存在或欄位缺失時用 Spec
    預設 (180, 5)。
    """
    try:
        from sqlalchemy import select

        from app.db.models.project import Project

        async with async_session_factory() as session:
            row = await session.execute(
                select(Project.cue_timeout_seconds, Project.cue_max_retries).where(
                    Project.id == project_id
                )
            )
            result = row.one_or_none()
        if result is None:
            return 180, 5
        return int(result[0] or 180), int(result[1] or 5)
    except Exception:
        logger.debug("_load_cue_params failed for %s", project_id, exc_info=True)
        return 180, 5


@dataclass
class ActResult:
    executed_actions: list[dict] = field(default_factory=list)
    skipped_actions: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True


class ActEngine:
    """Execute validated agent actions.

    Execution order: chat_message first, canvas ops second (spec §2.5).
    2–5s random delay between actions.
    """

    def __init__(
        self,
        project_id: UUID,
        agent_id: str,
        seat_role: str,
        agent_name: str,
        is_supervisor: bool = False,
        owning_user_id: UUID | None = None,
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._agent_name = agent_name
        self._is_supervisor = is_supervisor
        # Spec 27 §4.3：傳給 create_note → content_gate，啟用 must_be_concept 的 LLM tier-2。
        self._owning_user_id = owning_user_id

    async def execute(
        self,
        actions: list[dict],
        current_stage: str,
        think_result: Any | None = None,
        assess_result: Any | None = None,
        micro_phase: str | None = None,
        role_status: str = "normal",
        sub_phase: str | None = None,
        comm_mode: str = "discussion",
        seats: list[dict] | None = None,
        controller: TurnController | None = None,
        context: dict | None = None,
    ) -> ActResult:
        """Execute a list of actions from the ThinkEngine.

        Steps:
        1. Validate legality
        2. Apply Chinese conversion (belt-and-suspenders)
        3. Sort: chat first, canvas second
        4. Execute each with 2-5s inter-action delay
        5. Record DecisionTrace to DB
        """
        result = ActResult()
        # Spec 27 P5: per-turn cap on gate/dedup rejection explanations surfaced to chat.
        self._gate_notices = 0
        # Phase 42 B2（守則 6，#15）：留給出站訊息插值用（@顯示名安全網）。
        self._seats = seats or []
        legal, illegal = self._validate_actions(
            actions, comm_mode=comm_mode, controller=controller
        )
        result.skipped_actions.extend(illegal)

        policy_value = controller.policy.value if controller else "cued"

        if not legal:
            result.success = len(illegal) == 0
            await self._save_trace(
                current_stage, assess_result, think_result, result,
                micro_phase=micro_phase, role_status=role_status,
                turn_policy=policy_value,
            )
            return result

        # Sort: chat_message first, then canvas ops
        chat_actions = [a for a in legal if a.get("type") == "chat_message"]
        canvas_actions = [a for a in legal if a.get("type") != "chat_message"]
        ordered = chat_actions + canvas_actions

        ctx_dict = context or {}

        for i, action in enumerate(ordered):
            if i > 0:
                delay = random.uniform(2.0, 5.0)
                await asyncio.sleep(delay)

            try:
                await self._execute_single(action, current_stage, sub_phase=sub_phase)
                result.executed_actions.append(action)
                # Phase 42 A2：crew 實質輸出計入回合鎖 ledger（spec 20 §11.2）。
                # 組長不佔配額（is_supervisor 跳過，凍結期仍可引導，§11.6）。
                if (
                    not self._is_supervisor
                    and sub_phase
                    and action.get("type") not in _NON_SUBSTANTIVE_ROUND_TYPES
                ):
                    try:
                        from app.agents.round_lock import mark_crew_output

                        await mark_crew_output(
                            self._project_id, sub_phase, self._seat_role
                        )
                    except Exception:
                        logger.debug("mark_crew_output hook failed", exc_info=True)
                # Fix #1: supervisor 點名 crew 後設 awaiting-reply 鎖
                if (
                    self._is_supervisor
                    and action.get("type") == "chat_message"
                    and seats
                ):
                    await self._maybe_set_awaiting_reply(action, seats)
                # Phase 28：set_directive 成功後 emit cue event 給前端通知被點名者。
                if (
                    action.get("type") == "set_directive"
                    and action.get("invited_speaker")
                    and controller is not None
                    and controller.policy == TurnPolicy.CUED
                ):
                    invited = str(action["invited_speaker"])
                    # B7：cooldown guard — abandon 後 300s 內 supervisor 不該 cue 同一人類席位。
                    # _execute_single 已寫入 blackboard → 此處需 revert（清掉 invited_speaker）。
                    if _is_human_seat(seats, invited) and await _is_in_cooldown(
                        self._project_id, invited
                    ):
                        logger.info(
                            "cue cooldown guard: revert directive project=%s seat=%s",
                            self._project_id, invited,
                        )
                        await _revert_invited_speaker(
                            self._project_id, self._seat_role
                        )
                        continue
                    await self._emit_cue_event(invited_speaker=invited)
                    # B4：target 為人類席位 → 啟動 cue timeout watcher。
                    # AI 席位不啟動（既有 awaiting_reply lock 已處理 supervisor 等待）。
                    if _is_human_seat(seats, invited):
                        try:
                            from app.agents.cue_timeout_watcher import (
                                start_cue_timeout_watcher,
                            )

                            timeout_s, max_retries = await _load_cue_params(
                                self._project_id
                            )
                            await start_cue_timeout_watcher(
                                project_id=self._project_id,
                                target_seat_role=invited,
                                from_seat_role=self._seat_role,
                                timeout_seconds=timeout_s,
                                max_retries=max_retries,
                            )
                        except Exception:
                            logger.exception(
                                "start_cue_timeout_watcher failed for %s seat=%s",
                                self._project_id, invited,
                            )
                        # Phase 42 A2：組長 cue 真人 = 宣布本輪結束 → 回合鎖凍結
                        # （即使 crew 未全輪過；與 cued 人類分支疊加，spec 20 §11.3/§2.2）。
                        if sub_phase:
                            try:
                                from app.agents.round_lock import declare_round_end

                                await declare_round_end(self._project_id, sub_phase)
                            except Exception:
                                logger.debug(
                                    "declare_round_end hook failed", exc_info=True
                                )
                    # Phase 42（1.1a 隊友沉默修復）：crew 被點名分享「不」凍結回合（上面
                    # human 分支才 declare_round_end）。邀請次數累計改在 B13 trigger fire 時
                    # 統一記（triggers_b.py），以同時涵蓋 set_directive 與 @-mention 兩路徑、
                    # 不雙重計數——故此處不另外 bump。
                # Phase 28：chat_message 成功後通知 controller 推進輪流狀態，
                # 並廣播 turn_state 給前端 (RR 模式下 next_speaker 變動最關鍵)。
                if (
                    action.get("type") == "chat_message"
                    and controller is not None
                ):
                    await controller.on_speak(self._seat_role, ctx_dict)
                    if controller.policy == TurnPolicy.ROUND_ROBIN:
                        await self._emit_turn_state_event(controller, ctx_dict)
            except Exception as exc:
                logger.error(
                    "Action execution failed (type=%s): %s",
                    action.get("type"),
                    exc,
                )
                result.errors.append(str(exc))
                result.success = False

        await self._save_trace(
            current_stage, assess_result, think_result, result,
            micro_phase=micro_phase, role_status=role_status,
            turn_policy=policy_value,
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # Spec 13 — comm_mode action whitelist
    # Phase 41：移除 silent_write / silent_rearrange（沉默）兩種硬性動作禁制。
    # 移除後 AI crew 全階段皆可同時 chat_message + create_note；避免定錨 / 不重貼 / 收斂專注
    # 改由軟性護欄（反echo prompt + 去重 gate + 收斂 prompt 偏好）承載（Spec 27 v2.4）。
    # Phase 42 A1：advance_sub_phase 加入 reveal/threaded 白名單——組長在任何
    # comm_mode 都可宣布推進（supervisor-only 由 Layer 1 擋 crew）。
    # Phase 42 A3：set_user_task / note_highlight 加入 reveal/threaded 白名單——
    # 組長在任何 comm_mode 都可發任務提示與高亮（supervisor-only 由 Layer 1 擋 crew）。
    _COMM_MODE_ALLOWED: dict[str, frozenset[str]] = {
        "reveal_round": frozenset(
            {"chat_message", "create_note", "no_action", "advance_sub_phase",
             "set_user_task", "note_highlight"}
        ),
        # Spec 27：接話式 — 輪流發言（chat）+ create_note；聊天照常。
        "threaded_reveal": frozenset(
            {"chat_message", "create_note", "no_action", "advance_sub_phase",
             "set_user_task", "note_highlight"}
        ),
        "discussion": frozenset(),  # 空集 = 全部允許
    }

    def _validate_actions(
        self,
        actions: list[dict],
        comm_mode: str = "discussion",
        controller: TurnController | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Separate legal from illegal actions.

        Three layers:
          1. Crew cannot execute supervisor-only actions
          2. Spec 13 comm_mode action whitelist (reveal_round/threaded_reveal allow chat+create;
             discussion = no restriction. Phase 41: silent_write/silent_rearrange removed.)
          3. Phase 28：``set_directive`` 只在 Cued policy 下允許 (其他模式 reject + warning)
        """
        legal: list[dict] = []
        illegal: list[dict] = []
        allowed = self._COMM_MODE_ALLOWED.get(comm_mode, frozenset())
        for action in actions:
            action_type = action.get("type", "")

            # Layer 1: supervisor-only
            if not self._is_supervisor and action_type in _SUPERVISOR_ONLY_ACTIONS:
                logger.warning(
                    "Crew agent %s attempted supervisor-only action %s — blocked",
                    self._agent_id, action_type,
                )
                illegal.append({**action, "_blocked_reason": "crew不能執行supervisor-only動作"})
                continue

            # Layer 2: comm_mode whitelist (empty allowed = discussion = no restriction)
            if allowed and action_type not in allowed:
                logger.info(
                    "Agent %s action %s blocked by comm_mode=%s",
                    self._agent_id, action_type, comm_mode,
                )
                illegal.append({
                    **action,
                    "_blocked_reason": f"comm_mode={comm_mode} 不允許 {action_type}",
                })
                continue

            # Layer 3: Phase 28 — set_directive 是 Cued-only action
            if (
                action_type == "set_directive"
                and controller is not None
                and controller.policy != TurnPolicy.CUED
            ):
                logger.warning(
                    "Agent %s attempted set_directive under policy=%s — blocked",
                    self._agent_id, controller.policy.value,
                )
                illegal.append({
                    **action,
                    "_blocked_reason": (
                        f"set_directive 僅限 Cued 模式 (目前 policy="
                        f"{controller.policy.value})"
                    ),
                })
                continue

            legal.append(action)
        return legal, illegal

    async def _execute_single(
        self,
        action: dict,
        current_stage: str,
        sub_phase: str | None = None,
    ) -> None:
        """Dispatch a single action to the appropriate handler."""
        from app.agents.act_canvas import CANVAS_ACTION_TYPES, execute_canvas_tool

        action_type = action.get("type", "")
        content = action.get("content", "")

        # Ensure content is in Traditional Chinese
        if content:
            content = chinese_converter.convert(content)

        if action_type == "chat_message":
            # Phase 42 D2（WP9 #9）：act 層 per-action agent_typing start/stop，try/finally
            # 保證落地或放棄都發 stop（spec 06 §3.1 / 13 §6.4）。
            # 註：chat 的「決定→送出」窗極短、此層對 chat 多半不可見——**chat typing 可見性
            # 已由 option C（`base_agent._emit_round_typing`，think 前發 start）補足**（spec 13
            # §6.4 v1.2）；本層保留作落地/放棄的 stop 雙保險（canvas 動作的 start 另把回合層
            # 的 kind 細化為 canvas，前端 keyed by seatId 覆寫）。不在熱路徑加人工延遲偽造停頓。
            await self._emit_typing("chat", "start")
            try:
                # Safety-net: replace any remaining @{crew_N} template patterns；
                # Phase 42 B2（守則 6，#15）：學員不該看到 seat id——出站訊息把
                # human_creator / @{顯示名} 殘留改寫成真人顯示名。
                from app.agents.prompts.interpolation import (
                    interpolate_crew_names,
                    interpolate_human_name,
                )
                seats = getattr(self, "_seats", None)
                content = interpolate_crew_names(content, seats)
                content = interpolate_human_name(content, seats, include_bare_seat_id=True)
                await self._execute_chat_message(content, current_stage)
            finally:
                await self._emit_typing("chat", "stop")
        elif action_type in CANVAS_ACTION_TYPES:
            # Phase 42 D2（WP9 #9）：白板動作前發 agent_typing(kind=canvas)。
            await self._emit_typing("canvas", "start")
            try:
                canvas_result = await execute_canvas_tool(
                    op_type=action_type,
                    action=action,
                    project_id=self._project_id,
                    agent_id=self._agent_id,
                    agent_name=self._agent_name,
                    sub_phase_id=sub_phase,
                    seat_role=self._seat_role,
                    owning_user_id=self._owning_user_id,
                )
                # Spec 27 P5: don't silently drop gate/dedup rejections — explain in chat.
                await self._explain_canvas_rejection(canvas_result, current_stage)
            finally:
                await self._emit_typing("canvas", "stop")
        elif action_type == "set_directive":
            await self._execute_set_directive(action)
        elif action_type == "advance_sub_phase":
            # Phase 42 A1（spec 04-06 §5.8）：組長宣布推進——系統執行、硬 gate
            # 仍強制；未過以內容層 reason_zh 走 rejection 解釋通道回饋。
            from app.agents.act_progression import execute_advance_action

            advance_result = await execute_advance_action(
                project_id=self._project_id,
                agent_id=self._agent_id,
                current_sub_phase=sub_phase,
            )
            await self._explain_canvas_rejection(advance_result, current_stage)
        elif action_type == "set_user_task":
            # Phase 42 A3（spec 04-03 §2.3.2.1 守則 8 / 05 Flow 12）：任務提示。
            from app.agents.act_signals import execute_set_user_task

            await execute_set_user_task(
                project_id=self._project_id, action=action, sub_phase=sub_phase
            )
        elif action_type == "note_highlight":
            # Phase 42 A3（spec 04-03 §3.0.7，#34）：便條指認高亮。
            from app.agents.act_signals import execute_note_highlight

            await execute_note_highlight(
                project_id=self._project_id, action=action, seat_role=self._seat_role
            )
        elif action_type == "no_action":
            logger.debug("Agent %s chose no_action: %s", self._agent_id, action.get("reason", ""))
        else:
            logger.warning("Unknown action type: %s", action_type)

    async def _emit_typing(self, kind: str, state: str) -> None:
        """Phase 42 D2（WP9 #9）：發 agent_typing（best-effort，失敗不擋輸出）。"""
        from app.agents.act_signals import emit_agent_typing

        await emit_agent_typing(
            project_id=self._project_id,
            seat_id=self._seat_role,
            display_name=self._agent_name,
            kind=kind,
            state=state,
        )

    async def _explain_canvas_rejection(
        self, result: dict | None, stage: str
    ) -> None:
        """Surface a gate / dedup rejection to chat (Spec 27 P5 / §12 #8,#10).

        Previously a rejected note vanished silently (the ``execute_canvas_tool``
        return was discarded), so the human learner saw nothing. We make the
        reason visible instead. A true regenerate-on-rejection retry belongs to
        the think loop; here we only explain. Capped per turn to avoid flooding.
        """
        if not isinstance(result, dict) or result.get("success"):
            return
        rejection = result.get("rejection") or {}
        reason = rejection.get("reason_zh")
        if not reason:
            return
        from app.agents.act_canvas import MAX_GATE_REJECTION_NOTICES

        if getattr(self, "_gate_notices", 0) >= MAX_GATE_REJECTION_NOTICES:
            return
        self._gate_notices = getattr(self, "_gate_notices", 0) + 1
        await self._execute_chat_message(str(reason), stage)

    async def _maybe_set_awaiting_reply(
        self, action: dict, seats: list[dict]
    ) -> None:
        """Supervisor 發訊息若點名 crew，設 awaiting-reply 鎖（Fix #1）。"""
        content = str(action.get("content", ""))
        if not content:
            return
        try:
            from app.agents.supervisor.awaiting_reply import (
                detect_crew_mention,
                set_awaiting_reply,
            )
            mention = detect_crew_mention(content, seats)
            if mention is None:
                return
            seat_role, display_name = mention
            await set_awaiting_reply(self._project_id, seat_role, display_name)
            # A2（連發死房修）：組長 @ 點名 crew 時，同步寫 invited_speaker，讓被等的 crew 在
            # cued 下真的能發言。否則某些關卡（如 0.0a 暖場）cued 無 crew 放行機制（open-share
            # 空、_cued_open_seat/B13 只在 1.1a、chat @mention 不寫 invited_speaker）→ 被點名的
            # crew 動不了 → 組長乾等 awaiting-reply 鎖最久 120s＝死房。統一「@ 點名＝邀請」。
            # 只對 crew 席位（人類由 chat 回應、不需 invited_speaker）；non-cued policy 不讀
            # invited_speaker，寫了無害。crew 發言後 CuedPolicy.on_speak 會清掉 invited。
            if seat_role.lower().startswith("crew_"):
                try:
                    from app.agents.blackboard import BlackboardManager
                    from app.agents.blackboard_schemas import CoordinationDirective

                    bb = BlackboardManager(
                        project_id=self._project_id,
                        agent_id=self._agent_id,
                        seat_role=self._seat_role,
                    )
                    existing = await bb.read_coordination_directive()
                    if existing is not None:
                        directive = CoordinationDirective(
                            round_type=existing.round_type,
                            focus_topic=existing.focus_topic,
                            invited_speaker=seat_role,
                            instruction=existing.instruction,
                        )
                    else:
                        directive = CoordinationDirective(
                            invited_speaker=seat_role,
                            instruction=f"請 {display_name} 接著回應",
                        )
                    await bb.write_coordination_directive(directive)
                except Exception:
                    logger.debug("invite-on-mention directive write failed", exc_info=True)
        except Exception:
            logger.debug("set_awaiting_reply hook failed", exc_info=True)

    async def _is_recent_duplicate_supervisor_msg(self, content: str) -> bool:
        """供 supervisor：近窗內是否已發過實質相同的訊息（防內容洗版）。

        盲測 2026-06-09：組長「先把重疊便條清理…」「原始觀察便條寫法…」各重複多遍。以正規化後
        字集 Jaccard ≥ 0.7 比對近 150s 內自己發過的訊息；命中即跳過。Redis 失敗則放行（不擋正常
        發話）。只對 supervisor 生效，crew / 人類不受限。
        """
        norm = re.sub(r"[\s，。、！？!?,.~～「」『』（）()：:；;｜|]+", "", content)
        if len(norm) < 8:
            return False
        try:
            import redis.asyncio as aioredis

            from app.config import settings

            key = f"project:{self._project_id}:sup_recent_msgs"
            now = time.time()
            window = 150.0
            new_set = set(norm)
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                await r.zremrangebyscore(key, 0, now - window)
                for prev in await r.zrange(key, 0, -1):
                    ps = set(prev)
                    if ps and len(new_set & ps) / len(new_set | ps) >= 0.7:
                        return True
                await r.zadd(key, {norm[:80]: now})
                await r.expire(key, int(window) + 30)
            finally:
                await r.aclose()
        except Exception:
            return False
        return False

    async def _execute_chat_message(self, content: str, stage: str) -> None:
        """Publish ChatMessageEvent to EventBus and persist to DB."""
        if not content:
            return

        # supervisor 內容去重：近窗內實質相同的訊息不重發（防洗版）；crew / 人類不受限。
        if self._is_supervisor and await self._is_recent_duplicate_supervisor_msg(
            content
        ):
            logger.debug(
                "supervisor msg deduped (near-identical recent): %s", content[:24]
            )
            return

        event = ChatMessageEvent(
            project_id=self._project_id,
            sender_id=self._agent_id,
            sender_type="ai",
            sender_name=self._agent_name,
            content=content,
        )
        await event_bus.publish(event)

        # Update idle timestamp so Rule 5 detects AI activity in all-AI mode
        await self._update_last_event_ts()

        async with async_session_factory() as session:
            msg = Message(
                project_id=self._project_id,
                sender_type="ai",
                sender_id=self._agent_id,
                sender_name=self._agent_name,
                content=content,
                stage=stage,
            )
            session.add(msg)
            await session.commit()

        # Update conversation thread tracking
        try:
            from app.agents.conversation_state import ConversationStateTracker

            from app.agents.utils import load_seat_roles

            tracker = ConversationStateTracker(self._project_id)
            all_seats = await load_seat_roles(self._project_id)
            await tracker.update_on_message(self._agent_name, content, all_seats)
        except Exception as exc:
            logger.debug("Conversation state update failed: %s", exc)

        logger.debug(
            "Agent %s sent chat message in project %s",
            self._agent_id,
            self._project_id,
        )

    async def _execute_set_directive(self, action: dict) -> None:
        """Execute set_directive: write a CoordinationDirective to Blackboard.

        PhaseStrategy 定義遊戲規則；Directive 是 Supervisor 的即時指令（互補，非替代）。
        """
        from app.agents.blackboard import BlackboardManager
        from app.agents.blackboard_schemas import CoordinationDirective

        round_type = action.get("round_type", "open_diverge")
        focus_topic = action.get("focus_topic")
        invited_speaker = action.get("invited_speaker")
        instruction = action.get("instruction", "")

        if focus_topic:
            focus_topic = self._chinese_convert(focus_topic)
        if instruction:
            instruction = self._chinese_convert(instruction)

        try:
            directive = CoordinationDirective(
                round_type=round_type,
                focus_topic=focus_topic,
                invited_speaker=invited_speaker,
                instruction=instruction,
            )
        except Exception as exc:
            logger.warning("Invalid set_directive action: %s", exc)
            return

        bb = BlackboardManager(
            project_id=self._project_id,
            agent_id=self._agent_id,
            seat_role=self._seat_role,
        )
        await bb.write_coordination_directive(directive)
        logger.info(
            "Agent %s set_directive: round_type=%s focus=%s invited=%s",
            self._agent_id,
            round_type,
            focus_topic,
            invited_speaker,
        )

    async def _emit_cue_event(self, invited_speaker: str) -> None:
        """Phase 28：set_directive 成功後通知前端某人被點名了。"""
        try:
            await event_bus.publish(
                CueEvent(
                    project_id=self._project_id,
                    target_seat_role=invited_speaker,
                    from_seat_role=self._seat_role,
                )
            )
        except Exception:  # pragma: no cover - best-effort UI hint
            logger.debug("_emit_cue_event failed", exc_info=True)

    async def _emit_turn_state_event(
        self,
        controller: TurnController,
        context: dict,
    ) -> None:
        """Phase 28：RR 模式下廣播 next_speaker 變動，前端可即時更新按鈕狀態。"""
        try:
            # 以當前 seat 角度問一次 controller，藉此拿到實際 next_speaker。
            # 任意一個 seat 問都會回同樣的 next_speaker (RR 只看 queue head)。
            decision = await controller.is_my_turn(self._seat_role, context)
            await event_bus.publish(
                TurnStateEvent(
                    project_id=self._project_id,
                    policy=controller.policy.value,
                    next_speaker=decision.next_speaker,
                    allowed_actions=decision.allowed_actions,
                )
            )
        except Exception:  # pragma: no cover - best-effort UI hint
            logger.debug("_emit_turn_state_event failed", exc_info=True)

    async def _update_last_event_ts(self) -> None:
        """Update the project's last-event timestamp in Redis.

        Ensures Rule 5 (idle detection) works in all-AI mode where
        only AI agents produce events.
        """
        try:
            import redis.asyncio as aioredis
            from app.config import settings
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                await r.set(
                    f"project:{self._project_id}:last_event_ts",
                    str(time.time()),
                )
            finally:
                await r.aclose()
        except Exception as exc:
            logger.debug("Failed to update last_event_ts: %s", exc)

    def _chinese_convert(self, text: str) -> str:
        """Apply Chinese conversion if text is non-empty."""
        if not text:
            return text
        try:
            return chinese_converter.convert(text)
        except Exception:
            return text

    async def _save_trace(
        self,
        current_stage: str,
        assess_result: Any | None,
        think_result: Any | None,
        act_result: ActResult,
        *,
        micro_phase: str | None = None,
        role_status: str = "normal",
        turn_policy: str = "cued",
    ) -> None:
        """Persist a DecisionTrace row to agent_decision_trace.

        Phase 28：``assess_details`` 與 ``action_details`` 兩個 JSONB 都帶上
        ``turn_policy``，方便論文分析對齊三模式條件。
        """
        try:
            assess_details = (
                {**assess_result.details, "turn_policy": turn_policy}
                if assess_result and assess_result.details is not None
                else {"turn_policy": turn_policy}
            )
            action_details = {
                "executed": act_result.executed_actions,
                "skipped": act_result.skipped_actions,
                "errors": act_result.errors,
                "turn_policy": turn_policy,
            }
            async with async_session_factory() as session:
                trace = AgentDecisionTrace(
                    project_id=self._project_id,
                    agent_id=self._agent_id,
                    stage=current_stage,
                    micro_phase=micro_phase,
                    role_status=role_status,
                    assess_result=assess_result.decision if assess_result else "unknown",
                    assess_rule=assess_result.rule if assess_result else None,
                    assess_details=assess_details,
                    prompt_text=think_result.prompt_text if think_result else None,
                    llm_response=think_result.raw_response if think_result else None,
                    llm_model=think_result.model if think_result else None,
                    llm_tokens_in=think_result.tokens_in if think_result else None,
                    llm_tokens_out=think_result.tokens_out if think_result else None,
                    llm_latency_ms=think_result.latency_ms if think_result else None,
                    action_type=(
                        act_result.executed_actions[0].get("type")
                        if act_result.executed_actions
                        else "no_action"
                    ),
                    action_details=action_details,
                    action_result="success" if act_result.success else "error",
                )
                session.add(trace)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to save DecisionTrace: %s", exc)
