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
_SUPERVISOR_ONLY_ACTIONS = {"advance_stage"}


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
        legal, illegal = self._validate_actions(actions)
        result.skipped_actions.extend(illegal)

        if not legal:
            result.success = len(illegal) == 0
            await self._save_trace(
                current_stage, assess_result, think_result, result
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
                await self._execute_single(action, current_stage)
                result.executed_actions.append(action)
            except Exception as exc:
                logger.error(
                    "Action execution failed (type=%s): %s",
                    action.get("type"),
                    exc,
                )
                result.errors.append(str(exc))
                result.success = False

        await self._save_trace(current_stage, assess_result, think_result, result)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_actions(
        self, actions: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Separate legal from illegal actions.

        Crew agents cannot execute supervisor-only actions.
        """
        legal: list[dict] = []
        illegal: list[dict] = []
        for action in actions:
            action_type = action.get("type", "")
            if not self._is_supervisor and action_type in _SUPERVISOR_ONLY_ACTIONS:
                logger.warning(
                    "Crew agent %s attempted supervisor-only action %s — blocked",
                    self._agent_id,
                    action_type,
                )
                illegal.append({**action, "_blocked_reason": "crew不能執行advance-stage"})
            else:
                legal.append(action)
        return legal, illegal

    async def _execute_single(self, action: dict, current_stage: str) -> None:
        """Dispatch a single action to the appropriate handler."""
        action_type = action.get("type", "")
        content = action.get("content", "")

        # Ensure content is in Traditional Chinese
        if content:
            content = chinese_converter.convert(content)

        if action_type == "chat_message":
            await self._execute_chat_message(content, current_stage)
        elif action_type == "add_note":
            await self._execute_canvas_op("add_note", action)
        elif action_type == "move_note":
            await self._execute_canvas_op("move_note", action)
        elif action_type == "edit_note":
            await self._execute_canvas_op("edit_note", action)
        elif action_type == "delete_note":
            await self._execute_canvas_op("delete_note", action)
        elif action_type == "group_notes":
            await self._execute_canvas_op("group_notes", action)
        elif action_type == "no_action":
            logger.debug("Agent %s chose no_action: %s", self._agent_id, action.get("reason", ""))
        else:
            logger.warning("Unknown action type: %s", action_type)

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

    async def _execute_canvas_op(self, op_type: str, action: dict) -> None:
        """Execute canvas operations via the CanvasOps bridge."""
        from app.bridge.canvas_ops import canvas_ops

        content: str = action.get("content", "")
        if content:
            content = self._chinese_convert(content)

        if op_type == "add_note":
            note_id = await canvas_ops.add_note(
                project_id=self._project_id,
                content=content,
                position=action.get("position"),
                color=action.get("color", "yellow"),
                author_id=self._agent_id,
                author_name=self._agent_name,
                author_type="ai",
            )
            logger.info(
                "Agent %s add_note project=%s note_id=%s",
                self._agent_id,
                self._project_id,
                note_id,
            )

        elif op_type == "move_note":
            note_id = action.get("note_id", "")
            target_group = action.get("target_group")
            ok = await canvas_ops.move_note(
                project_id=self._project_id,
                note_id=note_id,
                target_group=target_group,
            )
            logger.info(
                "Agent %s move_note project=%s note_id=%s target_group=%s ok=%s",
                self._agent_id,
                self._project_id,
                note_id,
                target_group,
                ok,
            )

        elif op_type == "edit_note":
            note_id = action.get("note_id", "")
            ok = await canvas_ops.edit_note(
                project_id=self._project_id,
                note_id=note_id,
                new_content=content,
            )
            logger.info(
                "Agent %s edit_note project=%s note_id=%s ok=%s",
                self._agent_id,
                self._project_id,
                note_id,
                ok,
            )

        elif op_type == "delete_note":
            note_id = action.get("note_id", "")
            ok = await canvas_ops.delete_note(
                project_id=self._project_id,
                note_id=note_id,
            )
            logger.info(
                "Agent %s delete_note project=%s note_id=%s ok=%s",
                self._agent_id,
                self._project_id,
                note_id,
                ok,
            )

        elif op_type == "group_notes":
            note_ids: list[str] = action.get("note_ids", [])
            group_name: str = action.get("group_name", "")
            ok = await canvas_ops.group_notes(
                project_id=self._project_id,
                note_ids=note_ids,
                group_name=group_name,
            )
            logger.info(
                "Agent %s group_notes project=%s group=%s count=%d ok=%s",
                self._agent_id,
                self._project_id,
                group_name,
                len(note_ids),
                ok,
            )

        else:
            logger.warning("Unknown canvas op type: %s", op_type)

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
    ) -> None:
        """Persist a DecisionTrace row to agent_decision_trace."""
        try:
            async with async_session_factory() as session:
                trace = AgentDecisionTrace(
                    project_id=self._project_id,
                    agent_id=self._agent_id,
                    stage=current_stage,
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
