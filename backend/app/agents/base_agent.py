from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from app.agents.assess import AssessEngine, AssessResult
from app.agents.context_buffer import ContextBuffer
from app.agents.coordinator import agent_coordinator
from app.agents.evaluator import StageEvaluator
from app.agents.throttle import ThrottleGate
from app.llm.factory import LLMProviderFactory

logger = logging.getLogger(__name__)


class BaseAgent:
    """Universal agent implementation shared by both Supervisor and Crew agents.

    Decision cycle (runs every second):
    1. Observe  — build context from ContextBuffer
    2. Assess   — rule engine decides whether to act
    3. Think    — call LLM (only if decision == intervene)
    4. Act      — acquire coordinator lock → throttle wait → execute
    5. Log      — DecisionTrace is written inside ActEngine.execute()

    Supervisor additionally runs StageEvaluator on a separate schedule.
    """

    def __init__(
        self,
        project_id: UUID,
        agent_id: str,
        seat_role: str,
        agent_name: str,
        ai_contribution: str = "medium",
        is_supervisor: bool = False,
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._agent_name = agent_name
        self._contribution = ai_contribution
        self._is_supervisor = is_supervisor
        self._running = False

        # Sub-components (created lazily to respect the factory pattern)
        self._context_buffer = ContextBuffer(
            project_id=project_id,
            agent_id=agent_id,
            seat_role=seat_role,
        )
        self._assess_engine = AssessEngine()
        self._throttle = ThrottleGate(ai_contribution=ai_contribution)
        self._evaluator: StageEvaluator | None = (
            StageEvaluator(
                project_id=project_id,
                agent_id=agent_id,
                ai_contribution=ai_contribution,
            )
            if is_supervisor
            else None
        )

        # Lazy-import ThinkEngine and ActEngine to avoid circular imports
        self._think_engine: Any = None
        self._act_engine: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the decision loop. Runs until stop() is called."""
        self._running = True
        logger.info(
            "Agent %s (%s) starting in project %s",
            self._agent_id,
            "supervisor" if self._is_supervisor else "crew",
            self._project_id,
        )
        while self._running:
            try:
                await self._decision_cycle()
            except Exception as exc:
                logger.error(
                    "Unhandled error in agent %s decision cycle: %s",
                    self._agent_id,
                    exc,
                    exc_info=True,
                )
            await asyncio.sleep(1.0)

        await self._context_buffer.close()
        logger.info("Agent %s stopped", self._agent_id)

    async def stop(self) -> None:
        """Signal the agent to stop gracefully after the current cycle."""
        logger.info("Agent %s received stop signal", self._agent_id)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Main decision cycle
    # ------------------------------------------------------------------

    async def _decision_cycle(self) -> None:
        # Step 1: Observe
        context = await self._context_buffer.get_current_context()

        # Check if another agent is currently acting
        another_acting = agent_coordinator.is_agent_acting(self._project_id)
        is_all_ai = all(s.get("type") == "ai" for s in context.get("seats", []))

        # Update throttle for all-AI mode
        self._throttle.update_contribution(self._contribution, is_all_ai=is_all_ai)

        # Step 2: Assess
        assess_result: AssessResult = self._assess_engine.evaluate(
            context=context,
            agent_id=self._agent_id,
            ai_contribution=self._contribution,
            last_action_time=self._throttle.last_action_time,
            last_idle_event_time=context.get("_last_event_time"),
            another_agent_acting=another_acting,
            throttle_min_interval=self._throttle.params.min_interval,
        )

        logger.debug(
            "Agent %s assess → %s (rule=%s)",
            self._agent_id,
            assess_result.decision,
            assess_result.rule,
        )

        # Supervisor: run StageEvaluator on its own schedule
        if self._is_supervisor and self._evaluator is not None:
            if self._evaluator.should_evaluate():
                asyncio.create_task(self._run_evaluation(context))

        if assess_result.decision in ("wait", "observe"):
            return

        # Step 3: Think
        think_engine = self._get_think_engine()
        think_result = await think_engine.generate_actions(context)

        if not think_result.actions or (
            len(think_result.actions) == 1
            and think_result.actions[0].get("type") == "no_action"
        ):
            return

        # Step 4: Act — acquire coordinator lock first
        acquired = await agent_coordinator.acquire(
            project_id=self._project_id,
            agent_id=self._agent_id,
            is_supervisor=self._is_supervisor,
        )
        if not acquired:
            logger.debug("Agent %s could not acquire coordinator lock", self._agent_id)
            return

        try:
            # Throttle wait
            await self._throttle.wait()
            self._throttle.record_action()

            act_engine = self._get_act_engine()
            act_result = await act_engine.execute(
                actions=think_result.actions,
                current_stage=context.get("current_stage", "discover"),
                think_result=think_result,
                assess_result=assess_result,
            )

            # Record this action in context buffer for self-awareness
            if act_result.executed_actions:
                for executed in act_result.executed_actions:
                    await self._context_buffer.record_my_action({
                        "type": executed.get("type"),
                        "content": executed.get("content", ""),
                        "time": _now_time_str(),
                    })

            logger.debug(
                "Agent %s executed %d actions",
                self._agent_id,
                len(act_result.executed_actions),
            )
        finally:
            await agent_coordinator.release(self._project_id, self._agent_id)

    # ------------------------------------------------------------------
    # Supervisor evaluation task
    # ------------------------------------------------------------------

    async def _run_evaluation(self, context: dict) -> None:
        """Run stage evaluation in the background (supervisor only)."""
        if self._evaluator is None:
            return
        try:
            llm_service = LLMProviderFactory.get_service()
            eval_result = await self._evaluator.evaluate(context, llm_service)
            logger.info(
                "Supervisor %s stage eval: total=%.1f, passed=%s, action=%s",
                self._agent_id,
                eval_result.total_score,
                eval_result.passed,
                eval_result.action_taken,
            )
        except Exception as exc:
            logger.error("Stage evaluation error: %s", exc)

    # ------------------------------------------------------------------
    # Lazy component getters
    # ------------------------------------------------------------------

    def _get_think_engine(self) -> Any:
        if self._think_engine is None:
            from app.agents.think import ThinkEngine
            self._think_engine = ThinkEngine()
        return self._think_engine

    def _get_act_engine(self) -> Any:
        if self._act_engine is None:
            from app.agents.act import ActEngine
            self._act_engine = ActEngine(
                project_id=self._project_id,
                agent_id=self._agent_id,
                seat_role=self._seat_role,
                agent_name=self._agent_name,
                is_supervisor=self._is_supervisor,
            )
        return self._act_engine

    # ------------------------------------------------------------------
    # External integration hooks
    # ------------------------------------------------------------------

    async def on_human_seat_event(self, agreed: bool) -> None:
        """Called when a human responds to a stage advancement proposal."""
        if self._evaluator is not None:
            self._evaluator.register_human_response(agreed)

    def update_contribution(self, new_level: str) -> None:
        """Hot-reload AI contribution level without restarting the agent."""
        self._contribution = new_level
        self._throttle.update_contribution(new_level)
        if self._evaluator is not None:
            self._evaluator._contribution = new_level


def _now_time_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%H:%M")
