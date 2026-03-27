from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.db.models.stage_evaluation_log import StageEvaluationLog
from app.db.session import async_session_factory
from app.agents.evaluator_scoring import compute_quantitative

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

# Proposal timeout seconds when humans are present
_PROPOSAL_TIMEOUT_SECONDS = 60.0

# Stage sequence for advance
_STAGE_ORDER = ["discover", "define", "develop", "deliver"]


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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_evaluate(self) -> bool:
        """Return True if enough time has passed since the last evaluation."""
        interval = _EVAL_INTERVALS.get(self._contribution, 30.0)
        return (time.time() - self._last_eval_time) >= interval

    async def evaluate(self, context: dict, llm_service: Any) -> EvaluationResult:
        """Run a full evaluation cycle.

        1. Compute quantitative score
        2. Pre-screen: if quant * 0.4 < threshold * 0.8, skip qualitative
        3. Run qualitative LLM analysis
        4. Compute total, apply decision logic
        5. Log to DB
        """
        self._last_eval_time = time.time()
        stage: str = context.get("current_stage", "discover")
        canvas_state: dict = context.get("canvas_state", {})
        recent_chat: list[dict] = context.get("recent_chat", [])
        seats: list[dict] = context.get("seats", [])

        quant_score = self._compute_quantitative(stage, canvas_state, recent_chat, seats)

        # Stage-specific weighting (Discover: 30:70, others: 40:60)
        if stage == "discover":
            quant_weight, qual_weight = 0.3, 0.7
        else:
            quant_weight, qual_weight = 0.4, 0.6

        # Pre-screening
        qual_score: float | None = None
        qual_result: dict | None = None
        weak_areas: list[str] = []
        summary = ""
        blind_spot_score: float | None = None

        if quant_score * quant_weight >= self._threshold * 0.8:
            qual_result = await self._run_qualitative(stage, canvas_state, recent_chat, llm_service)
            if qual_result:
                qual_score = qual_result.get("overall_score", 0.0)
                weak_areas = qual_result.get("weak_areas", [])
                summary = qual_result.get("summary", "")
                blind_spot_score = qual_result.get("blind_spot_score")
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
            total = quant_score * quant_weight  # Only quantitative component

        passed = total >= self._threshold

        # Blind spot veto (Discover only): block if blind_spot_score < 40
        if stage == "discover" and blind_spot_score is not None and blind_spot_score < 40:
            passed = False
            if not any("盲區分數不足" in w for w in weak_areas):
                weak_areas.insert(0, "盲區分數不足——團隊可能遺漏了重要面向")
            logger.info(
                "Blind spot veto triggered: blind_spot_score=%.1f < 40",
                blind_spot_score,
            )

        if passed:
            self._consecutive_pass_count += 1
        else:
            self._consecutive_pass_count = 0

        # Discover requires at least 3 consecutive passes regardless of contribution
        if stage == "discover":
            required_passes = max(3, _COOLING_COUNTS.get(self._contribution, 2))
        else:
            required_passes = _COOLING_COUNTS.get(self._contribution, 2)

        has_humans = any(s.get("type") == "human" for s in seats)
        action_taken = "none"

        if not passed and weak_areas:
            action_taken = "guided_weak_areas"
            await self._publish_weak_area_guidance(weak_areas)
        elif passed and self._consecutive_pass_count >= required_passes:
            # Discover: blind spot challenge gate (two-pass)
            if stage == "discover" and not self._blind_spot_challenge_sent:
                await self._publish_blind_spot_challenge()
                self._blind_spot_challenge_sent = True
                self._consecutive_pass_count = required_passes - 1
                action_taken = "blind_spot_challenge"
            else:
                if stage == "discover":
                    self._blind_spot_challenge_sent = False
                if has_humans:
                    action_taken = await self._propose_advance(stage, total, context)
                else:
                    action_taken = await self._advance_stage(stage)

        result = EvaluationResult(
            quantitative_score=quant_score,
            qualitative_score=qual_score,
            total_score=total,
            threshold=self._threshold,
            passed=passed,
            weak_areas=weak_areas,
            summary=summary,
            action_taken=action_taken,
            consecutive_pass_count=self._consecutive_pass_count,
            blind_spot_score=blind_spot_score,
        )

        await self._log_to_db(stage, result)
        return result

    def register_human_response(self, agreed: bool) -> None:
        """Called externally when a human responds to a stage advance proposal."""
        self._proposal_agreed = agreed
        self._proposal_event.set()

    # ------------------------------------------------------------------
    # Quantitative scoring (delegated to evaluator_scoring module)
    # ------------------------------------------------------------------

    def _compute_quantitative(
        self,
        stage: str,
        canvas: dict,
        recent_chat: list[dict],
        seats: list[dict],
    ) -> float:
        """Delegate to evaluator_scoring module (see evaluator_scoring.py)."""
        return compute_quantitative(stage, canvas, recent_chat, seats)

    # ------------------------------------------------------------------
    # Qualitative LLM analysis
    # ------------------------------------------------------------------

    async def _run_qualitative(
        self,
        stage: str,
        canvas: dict,
        chat: list[dict],
        llm_service: Any,
    ) -> dict | None:
        stage_names = {
            "discover": "Discover（發現）",
            "define": "Define（定義）",
            "develop": "Develop（發展）",
            "deliver": "Deliver（交付）",
        }
        stage_display = stage_names.get(stage, stage)

        canvas_summary = json.dumps(canvas, ensure_ascii=False, indent=2)
        chat_summary = "\n".join(
            f"[{m.get('time', '')}] {m.get('sender', '')}: {m.get('content', '')}"
            for m in chat[-20:]
        )

        prompt = (
            f"請分析以下 Design Thinking {stage_display} 階段的團隊產出：\n\n"
            f"白板內容：{canvas_summary}\n"
            f"聊天紀錄摘要：{chat_summary}\n\n"
            "請從以下四個面向評分（0-100）：\n"
            "1. 內容多樣性：觀點是否涵蓋多個不同面向？\n"
            "2. 討論深度：每個面向是否有足夠的延伸和探討？\n"
            "3. 收斂程度：團隊是否開始形成共識或重複觀點？\n"
            "4. 盲區檢查：是否有明顯遺漏的重要面向？\n\n"
            "回應格式（只回應 JSON，不要包含其他文字）：\n"
            '{"diversity_score": 0-100, "depth_score": 0-100, '
            '"convergence_score": 0-100, "blind_spot_score": 0-100, '
            '"overall_score": 0-100, "weak_areas": ["面向1", "面向2"], '
            '"summary": "整體評估摘要"}'
        )

        messages = [
            {"role": "system", "content": "你是一位 Design Thinking 工作坊品質評估專家。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await llm_service.chat_completion(
                messages=messages, temperature=0.3, max_tokens=512
            )
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(l for l in lines if not l.startswith("```")).strip()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Qualitative evaluation LLM call failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Stage advancement
    # ------------------------------------------------------------------

    async def _propose_advance(self, stage: str, total_score: float, context: dict) -> str:
        """Propose stage advancement to humans via chat. Wait up to 60s for response."""
        stage_names = {"discover": "發現", "define": "定義", "develop": "發展", "deliver": "交付"}
        current_name = stage_names.get(stage, stage)
        next_stage = self._get_next_stage(stage)
        if not next_stage:
            return "already_final_stage"

        next_name = stage_names.get(next_stage, next_stage)

        await self._publish_supervisor_message(
            f"我評估目前的 {current_name} 階段已經完成得相當充分（評分：{total_score:.0f} 分）。"
            f"大家覺得可以進入下一個 {next_name} 階段了嗎？"
        )

        self._proposal_pending = True
        self._proposal_event.clear()
        self._proposal_agreed = False

        try:
            await asyncio.wait_for(self._proposal_event.wait(), timeout=_PROPOSAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.info("Stage advance proposal timed out — asking again")
            return "proposal_timeout"

        if self._proposal_agreed:
            return await self._advance_stage(stage)
        else:
            self._threshold += 10.0
            logger.info(
                "Stage advance proposal rejected — threshold raised to %.1f",
                self._threshold,
            )
            return "proposal_rejected"

    async def _advance_stage(self, current_stage: str) -> str:
        """Directly advance the project to the next stage."""
        next_stage = self._get_next_stage(current_stage)
        if not next_stage:
            logger.info("Already at final stage: %s", current_stage)
            return "already_final_stage"

        try:
            async with async_session_factory() as session:
                from sqlalchemy import update
                from app.db.models.project import Project
                from app.db.models.stage_history import StageHistory  # type: ignore[attr-defined]
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)

                # Close current stage history entry
                await session.execute(
                    update(StageHistory)
                    .where(
                        StageHistory.project_id == self._project_id,
                        StageHistory.stage == current_stage,
                        StageHistory.ended_at.is_(None),
                    )
                    .values(ended_at=now)
                )

                # Update project stage
                await session.execute(
                    update(Project)
                    .where(Project.id == self._project_id)
                    .values(current_stage=next_stage, updated_at=now)
                )

                # Open new stage history entry
                sh = StageHistory(
                    project_id=self._project_id,
                    stage=next_stage,
                    started_at=now,
                )
                session.add(sh)
                await session.commit()

            # Broadcast stage change event
            from app.events.types import StageChangedEvent
            from app.events.bus import event_bus

            event = StageChangedEvent(
                project_id=self._project_id,
                from_stage=current_stage,
                to=next_stage,
                triggered_by="ai_evaluator",
            )
            await event_bus.publish(event)

            self._consecutive_pass_count = 0
            self._blind_spot_challenge_sent = False
            logger.info(
                "Project %s advanced: %s → %s",
                self._project_id,
                current_stage,
                next_stage,
            )
            return f"advanced_to_{next_stage}"
        except Exception as exc:
            logger.error("Failed to advance stage: %s", exc)
            return "advance_failed"

    @staticmethod
    def _get_next_stage(current: str) -> str | None:
        try:
            idx = _STAGE_ORDER.index(current)
            if idx + 1 < len(_STAGE_ORDER):
                return _STAGE_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    # ------------------------------------------------------------------
    # Chat guidance helpers
    # ------------------------------------------------------------------

    async def _publish_supervisor_message(self, content_raw: str) -> None:
        """Publish a Supervisor chat message (with Chinese conversion)."""
        from app.events.types import ChatMessageEvent
        from app.events.bus import event_bus
        from app.chinese.converter import chinese_converter

        event = ChatMessageEvent(
            project_id=self._project_id,
            sender_id=self._agent_id,
            sender_type="ai",
            sender_name="Supervisor",
            content=chinese_converter.convert(content_raw),
        )
        await event_bus.publish(event)

    async def _publish_blind_spot_challenge(self) -> None:
        """Send a 'final call' asking team to identify missed perspectives."""
        try:
            await self._publish_supervisor_message(
                "在我們準備往下走之前，讓我確認一下——"
                "我們是不是還漏了什麼重要的面向？"
                "還有沒有我們沒想到的？"
            )
            logger.info("Published blind spot challenge for project %s", self._project_id)
        except Exception as exc:
            logger.error("Failed to publish blind spot challenge: %s", exc)

    async def _publish_weak_area_guidance(self, weak_areas: list[str]) -> None:
        """Publish a chat message guiding the team to improve weak areas (spec §4.4)."""
        if not weak_areas:
            return
        try:
            primary_area = weak_areas[0]
            await self._publish_supervisor_message(
                f"我覺得我們在 {primary_area} 方面可以再深入探討一些，"
                f"這樣能讓這個階段的產出更紮實。大家有什麼想法嗎？"
            )
            logger.info("Published weak-area guidance for project %s: %s", self._project_id, primary_area)
        except Exception as exc:
            logger.error("Failed to publish weak-area guidance: %s", exc)

    # ------------------------------------------------------------------
    # DB logging
    # ------------------------------------------------------------------

    async def _log_to_db(self, stage: str, result: EvaluationResult) -> None:
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
                    },
                )
                session.add(log)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to log StageEvaluationLog: %s", exc)
