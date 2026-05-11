from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any
from uuid import UUID

from app.agents.assess import AssessEngine, AssessResult
from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_writer import write_intention_from_think_result
from app.agents.context_buffer import ContextBuffer
from app.agents.conversation_health import ConversationHealthAnalyzer
from app.agents.coordinator import agent_coordinator
from app.agents.evaluator import StageEvaluator
from app.agents.phase_strategy import PHASE_STRATEGIES
from app.agents.summarizer import do_summarize, should_summarize
from app.agents.throttle import ThrottleGate
from app.llm.factory import LLMProviderFactory
from app.ws.presence_tracker import presence_tracker

logger = logging.getLogger(__name__)

# Staggered entry delays (seconds after presence gate opens).
# Supervisor speaks first; Crew agents phase in gradually so each sees
# the previous agents' output before acting.  (論文 §4.1.3)
_ENTRY_DELAYS: dict[str, float] = {
    "supervisor": 0.0,
    "crew_1": 10.0,
    "crew_2": 10.0,
    "crew_3": 10.0,
    "crew_4": 10.0,
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
        # Keep a strong reference to the background evaluation task so the
        # GC can't collect it mid-run (asyncio fire-and-forget anti-pattern fix).
        # Symptom without this: "coroutine ignored GeneratorExit" + "Task was destroyed but it is pending"
        self._evaluation_task: asyncio.Task | None = None

        # Human Presence Gate — created in start() to ensure a running event loop
        self._presence_event: asyncio.Event | None = None
        self._stop_event: asyncio.Event | None = None

        # Lazy-import ThinkEngine and ActEngine to avoid circular imports
        self._think_engine: Any = None
        self._act_engine: Any = None

        # Summarizer cooldown (Phase 13): prevent rapid-fire summaries
        self._last_summary_time: float = 0.0

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
        # Cancel any in-flight background evaluation task so it doesn't
        # outlive the agent loop and trigger "Task was destroyed but it is pending".
        task = self._evaluation_task
        if task is not None and not task.done():
            task.cancel()

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
        """Dynamic cooldown based on conversation state."""
        seats = context.get("seats", [])
        is_all_ai = all(s.get("type") == "ai" for s in seats)
        # Check if humans are actively chatting (not just occupying a seat)
        recent_chat = context.get("recent_chat", [])
        human_active = any(m.get("sender_type") == "human" for m in recent_chat[-10:])
        if is_all_ai or not human_active:
            # All-AI mode OR human present but silent: equal footing, short cooldown
            base = 25.0
            base *= 0.3
        else:
            # Human actively participating: longer cooldown to give them space
            base = 30.0 if self._is_supervisor else 40.0

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

        # Load PhaseStrategy and inject into context (Phase 13)
        micro_phase = context.get("current_micro_phase", "1.1")
        strategy = PHASE_STRATEGIES.get(micro_phase)
        if strategy:
            context["phase_strategy"] = {
                "comm_strategy": strategy.comm_strategy,
                "comm_goal": strategy.comm_goal,
                "supervisor_mode": strategy.supervisor_mode,
            }

        # Supervisor Summarizer: SS 策略下定期做摘要
        if self._is_supervisor and strategy:
            if strategy.comm_strategy == "simultaneous_summarizer":
                # 摘要冷卻：至少間隔 30 秒避免連續觸發
                summary_cooldown = time.time() - self._last_summary_time > 30.0
                if summary_cooldown and should_summarize(context, strategy.summarize_interval):
                    self._last_summary_time = time.time()
                    llm_service = LLMProviderFactory.get_service()
                    summary = await do_summarize(context, llm_service)
                    if summary:
                        act_engine = self._get_act_engine()
                        await act_engine.execute(
                            actions=[{"type": "chat_message", "content": f"【摘要】{summary}"}],
                            current_stage=context.get("current_stage", "discover"),
                        )
                    return

        # Spec 14: Supervisor persona router — 決定本回合是 A/B 哪支發話
        if "supervisor" in self._seat_role.lower():
            try:
                from app.agents.supervisor.router import select_supervisor_persona
                decision = await select_supervisor_persona(self._project_id, context)
                if decision.persona is not None:
                    context["_supervisor_persona_invocation"] = decision.persona.invocation
                    logger.info(
                        "Supervisor router: project=%s persona=%s triggers=%s pending_a=%d",
                        self._project_id,
                        decision.persona.persona,
                        decision.persona.trigger_ids,
                        decision.pending_a_queue_size,
                    )
            except Exception:
                logger.debug("Supervisor router failed (non-fatal)", exc_info=True)

        # Check if another agent is currently acting
        another_acting = agent_coordinator.is_agent_acting(self._project_id)
        is_all_ai = all(s.get("type") == "ai" for s in context.get("seats", []))

        # Update throttle for all-AI mode
        self._throttle.update_contribution(self._contribution, is_all_ai=is_all_ai)

        # Step 2: Assess
        assess_result: AssessResult = await self._assess_engine.evaluate(
            context=context,
            agent_id=self._agent_id,
            ai_contribution=self._contribution,
            last_action_time=self._throttle.last_action_time,
            last_idle_event_time=context.get("_last_event_time"),
            another_agent_acting=another_acting,
            throttle_min_interval=self._throttle.params.min_interval,
        )

        if assess_result.decision == "observe":
            logger.debug(
                "Agent %s assess → observe (rule=%s)",
                self._agent_id,
                assess_result.rule,
            )
        else:
            logger.info(
                "Agent %s assess → %s (rule=%s, details=%s)",
                self._agent_id,
                assess_result.decision,
                assess_result.rule,
                assess_result.details,
            )

        # Supervisor: run StageEvaluator on its own schedule (one at a time)
        if self._is_supervisor and self._evaluator is not None:
            should_eval = self._evaluator.should_evaluate(context)
            if should_eval and not self._evaluation_in_progress:
                logger.info("Triggering stage evaluation for %s", self._project_id)
                self._evaluation_in_progress = True
                # Store the task so it isn't GC'd before completion.
                # The done_callback clears the reference once finished.
                task = asyncio.create_task(self._run_evaluation(context))
                self._evaluation_task = task
                task.add_done_callback(lambda _t: setattr(self, "_evaluation_task", None))

        if assess_result.decision in ("wait", "observe"):
            return

        # Rule X: inject force-organize flag so LLM prioritizes canvas tools
        if assess_result.rule == "rule_x_canvas_untidy":
            context["_force_canvas_organize"] = True

        # Round gate: supervisor 首次 INTERVENE 即開門，不需等 action 完成
        if self._is_supervisor and not self._first_action_done:
            self._first_action_done = True
            await agent_coordinator.mark_supervisor_done(
                self._project_id, self._agent_id
            )

        # Proactive initiation budget (dynamic cooldown — Solution C)
        _REACTIVE_RULES = frozenset((
            "rule_0_1_fresh_project",
            "rule_1_mention", "rule_5_idle",
            "rule_5_5_reengagement", "rule_5_5_peer_relevance",
            "rule_0_5_debate_stance",
            "rule_6_relevant_event", "rule_7_addressed",
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
                micro_phase=context.get("current_micro_phase"),
                role_status=context.get("my_role_status", "normal"),
                sub_phase=context.get("current_sub_phase"),
                comm_mode=context.get("comm_mode", "discussion"),
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
        except asyncio.CancelledError:
            # Expected during shutdown — re-raise so asyncio finalises cleanly.
            raise
        except Exception as exc:
            logger.error("Stage evaluation error: %s", exc)
        finally:
            self._evaluation_in_progress = False

    # ------------------------------------------------------------------
    # Blackboard write (§4.1)
    # ------------------------------------------------------------------

    async def _write_blackboard(self, think_result: Any, context: dict) -> None:
        """Delegate to blackboard_writer module."""
        await write_intention_from_think_result(
            blackboard=self._blackboard,
            think_result=think_result,
            context=context,
            agent_id=self._agent_id,
            seat_role=self._seat_role,
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
    return datetime.now(timezone.utc).strftime("%H:%M:%S")
