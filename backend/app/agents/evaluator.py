from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.blackboard import BlackboardManager
from app.db.models.stage_evaluation_log import StageEvaluationLog
from app.db.session import async_session_factory
from app.agents.context_buffer import get_evaluator_canvas
from app.agents.evaluator_scoring import compute_quantitative
from app.agents.topic_saturation import compute_and_write_topic_saturation
from app.agents.stage_advancement import advance_stage, propose_advance
from app.stages.micro_phases import get_next_micro_phase, is_macro_boundary

logger = logging.getLogger(__name__)

# Evaluation frequency per contribution level (seconds between evaluations)
_EVAL_INTERVALS: dict[str, float] = {
    "low": 45.0,
    "medium": 30.0,
    "high": 20.0,
}

# Consecutive passes required before advancing (cooling period)
_COOLING_COUNTS: dict[str, int] = {
    "low": 3,
    "medium": 2,
    "high": 1,
}

# Default score thresholds
_THRESHOLDS: dict[str, float] = {
    "low": 80.0,
    "medium": 70.0,
    "high": 60.0,
}


@dataclass
class EvaluationResult:
    quantitative_score: float
    qualitative_score: float | None
    total_score: float
    threshold: float
    passed: bool
    weak_areas: list[str]
    summary: str
    action_taken: str
    consecutive_pass_count: int
    blind_spot_score: float | None = None


class StageEvaluator:
    """Supervisor-only component: evaluates stage completion and triggers advancement.

    Uses both quantitative metrics (no LLM) and qualitative LLM analysis.
    Implements the cooling-period + human-proposal flow from spec §4.4.
    """

    def __init__(
        self,
        project_id: UUID,
        agent_id: str,
        ai_contribution: str = "medium",
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._contribution = ai_contribution

        self._last_eval_time: float = 0.0
        self._consecutive_pass_count: int = 0
        self._threshold: float = _THRESHOLDS.get(ai_contribution, 70.0)
        self._proposal_pending: bool = False
        self._proposal_event: asyncio.Event = asyncio.Event()
        self._proposal_agreed: bool = False
        self._blind_spot_challenge_sent: bool = False
        self._last_guidance_text: str = ""
        self._last_guidance_time: float = 0.0
        self._crew_responded_since_guidance: bool = True  # Start as True to allow first guidance
        self._blackboard = BlackboardManager(
            project_id=project_id,
            agent_id=agent_id,
            seat_role="supervisor",
        )
        # Event-driven evaluation (Phase 13): 每累積 N 個新事件才評估
        self._last_eval_chat_count: int = 0
        # Stale score fallback (Phase 13): LLM 失敗時沿用上次成功分數
        self._last_valid_scores: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_evaluate(self, context: dict | None = None) -> bool:
        """Event-driven evaluation gate with time floor and ceiling."""
        min_interval = _EVAL_INTERVALS.get(self._contribution, 30.0)
        elapsed = time.time() - self._last_eval_time
        if elapsed < min_interval:
            return False
        # 時間上限：超過 3 倍間隔強制評估（防止停滯）
        if elapsed > min_interval * 3:
            return True
        # Event-driven: 比較聊天數量差異
        if context is not None:
            current_chat_count = len(context.get("recent_chat", []))
            events_since = current_chat_count - self._last_eval_chat_count
            _EVENT_THRESHOLDS = {"low": 6, "medium": 4, "high": 3}
            required = _EVENT_THRESHOLDS.get(self._contribution, 4)
            return events_since >= required
        return True

    async def evaluate(self, context: dict, llm_service: Any) -> EvaluationResult:
        """Run a full evaluation cycle.

        1. Compute quantitative score
        2. Pre-screen: if quant * 0.4 < threshold * 0.8, skip qualitative
        3. Run qualitative LLM analysis
        4. Compute total, apply decision logic
        5. Log to DB
        """
        self._last_eval_time = time.time()
        self._last_eval_chat_count = len(context.get("recent_chat", []))
        stage: str = context.get("current_stage", "discover")
        phase_strategy = context.get("phase_strategy", {})
        micro_phase: str | None = context.get("current_micro_phase")
        canvas_state = await get_evaluator_canvas(
            context.get("project_id", self._project_id),
            micro_phase=micro_phase,
        )
        recent_chat: list[dict] = context.get("recent_chat", [])
        seats: list[dict] = context.get("seats", [])
        project_name: str = context.get("project_name", "")
        project_description: str = context.get("project_description", "")

        # Track if any Crew responded since last guidance (for dedup)
        if not self._crew_responded_since_guidance:
            for msg in recent_chat[-5:]:
                sender = msg.get("sender", "").lower()
                if any(r in sender for r in ("crew", "同理心", "結構化", "創意", "可行性")):
                    self._crew_responded_since_guidance = True
                    break

        if micro_phase:
            from app.agents.micro_phase_scoring import compute_micro_phase_quantitative
            quant_score = await compute_micro_phase_quantitative(micro_phase, canvas_state, recent_chat, seats, llm_service=llm_service)
        else:
            quant_score = await self._compute_quantitative(stage, canvas_state, recent_chat, seats, llm_service=llm_service)

        # Stage-specific weighting (Phase 1: 50:50 to ensure notes matter, others: 40:60)
        if stage == "discover":
            quant_weight, qual_weight = 0.5, 0.5
        else:
            quant_weight, qual_weight = 0.4, 0.6

        # Pre-screening
        qual_score: float | None = None
        qual_result: dict | None = None
        weak_areas: list[str] = []
        summary = ""
        blind_spot_score: float | None = None

        # Pre-screening: skip qualitative if quantitative alone can't plausibly reach threshold.
        # All-AI mode uses a lower gate to allow faster advancement.
        has_humans = any(s.get("type") == "human" for s in seats)
        pre_screen_multiplier = 0.3 if not has_humans else 0.5
        pre_screen_pass = quant_score >= self._threshold * pre_screen_multiplier
        if pre_screen_pass:
            qual_result = await self._run_qualitative(
                stage, canvas_state, recent_chat, llm_service,
                project_name=project_name, project_description=project_description,
            )
            if qual_result:
                qual_score = qual_result.get("overall_score", 0.0)
                weak_areas = qual_result.get("weak_areas", [])
                summary = qual_result.get("summary", "")
                blind_spot_score = qual_result.get("blind_spot_score")
                # If LLM response omits blind_spot_score, skip the veto
                # (previously treated as 0 which caused permanent stalls)
                if stage == "discover" and blind_spot_score is None:
                    logger.warning("LLM response missing blind_spot_score; skipping veto")
                # Stale score fallback: 快取成功的分數 (Phase 13)
                self._last_valid_scores = {
                    "qual_score": qual_score,
                    "blind_spot_score": blind_spot_score or 0.0,
                }
            elif self._last_valid_scores:
                # LLM 評估失敗，沿用上次成功分數 (stale-but-valid)
                qual_score = self._last_valid_scores.get("qual_score")
                blind_spot_score = None  # Do NOT reuse stale blind_spot for veto
                logger.info("Using stale qual_score=%.1f; blind_spot disabled (stale)",
                            qual_score or 0)
        else:
            logger.debug(
                "Pre-screening skipped qualitative (quant=%.1f, threshold=%.1f)",
                quant_score,
                self._threshold,
            )
            weak_areas = ["量化分數不足，尚未達到質性分析門檻"]

        # Total score
        if qual_score is not None:
            total = quant_score * quant_weight + qual_score * qual_weight
        else:
            # LLM unavailable — use quantitative score as sole indicator
            # Scale it to full range (not half) so advancement isn't blocked
            total = quant_score * 1.0

        # Effective threshold: adjust for All-AI mode and time pressure
        has_humans = any(s.get("type") == "human" for s in seats)
        effective_threshold = self._threshold
        if not has_humans:
            effective_threshold -= 10.0  # All-AI 模式降低門檻
        duration_minutes = context.get("stage_duration_minutes", 0.0)
        effective_threshold -= self._time_pressure_adjustment(stage, duration_minutes, micro_phase=micro_phase)

        passed = total >= effective_threshold

        # Blind spot veto: only at macro boundary (e.g. 1.3→2.1), not intra-Discover
        comm_goal = phase_strategy.get("comm_goal", "")
        blind_spot_veto_threshold = 50.0 if comm_goal in ("debate", "mild_competition") else 30.0
        next_mp = get_next_micro_phase(micro_phase) if micro_phase else None
        at_macro_boundary = (
            micro_phase is not None
            and next_mp is not None
            and is_macro_boundary(micro_phase, next_mp)
        )
        if stage == "discover" and at_macro_boundary and blind_spot_score is not None and blind_spot_score < blind_spot_veto_threshold:
            passed = False
            if not any("盲區分數不足" in w for w in weak_areas):
                weak_areas.insert(0, "盲區分數不足——團隊可能遺漏了重要面向")
            logger.info(
                "Blind spot veto triggered: blind_spot_score=%.1f < %.1f (comm_goal=%s)",
                blind_spot_score, blind_spot_veto_threshold, comm_goal,
            )

        if passed:
            self._consecutive_pass_count += 1
        elif qual_score is None and pre_screen_pass:
            # LLM infrastructure failure (not content quality failure)
            # Preserve pass count to avoid penalising transient outages
            logger.info(
                "Evaluation failed due to LLM unavailability; "
                "pass count preserved at %d",
                self._consecutive_pass_count,
            )
        else:
            self._consecutive_pass_count = 0

        # Discover requires at least 2 consecutive passes (lowered from 3)
        # All-AI mode: 1 pass is sufficient for faster iteration
        if not has_humans:
            required_passes = 1
        elif stage == "discover":
            required_passes = max(2, _COOLING_COUNTS.get(self._contribution, 2))
        else:
            required_passes = _COOLING_COUNTS.get(self._contribution, 2)

        action_taken = "none"

        if not passed and weak_areas:
            action_taken = "guided_weak_areas"
            await self._publish_weak_area_guidance(weak_areas)
        elif passed and self._consecutive_pass_count >= required_passes:
            # Discover: blind spot challenge gate (two-pass) — only with humans, macro stage mode
            if stage == "discover" and not micro_phase and not self._blind_spot_challenge_sent and has_humans:
                await self._publish_blind_spot_challenge()
                self._blind_spot_challenge_sent = True
                self._consecutive_pass_count = required_passes - 1
                action_taken = "blind_spot_challenge"
            elif micro_phase:
                # Micro-phase aware advancement
                next_mp = get_next_micro_phase(micro_phase)
                if next_mp is None:
                    action_taken = "terminal_micro_phase"  # 4.3 is terminal
                elif is_macro_boundary(micro_phase, next_mp):
                    # Cross macro phase boundary — use existing propose/advance flow
                    if has_humans:
                        action_taken = await self._propose_advance(stage, total)
                    else:
                        action_taken = await self._advance_stage(stage)
                else:
                    # Same macro phase — advance micro phase directly
                    action_taken = await self._advance_micro_phase(micro_phase, next_mp)
            else:
                if stage == "discover":
                    self._blind_spot_challenge_sent = False
                if has_humans:
                    action_taken = await self._propose_advance(stage, total)
                else:
                    action_taken = await self._advance_stage(stage)

        result = EvaluationResult(
            quantitative_score=quant_score,
            qualitative_score=qual_score,
            total_score=total,
            threshold=effective_threshold,
            passed=passed,
            weak_areas=weak_areas,
            summary=summary,
            action_taken=action_taken,
            consecutive_pass_count=self._consecutive_pass_count,
            blind_spot_score=blind_spot_score,
        )

        await self._log_to_db(stage, result, micro_phase=micro_phase)

        # Compute and write Topic Saturation to Blackboard (Summarizer role)
        await self._compute_topic_saturation(stage, canvas_state, recent_chat, llm_service)

        return result

    def register_human_response(self, agreed: bool) -> None:
        """Called externally when a human responds to a stage advance proposal."""
        self._proposal_agreed = agreed
        self._proposal_event.set()

    async def _compute_quantitative(
        self, stage: str, canvas: dict, recent_chat: list[dict], seats: list[dict],
        llm_service: Any = None,
    ) -> float:
        return await compute_quantitative(stage, canvas, recent_chat, seats, llm_service=llm_service)

    @staticmethod
    def _time_pressure_adjustment(
        stage: str,
        duration_minutes: float,
        micro_phase: str | None = None,
    ) -> float:
        """Gradually lower threshold as time exceeds target for the stage."""
        _MICRO_PHASE_TARGET_MINUTES: dict[str, float] = {
            "1.1": 8, "1.2": 10, "1.3": 5,
            "2.1": 7, "2.2": 7, "2.3": 5,
            "3.1": 10, "3.2": 5, "3.3": 5,
            "4.1": 7, "4.2": 5, "4.3": 7,
        }
        _STAGE_TARGET_MINUTES: dict[str, float] = {
            "discover": 15.0,
            "define": 10.0,
            "develop": 15.0,
            "deliver": 10.0,
        }
        if micro_phase and micro_phase in _MICRO_PHASE_TARGET_MINUTES:
            target = _MICRO_PHASE_TARGET_MINUTES[micro_phase]
        else:
            target = _STAGE_TARGET_MINUTES.get(stage, 15.0)
        if duration_minutes <= target:
            return 0.0
        overtime = duration_minutes - target
        reduction = min(20.0, (overtime / 3.0) * 5.0)
        logger.info(
            "Time pressure: stage=%s, micro_phase=%s, duration=%.1f min, target=%.1f min, reduction=%.1f",
            stage, micro_phase, duration_minutes, target, reduction,
        )
        return reduction

    # ------------------------------------------------------------------
    # Qualitative LLM analysis
    # ------------------------------------------------------------------

    async def _run_qualitative(
        self,
        stage: str,
        canvas: dict,
        chat: list[dict],
        llm_service: Any,
        *,
        project_name: str = "",
        project_description: str = "",
    ) -> dict | None:
        from app.agents.evaluator_qualitative import run_qualitative
        return await run_qualitative(
            stage=stage,
            canvas=canvas,
            chat=chat,
            llm_service=llm_service,
            project_name=project_name,
            project_description=project_description,
        )

    # ------------------------------------------------------------------
    # Stage advancement
    # ------------------------------------------------------------------

    async def _propose_advance(self, stage: str, total_score: float) -> str:
        """Propose stage advancement to humans via chat. Wait up to 60s."""
        self._proposal_pending = True
        self._proposal_agreed = False
        # Use a mutable ref so propose_advance can update threshold on rejection
        threshold_ref = [self._threshold]
        result = await propose_advance(
            stage=stage,
            total_score=total_score,
            project_id=self._project_id,
            agent_id=self._agent_id,
            proposal_event=self._proposal_event,
            get_proposal_agreed=lambda: self._proposal_agreed,
            publish_supervisor_message=self._publish_supervisor_message,
            threshold_ref=threshold_ref,
            blackboard=self._blackboard,
        )
        self._threshold = threshold_ref[0]
        self._proposal_pending = False
        if result.startswith("advanced_to_"):
            self._consecutive_pass_count = 0
            self._blind_spot_challenge_sent = False
        return result

    async def _advance_micro_phase(self, from_phase: str, to_phase: str) -> str:
        """Advance micro phase within the same macro stage (no human proposal needed)."""
        try:
            from app.agents.stage_advancement import advance_micro_phase
            result = await advance_micro_phase(
                project_id=self._project_id,
                agent_id=self._agent_id,
                from_phase=from_phase,
                to_phase=to_phase,
            )
        except Exception as exc:
            logger.error("Micro phase advance failed: %s", exc)
            return "micro_advance_failed"
        if result.startswith("micro_advanced_to_"):
            self._consecutive_pass_count = 0
        return result

    async def _advance_stage(self, current_stage: str) -> str:
        """Directly advance the project to the next stage."""
        result = await advance_stage(
            current_stage=current_stage,
            project_id=self._project_id,
            agent_id=self._agent_id,
            blackboard=self._blackboard,
        )
        if result.startswith("advanced_to_"):
            self._consecutive_pass_count = 0
            self._blind_spot_challenge_sent = False
        return result

    # ------------------------------------------------------------------
    # Chat guidance helpers (delegated to evaluator_guidance.py)
    # ------------------------------------------------------------------

    async def _publish_supervisor_message(self, content_raw: str) -> None:
        from app.agents.evaluator_guidance import publish_supervisor_message
        await publish_supervisor_message(self._project_id, self._agent_id, content_raw)

    async def _publish_blind_spot_challenge(self) -> None:
        from app.agents.evaluator_guidance import publish_blind_spot_challenge
        await publish_blind_spot_challenge(self._project_id, self._agent_id)

    async def _publish_weak_area_guidance(self, weak_areas: list[str]) -> None:
        from app.agents.evaluator_guidance import publish_weak_area_guidance
        text, t, responded = await publish_weak_area_guidance(
            weak_areas=weak_areas,
            project_id=self._project_id,
            agent_id=self._agent_id,
            blackboard=self._blackboard,
            last_guidance_text=self._last_guidance_text,
            last_guidance_time=self._last_guidance_time,
            crew_responded_since_guidance=self._crew_responded_since_guidance,
        )
        self._last_guidance_text = text
        self._last_guidance_time = t
        self._crew_responded_since_guidance = responded

    async def _compute_topic_saturation(
        self,
        stage: str,
        canvas: dict,
        chat: list[dict],
        llm_service: Any,
    ) -> None:
        """Delegate to topic_saturation module."""
        await compute_and_write_topic_saturation(
            blackboard=self._blackboard,
            stage=stage,
            canvas=canvas,
            chat=chat,
            llm_service=llm_service,
        )

    # ------------------------------------------------------------------
    # DB logging
    # ------------------------------------------------------------------

    async def _log_to_db(
        self, stage: str, result: EvaluationResult, *, micro_phase: str | None = None
    ) -> None:
        try:
            async with async_session_factory() as session:
                log = StageEvaluationLog(
                    project_id=self._project_id,
                    stage=stage,
                    quantitative_score=result.quantitative_score,
                    qualitative_score=result.qualitative_score,
                    total_score=result.total_score,
                    threshold=result.threshold,
                    passed=result.passed,
                    consecutive_pass_count=result.consecutive_pass_count,
                    action_taken=result.action_taken,
                    details={
                        "weak_areas": result.weak_areas,
                        "summary": result.summary,
                        "blind_spot_score": result.blind_spot_score,
                        "micro_phase": micro_phase,
                    },
                )
                session.add(log)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to log StageEvaluationLog: %s", exc)
