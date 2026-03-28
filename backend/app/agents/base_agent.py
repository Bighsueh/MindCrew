from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any
from uuid import UUID

from app.agents.assess import AssessEngine, AssessResult
from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import AgentIntention
from app.agents.context_buffer import ContextBuffer
from app.agents.conversation_health import ConversationHealthAnalyzer
from app.agents.coordinator import agent_coordinator
from app.agents.evaluator import StageEvaluator
from app.agents.throttle import ThrottleGate
from app.llm.factory import LLMProviderFactory
from app.ws.presence_tracker import presence_tracker

logger = logging.getLogger(__name__)

# Staggered entry delays (seconds after presence gate opens).
# Supervisor speaks first; Crew agents phase in gradually so each sees
# the previous agents' output before acting.  (論文 §4.1.3)
_ENTRY_DELAYS: dict[str, float] = {
    "supervisor": 0.0,
    "crew_1": 8.0,
    "crew_2": 12.0,
    "crew_3": 16.0,
    "crew_4": 20.0,
}


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
        self._health_analyzer = ConversationHealthAnalyzer()
        self._blackboard = BlackboardManager(
            project_id=project_id,
            agent_id=agent_id,
            seat_role=seat_role,
        )

        # Guard against concurrent evaluations (race condition fix)
        self._evaluation_in_progress = False

        # Human Presence Gate — created in start() to ensure a running event loop
        self._presence_event: asyncio.Event | None = None
        self._stop_event: asyncio.Event | None = None

        # Lazy-import ThinkEngine and ActEngine to avoid circular imports
        self._think_engine: Any = None
        self._act_engine: Any = None

        # Proactive initiation budget (spec §5.2)
        self._last_proactive_time: float | None = None

        # Staggered entry: one-time delay per agent lifecycle
        self._entry_completed: bool = False
        # Round gate: supervisor signals after first action
        self._first_action_done: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the decision loop. Runs until stop() is called.

        The loop blocks on the Human Presence Gate: when no human is connected
        to the project, the agent pauses with zero CPU usage.  It resumes
        instantly when a human connects.
        """
        # Create asyncio primitives inside the running event loop (Python 3.10+)
        self._presence_event = presence_tracker.get_presence_event(self._project_id)
        self._stop_event = asyncio.Event()
        self._running = True
        logger.info(
            "Agent %s (%s) starting in project %s",
            self._agent_id,
            "supervisor" if self._is_supervisor else "crew",
            self._project_id,
        )
        while self._running:
            # ── Human Presence Gate ──────────────────────────────
            # Block until at least one human is connected OR stop() is called.
            await _wait_for_any(self._presence_event, self._stop_event)
            if not self._running:
                break

            # ── Staggered Entry Protocol ────────────────────────
            if not self._entry_completed:
                await self._staggered_entry()
                self._entry_completed = True

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
        if self._stop_event is not None:
            self._stop_event.set()  # Unblock if waiting on presence gate

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Staggered entry (Solution A)
    # ------------------------------------------------------------------

    async def _staggered_entry(self) -> None:
        """One-time delay so Supervisor speaks first, Crew phases in gradually.

        Avoids the 'simultaneous burst' problem where all agents generate
        independent actions before seeing each other's output.
        """
        delay = _ENTRY_DELAYS.get(self._seat_role, 10.0)
        if delay > 0:
            logger.info(
                "Agent %s (%s) staggered entry: waiting %.1fs",
                self._agent_id,
                self._seat_role,
                delay,
            )
            await asyncio.sleep(delay)
        # Crew agents also wait for the round gate (supervisor's first action)
        if not self._is_supervisor:
            await agent_coordinator.wait_for_round_gate(self._project_id)

    # ------------------------------------------------------------------
    # Dynamic proactive cooldown (Solution C)
    # ------------------------------------------------------------------

    def _compute_proactive_cooldown(self, context: dict) -> float:
        """Dynamic cooldown based on conversation state.

        Active conversation → shorter cooldown (more to respond to).
        Silent conversation → shorter cooldown (break the silence).
        Normal flow where I'm not needed → longer cooldown.
        """
        base = 45.0 if self._is_supervisor else 60.0

        # New thread starting → halve cooldown
        active_thread = context.get("active_thread")
        if active_thread and active_thread.get("turn_count", 0) <= 3:
            base *= 0.5

        # Long silence (>20s) → greatly reduce cooldown
        last_event_time = context.get("_last_event_time")
        if last_event_time:
            silence = time.time() - last_event_time
            if silence > 20:
                base *= 0.3

        # Directive invitation → bypass entirely
        directive = context.get("blackboard", {}).get("coordination_directive")
        if directive and directive.get("invited_speaker"):
            if self._seat_role.lower() in directive["invited_speaker"].lower():
                return 0.0

        return base

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

        # Supervisor: run StageEvaluator on its own schedule (one at a time)
        if self._is_supervisor and self._evaluator is not None:
            if self._evaluator.should_evaluate() and not self._evaluation_in_progress:
                self._evaluation_in_progress = True
                asyncio.create_task(self._run_evaluation(context))

        if assess_result.decision in ("wait", "observe"):
            return

        # Proactive initiation budget (dynamic cooldown — Solution C)
        _REACTIVE_RULES = frozenset((
            "rule_0_invited", "rule_1_mention", "rule_5_idle",
            "rule_5_5_reengagement", "rule_6_relevant_event",
            "rule_7_addressed",
        ))
        is_reactive = assess_result.rule in _REACTIVE_RULES
        if not is_reactive:
            budget = self._compute_proactive_cooldown(context)
            if self._last_proactive_time is not None:
                elapsed = time.time() - self._last_proactive_time
                if elapsed < budget:
                    logger.debug(
                        "Agent %s proactive initiation blocked (elapsed=%.1f < budget=%.1f)",
                        self._agent_id,
                        elapsed,
                        budget,
                    )
                    return

        # Inject conversation health into context (all agents)
        all_seats = [s.get("role", "") for s in context.get("seats", [])]
        health = self._health_analyzer.get_health_context(
            context.get("recent_chat", []),
            context.get("active_thread"),
            all_seats,
        )
        if health:
            context["conversation_health"] = health

        # Step 3: Think
        think_engine = self._get_think_engine()
        think_result = await think_engine.generate_actions(context)

        if not think_result.actions or (
            len(think_result.actions) == 1
            and think_result.actions[0].get("type") == "no_action"
        ):
            return

        # Step 3.5: WRITE_BLACKBOARD — publish intention for coordination
        await self._write_blackboard(think_result, context)

        # Queue backpressure: diminishing join probability as queue fills
        queue_depth = agent_coordinator.get_queue_depth(self._project_id)
        if queue_depth > 0 and assess_result.rule != "rule_1_mention":
            join_prob = 1.0 / (1.0 + queue_depth)
            if random.random() > join_prob:
                logger.debug(
                    "Agent %s yielded due to queue backpressure (depth=%d, p=%.2f)",
                    self._agent_id,
                    queue_depth,
                    join_prob,
                )
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

            # Record proactive initiation time for budget enforcement
            if not is_reactive and act_result.executed_actions:
                self._last_proactive_time = time.time()

            logger.debug(
                "Agent %s executed %d actions",
                self._agent_id,
                len(act_result.executed_actions),
            )
        finally:
            await agent_coordinator.release(self._project_id, self._agent_id)
            # Round gate: supervisor marks first action done so crew can proceed
            if self._is_supervisor and not self._first_action_done:
                self._first_action_done = True
                await agent_coordinator.mark_supervisor_done(
                    self._project_id, self._agent_id
                )

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
        finally:
            self._evaluation_in_progress = False

    # ------------------------------------------------------------------
    # Blackboard write (§4.1)
    # ------------------------------------------------------------------

    async def _write_blackboard(self, think_result: Any, context: dict) -> None:
        """Extract reasoning + intent from ThinkResult and write to Blackboard."""
        try:
            # Determine focus_topic and viewpoint from LLM response
            # The LLM may include these in reasoning or we extract from actions
            focus_topic: str | None = None
            viewpoint: str | None = None
            next_intent = "no_action"

            for action in think_result.actions:
                atype = action.get("type", "no_action")
                if atype != "no_action":
                    next_intent = atype
                    if atype == "add_note":
                        focus_topic = action.get("content", "")[:50]
                    elif atype == "chat_message":
                        focus_topic = action.get("content", "")[:50]
                    break

            # Try to extract focus_topic/viewpoint from raw JSON response
            try:
                import json as _json
                raw_data = _json.loads(think_result.raw_response.strip().strip("`").strip())
                focus_topic = raw_data.get("focus_topic", focus_topic)
                viewpoint = raw_data.get("viewpoint", viewpoint)
            except Exception:
                pass

            intention = AgentIntention(
                agent_id=self._agent_id,
                seat_role=self._seat_role,
                reasoning_summary=think_result.reasoning[:200] if think_result.reasoning else "",
                next_intent=next_intent,
                focus_topic=focus_topic,
                viewpoint=viewpoint,
                confidence=0.7,
                stage=context.get("current_stage", "discover"),
            )
            await self._blackboard.write_intention(intention)
        except Exception:
            logger.warning(
                "Failed to write blackboard for %s", self._agent_id, exc_info=True
            )

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


async def _wait_for_any(*events: asyncio.Event) -> None:
    """Block until *any* of the given events is set.

    Returns immediately if at least one event is already set.
    """
    if any(e.is_set() for e in events):
        return

    tasks = [asyncio.create_task(e.wait()) for e in events]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        # Await cancellation so tasks don't leak as "pending" warnings
        await asyncio.gather(*tasks, return_exceptions=True)


def _now_time_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%H:%M")
