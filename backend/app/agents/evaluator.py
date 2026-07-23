from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.blackboard import BlackboardManager
from app.agents.llm_context import LLMCallContext
from app.db.models.stage_evaluation_log import StageEvaluationLog
from app.db.session import async_session_factory
from app.agents.context_buffer import get_evaluator_canvas
from app.agents.evaluator_scoring import compute_quantitative
from app.agents.topic_saturation import compute_and_write_topic_saturation
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

# Phase 42 B1：暖場「45s 最低停留＋真人 ≥15 字放行」模型移除——退場改
# (達標 AND 全員參與) OR 硬上限（G02／spec 28 v2.1 §5.1：live 實證 crew 失能時
# 舊字面「(達標 OR 上限) AND 全員」會軟卡、與 §5.3 防死鎖矛盾），判定在
# progression/warmup_exit.py。（Phase 42 補正 R5：本註解原寫舊公式，更正。）
# Phase 42 A1：v4.18 的無引導者邊界 70% 提前放行閥已移除（spec 04-06 §5.8 v4.25）——
# 防死鎖職責統一由「組長 time-box 誠實收尾」與 progression watcher 兜底覆蓋。


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
    """Supervisor-only component: evaluates stage completion and feeds signals.

    Uses both quantitative metrics (no LLM) and qualitative LLM analysis.
    Phase 42 A1（spec 04-06 §5.8 v4.25）：不再靜默跨 micro/macro 邊界，
    評估通過後改寫「邊界訊號」進組長的本關訊號面板，由組長宣布推進；
    暖場（_evaluate_warmup）自 B1 起同此模型（三情境訊號，spec 28 v2.0 §5）。
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

    async def evaluate(
        self, context: dict, llm_service: Any, *, llm_ctx: LLMCallContext
    ) -> EvaluationResult:
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

        # 暖場 macro stage:不跑 discover 計分(沒 artifact 會卡死)。改用「人有參與 + 最低停留」
        # 決定推進;全 AI 不卡死;time-box 為安全閥(避免人 AFK 永久卡住,並標記未達標)。
        if stage == "warmup":
            return await self._evaluate_warmup(recent_chat)

        # Track if any Crew responded since last guidance (for dedup).
        # Phase 19: also recognise persona display names (any AI seat that is
        # not the supervisor counts as a crew response).
        if not self._crew_responded_since_guidance:
            crew_names: list[str] = ["crew", "同理心", "結構化", "創意", "可行性"]
            for s in seats:
                role = s.get("role") or s.get("seat_role")
                if not role or role == "supervisor":
                    continue
                if s.get("type") != "ai" and s.get("occupant_type") != "ai":
                    continue
                persona = s.get("persona") if isinstance(s, dict) else None
                if isinstance(persona, dict):
                    name = str(persona.get("name", "")).strip().lower()
                    if name:
                        crew_names.append(name)
                dn = s.get("display_name") or ""
                if dn:
                    crew_names.append(str(dn).lower())
            for msg in recent_chat[-5:]:
                sender = msg.get("sender", "").lower()
                if any(r in sender for r in crew_names):
                    self._crew_responded_since_guidance = True
                    break

        if micro_phase:
            from app.agents.micro_phase_scoring import compute_micro_phase_quantitative
            quant_score = await compute_micro_phase_quantitative(micro_phase, canvas_state, recent_chat, seats, llm_service=llm_service, llm_ctx=llm_ctx)
        else:
            quant_score = await self._compute_quantitative(stage, canvas_state, recent_chat, seats, llm_service=llm_service, llm_ctx=llm_ctx)

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
                llm_ctx=llm_ctx,
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

        # v4.15 一致性 guard：micro 內細格未走完前不跨 micro/macro 邊界。
        # 讓 progression_watcher 先把 current_sub_phase 走到該 micro 的最後一格。
        current_sub_phase = context.get("current_sub_phase")
        _at_micro_end = True
        if micro_phase and current_sub_phase:
            from app.stages.sub_phases import SUB_PHASES, SUB_PHASE_ORDER
            _sp = SUB_PHASES.get(current_sub_phase)
            if _sp is not None and _sp.parent_micro_phase == micro_phase:
                _subs = [
                    s for s in SUB_PHASE_ORDER
                    if SUB_PHASES[s].parent_micro_phase == micro_phase
                ]
                _at_micro_end = (not _subs) or (_subs[-1] == current_sub_phase)

        # Phase 42 A1（spec 04-06 §5.8 v4.25）：Evaluator 不再自行跨界——
        # v4.18 無引導者 70% 邊界閥與 propose_advance 60s 同意窗一併移除。
        # 評估通過＋已在 micro 末端 → 寫「邊界訊號」給組長（本關訊號面板），
        # 由組長宣布推進、系統執行；組長失能由 progression watcher 兜底。
        action_taken = "none"

        if not passed and weak_areas:
            action_taken = "guided_weak_areas"
            await self._publish_weak_area_guidance(weak_areas)
        elif passed and self._consecutive_pass_count >= required_passes:
            if micro_phase and not _at_micro_end:
                # 細格尚未走到 micro 末端 → 本輪不給邊界訊號（不重置 consecutive_pass）。
                action_taken = "await_sub_phase_walk"
            # Discover: blind spot challenge gate (two-pass) — only with humans, macro stage mode
            elif (
                stage == "discover"
                and not micro_phase
                and not self._blind_spot_challenge_sent
                and has_humans
            ):
                await self._publish_blind_spot_challenge()
                self._blind_spot_challenge_sent = True
                self._consecutive_pass_count = required_passes - 1
                action_taken = "blind_spot_challenge"
            else:
                action_taken = "boundary_signal"

        # 每輪評估都更新邊界訊號（最新判定供面板渲染；best-effort）。
        try:
            from app.progression.boundary_signal import set_boundary_signal

            await set_boundary_signal(
                self._project_id,
                micro_phase=micro_phase,
                sub_phase=current_sub_phase,
                ready=(action_taken == "boundary_signal"),
                passed=passed,
                total_score=total,
                weak_areas=weak_areas,
            )
        except Exception:
            logger.debug("boundary signal write failed", exc_info=True)

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
        await self._compute_topic_saturation(stage, canvas_state, recent_chat, llm_service, llm_ctx)

        return result

    async def _compute_quantitative(
        self, stage: str, canvas: dict, recent_chat: list[dict], seats: list[dict],
        llm_service: Any = None,
        llm_ctx: LLMCallContext | None = None,
    ) -> float:
        return await compute_quantitative(stage, canvas, recent_chat, seats, llm_service=llm_service, llm_ctx=llm_ctx)

    @staticmethod
    def _time_pressure_adjustment(
        stage: str,
        duration_minutes: float,
        micro_phase: str | None = None,
    ) -> float:
        """Gradually lower threshold as time exceeds target for the stage."""
        # Phase 42 C1：對齊新 6 桶（舊 1.3 隨 Persona 移除；1.1=1.1a–1.1d、
        # 2.2=2.2–2.4、2.3=2.5–2.7）。值為時間壓力調整的經驗參考，
        # 非 time-box（上限由 timer 比例分配管，spec 16 v2.0 §2.1）。
        _MICRO_PHASE_TARGET_MINUTES: dict[str, float] = {
            "1.1": 10, "1.2": 8,
            "2.1": 5, "2.2": 8, "2.3": 7,
        }
        _STAGE_TARGET_MINUTES: dict[str, float] = {
            "discover": 15.0,
            "define": 10.0,
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
        llm_ctx: LLMCallContext | None = None,
    ) -> dict | None:
        from app.agents.evaluator_qualitative import run_qualitative
        return await run_qualitative(
            stage=stage,
            canvas=canvas,
            chat=chat,
            llm_service=llm_service,
            project_name=project_name,
            project_description=project_description,
            llm_ctx=llm_ctx,
        )

    # ------------------------------------------------------------------
    # Stage advancement
    # ------------------------------------------------------------------

    # Phase 42 A1：_propose_advance（60s 同意窗包裝）與 _advance_micro_phase
    # （靜默跨 micro）已移除——邊界推進改由組長宣布（act `advance_sub_phase`），
    # 執行路徑見 progression/advance_router.py。

    async def _evaluate_warmup(self, recent_chat: list[dict]) -> EvaluationResult:
        """暖場退場訊號（Phase 42 B1，spec 28 v2.0 §5）：算訊號、餵組長，不再自行推進。

        退場公式（§5.1，G02 v2.1 修訂）＝(達團隊目標 AND 全員參與) OR 硬上限 5 分到，
        判定彙整於 ``progression.warmup_exit.warmup_status``。本方法每輪把判定寫進
        邊界訊號（組長的本關訊號面板據此渲染三情境），常態推進＝組長宣布收尾並
        act `advance_sub_phase`（橋接必經、由推進迴路結構保證）；組長失能時
        watcher 於硬上限後樣板兜底。舊「真人 ≥15 字＋45s 放行」模型已移除（§5.1）。
        """
        pid = self._project_id
        from app.progression.warmup_exit import warmup_status

        status = await warmup_status(pid)
        action = "boundary_signal" if status.ready else "none"

        # 邊界訊號寫入：暖場面板（signal_panel._warmup_panel）直接讀 warmup_status、
        # 不消費此訊號——保留寫入是為了與其他格的 evaluator 行為對齊＋live 偵錯時
        # 可從 Redis 直接檢視暖場判定（A1 驗收即以此為證據管道）。
        try:
            from app.progression.boundary_signal import set_boundary_signal

            await set_boundary_signal(
                pid,
                micro_phase="0.0",
                sub_phase="0.0a",
                ready=status.ready,
                passed=status.ready,
                total_score=0.0,
                weak_areas=list(status.missing_zh),
            )
        except Exception:
            logger.debug("warmup boundary signal write failed", exc_info=True)

        if status.ready:
            summary = (
                f"暖場可收尾（{status.note_count}/{status.goal} 張"
                f"{'、已達標' if status.goal_reached else '、硬上限到'}）→ 等組長宣布收尾"
            )
        else:
            summary = "暖場進行中：" + ("；".join(status.missing_zh) or "等待訊號")
        return EvaluationResult(
            quantitative_score=0.0,
            qualitative_score=None,
            total_score=0.0,
            threshold=0.0,
            passed=status.ready,
            weak_areas=list(status.missing_zh),
            summary=summary,
            action_taken=action,
            consecutive_pass_count=self._consecutive_pass_count,
        )

    # Phase 42 B1：_advance_stage 移除——evaluator 全面不再直接推進（含暖場）。
    # 推進執行路徑統一在 progression/advance_router.py（組長宣布 / watcher 兜底）。

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
        llm_ctx: LLMCallContext | None = None,
    ) -> None:
        """Delegate to topic_saturation module."""
        await compute_and_write_topic_saturation(
            blackboard=self._blackboard,
            stage=stage,
            canvas=canvas,
            chat=chat,
            llm_service=llm_service,
            llm_ctx=llm_ctx,
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
