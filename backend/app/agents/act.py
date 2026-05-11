from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.chinese.converter import chinese_converter
from app.db.models.agent_decision_trace import AgentDecisionTrace
from app.db.models.message import Message
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent

logger = logging.getLogger(__name__)

# Action types that crew agents are forbidden to execute
_SUPERVISOR_ONLY_ACTIONS = {"advance_stage", "set_directive"}


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
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._agent_name = agent_name
        self._is_supervisor = is_supervisor

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
        legal, illegal = self._validate_actions(actions, comm_mode=comm_mode)
        result.skipped_actions.extend(illegal)

        if not legal:
            result.success = len(illegal) == 0
            await self._save_trace(
                current_stage, assess_result, think_result, result,
                micro_phase=micro_phase, role_status=role_status,
            )
            return result

        # Sort: chat_message first, then canvas ops
        chat_actions = [a for a in legal if a.get("type") == "chat_message"]
        canvas_actions = [a for a in legal if a.get("type") != "chat_message"]
        ordered = chat_actions + canvas_actions

        for i, action in enumerate(ordered):
            if i > 0:
                delay = random.uniform(2.0, 5.0)
                await asyncio.sleep(delay)

            try:
                await self._execute_single(action, current_stage, sub_phase=sub_phase)
                result.executed_actions.append(action)
                # Fix #1: supervisor 點名 crew 後設 awaiting-reply 鎖
                if (
                    self._is_supervisor
                    and action.get("type") == "chat_message"
                    and seats
                ):
                    await self._maybe_set_awaiting_reply(action, seats)
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
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # Spec 13 — comm_mode action whitelist
    _COMM_MODE_ALLOWED: dict[str, frozenset[str]] = {
        "silent_write": frozenset({"create_note", "no_action"}),
        "silent_rearrange": frozenset({"move_note", "swap_notes", "no_action"}),
        "reveal_round": frozenset({"chat_message", "create_note", "no_action"}),
        "discussion": frozenset(),  # 空集 = 全部允許
    }

    def _validate_actions(
        self, actions: list[dict], comm_mode: str = "discussion",
    ) -> tuple[list[dict], list[dict]]:
        """Separate legal from illegal actions.

        Two layers:
          1. Crew cannot execute supervisor-only actions
          2. Spec 13 comm_mode action whitelist (silent_write only allows create_note, etc.)
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
            # Safety-net: replace any remaining @{crew_N} template patterns
            from app.agents.prompts.interpolation import interpolate_crew_names
            content = interpolate_crew_names(content)
            await self._execute_chat_message(content, current_stage)
        elif action_type in CANVAS_ACTION_TYPES:
            await execute_canvas_tool(
                op_type=action_type,
                action=action,
                project_id=self._project_id,
                agent_id=self._agent_id,
                agent_name=self._agent_name,
                sub_phase_id=sub_phase,
                seat_role=self._seat_role,
            )
        elif action_type == "set_directive":
            await self._execute_set_directive(action)
        elif action_type == "no_action":
            logger.debug("Agent %s chose no_action: %s", self._agent_id, action.get("reason", ""))
        else:
            logger.warning("Unknown action type: %s", action_type)

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
        except Exception:
            logger.debug("set_awaiting_reply hook failed", exc_info=True)

    async def _execute_chat_message(self, content: str, stage: str) -> None:
        """Publish ChatMessageEvent to EventBus and persist to DB."""
        if not content:
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

    async def _update_last_event_ts(self) -> None:
        """Update the project's last-event timestamp in Redis.

        Ensures Rule 5 (idle detection) works in all-AI mode where
        only AI agents produce events.
        """
        try:
            import redis.asyncio as aioredis
            from app.config import settings
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await r.set(
                f"project:{self._project_id}:last_event_ts",
                str(time.time()),
            )
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
    ) -> None:
        """Persist a DecisionTrace row to agent_decision_trace."""
        try:
            async with async_session_factory() as session:
                trace = AgentDecisionTrace(
                    project_id=self._project_id,
                    agent_id=self._agent_id,
                    stage=current_stage,
                    micro_phase=micro_phase,
                    role_status=role_status,
                    assess_result=assess_result.decision if assess_result else "unknown",
                    assess_rule=assess_result.rule if assess_result else None,
                    assess_details=assess_result.details if assess_result else None,
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
                    action_details=(
                        {"executed": act_result.executed_actions,
                         "skipped": act_result.skipped_actions,
                         "errors": act_result.errors}
                    ),
                    action_result="success" if act_result.success else "error",
                )
                session.add(trace)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to save DecisionTrace: %s", exc)
