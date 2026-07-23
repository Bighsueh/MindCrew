"""Timer service — Spec 15 §4.

老師可控（pause / resume / extend / skip），組員看得到但不能改。
所有 op 寫進 project.timer_state JSONB。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.db.models.project import Project
from app.db.session import async_session_factory
from app.timer.calculator import (
    DEFAULT_PRESET,
    compute_sub_phase_budgets,
    get_phase_budget_seconds,
    load_preset,
)
from app.timer.schemas import TimerConfig, TimerState, now_iso

logger = logging.getLogger(__name__)


class TimerService:
    """Timer 控制服務。所有方法都是 async + class-level（無 instance state）。"""

    # ------------------------------------------------------------------
    # Config 初始化
    # ------------------------------------------------------------------

    @staticmethod
    async def initialize_project(
        project_id: UUID,
        config: TimerConfig | None = None,
    ) -> TimerConfig:
        """建立專案時呼叫，寫入 timer_config + 空 state。"""
        if config is None:
            config = DEFAULT_PRESET

        # Phase 39 (spec/16 §2.1 v1.1): 前端對已知 preset 只送部分欄位
        # （total_session_minutes + macro_budgets + intensity + preset_id），
        # 缺 sub_phase_overrides。對已知 canonical preset 且未帶 overrides 時，
        # 用後端權威 preset（含 intensity + 縮放後 sub_phase_overrides）取代，
        # 確保短場（40/60/90）的調校預算與 intensity 真正生效。custom 不受影響。
        from app.timer.calculator import PRESETS

        if (
            config.preset_id in PRESETS
            and not config.sub_phase_overrides
        ):
            config = load_preset(config.preset_id)

        # Phase 42 B1 (spec/16 §2.1/§4.4 v2.0)：暖場固定軟 3／硬 5 分、所有 preset
        # （含 custom）相同——不論呼叫端送什麼，一律強制覆寫 warmup macro 預算與
        # 0.0a override 為硬上限 5 分（#19 唯一例外；防 custom / 舊前端帶舊值）。
        from app.timer.calculator import WARMUP_HARD_BUDGET_MINUTES

        config = config.model_copy(
            update={
                "macro_budgets": {
                    **config.macro_budgets,
                    "warmup": WARMUP_HARD_BUDGET_MINUTES,
                },
                "sub_phase_overrides": {
                    **config.sub_phase_overrides,
                    "0.0a": WARMUP_HARD_BUDGET_MINUTES,
                },
            }
        )

        async with async_session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(
                    timer_config=config.model_dump(),
                    timer_state=TimerState().model_dump(),
                )
            )
            await session.commit()
        logger.info("Timer initialized project=%s preset=%s", project_id, config.preset_id)
        return config

    # ------------------------------------------------------------------
    # Phase 切換
    # ------------------------------------------------------------------

    @staticmethod
    async def start_phase(project_id: UUID, sub_phase_id: str) -> TimerState:
        """advance_sub_phase 呼叫：切換到新 sub_phase 時呼叫，重置時戳。"""
        async with async_session_factory() as session:
            project = (await session.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one_or_none()
            if project is None:
                return TimerState()

            state = TimerState(
                current_sub_phase=sub_phase_id,
                phase_started_at=now_iso(),
                paused_at=None,
                total_paused_seconds=0,
                warnings_fired=[],
            )
            # 同步寫頂層 ``project.current_sub_phase`` 欄位（不只 timer_state JSON）。
            # progression_watcher / advance 流程讀的是頂層欄位；過去只寫 JSON 導致
            # 暖場時頂層欄位為 NULL → watcher 永不開工（keystone 卡 1.1a 根因）。
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(
                    timer_state=state.model_dump(),
                    current_sub_phase=sub_phase_id,
                )
            )
            await session.commit()

        # Phase 35 (spec/16 §6.5.5): 切換 sub_phase 時清掉舊 phase 的 supervisor
        # fired triggers，讓 B3* 能在新 sub_phase 重新 fire。
        try:
            from app.agents.supervisor.dedup import reset_fired_triggers
            await reset_fired_triggers(project_id, sub_phase=None)
        except Exception:
            logger.debug("reset_fired_triggers on start_phase failed", exc_info=True)

        logger.info(
            "Timer phase started project=%s sub_phase=%s",
            project_id, sub_phase_id,
        )
        return state

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    @staticmethod
    async def pause(project_id: UUID, reason: str = "teacher") -> TimerState | None:
        """暫停 timer。``reason`` 區分來源（"teacher" 老師手動／"llm_down" fail-stop，
        spec 20 §13.3）；既有老師端呼叫不帶參數＝預設 "teacher"，行為不變。"""
        state = await TimerService.get_state(project_id)
        if state is None or state.is_paused():
            return state
        new_state = state.model_copy(
            update={"paused_at": now_iso(), "pause_reason": reason}
        )
        await TimerService._save_state(project_id, new_state)
        logger.info("Timer paused project=%s reason=%s", project_id, reason)
        return new_state

    @staticmethod
    async def resume(project_id: UUID) -> TimerState | None:
        state = await TimerService.get_state(project_id)
        if state is None or not state.is_paused():
            return state
        paused_at = state.parse_paused_at()
        added = 0
        if paused_at is not None:
            added = int(
                (datetime.now(timezone.utc) - paused_at).total_seconds()
            )
        new_state = state.model_copy(update={
            "paused_at": None,
            "pause_reason": None,
            "total_paused_seconds": state.total_paused_seconds + max(0, added),
        })
        await TimerService._save_state(project_id, new_state)
        logger.info("Timer resumed project=%s added_pause=%d", project_id, added)
        return new_state

    # ------------------------------------------------------------------
    # Extend / Skip
    # ------------------------------------------------------------------

    @staticmethod
    async def extend(project_id: UUID, additional_minutes: int) -> TimerConfig | None:
        """+N 分鐘到當前 sub_phase。寫入 sub_phase_overrides。"""
        config = await TimerService.get_config(project_id)
        state = await TimerService.get_state(project_id)
        if config is None or state is None or not state.current_sub_phase:
            return config

        cur = state.current_sub_phase
        current_secs = get_phase_budget_seconds(config, cur)
        new_mins = max(1, current_secs // 60 + additional_minutes)
        new_overrides = dict(config.sub_phase_overrides)
        new_overrides[cur] = new_mins
        new_config = config.model_copy(update={"sub_phase_overrides": new_overrides})
        await TimerService._save_config(project_id, new_config)
        logger.info(
            "Timer extended project=%s sub_phase=%s +%dm (now %dm)",
            project_id, cur, additional_minutes, new_mins,
        )
        return new_config

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    async def get_state(project_id: UUID) -> TimerState | None:
        async with async_session_factory() as session:
            project = (await session.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one_or_none()
            if project is None:
                return None
            raw = project.timer_state or {}
            try:
                return TimerState.model_validate(raw)
            except Exception:
                return TimerState()

    @staticmethod
    async def get_config(project_id: UUID) -> TimerConfig | None:
        async with async_session_factory() as session:
            project = (await session.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one_or_none()
            if project is None:
                return None
            raw = project.timer_config or {}
            if not raw:
                return DEFAULT_PRESET
            try:
                return TimerConfig.model_validate(raw)
            except Exception:
                return DEFAULT_PRESET

    @staticmethod
    async def get_used_pct(project_id: UUID) -> float:
        """Spec 15 §7：給 Supervisor B3 trigger 用。"""
        config = await TimerService.get_config(project_id)
        state = await TimerService.get_state(project_id)
        if config is None or state is None or not state.current_sub_phase:
            return 0.0
        budget = get_phase_budget_seconds(config, state.current_sub_phase)
        if budget <= 0:
            return 0.0
        used = TimerService._compute_used_seconds(state)
        return min(used / budget * 100.0, 200.0)  # cap for sanity

    @staticmethod
    async def get_used_seconds(project_id: UUID) -> int | None:
        """本關已用秒數（已扣暫停）；timer 未初始化 / 未起算回 None。

        Phase 42 B1：暖場「軟 3 分檢核點」需要絕對秒數（warmup_exit 消費），
        與 get_used_pct 同一計算來源。
        """
        state = await TimerService.get_state(project_id)
        if state is None or not state.phase_started_at:
            return None
        return TimerService._compute_used_seconds(state)

    @staticmethod
    def _compute_used_seconds(state: TimerState) -> int:
        started = state.parse_started_at()
        if started is None:
            return 0
        now = datetime.now(timezone.utc)
        elapsed = int((now - started).total_seconds())
        # 扣除暫停時間
        paused_seconds = state.total_paused_seconds
        if state.is_paused():
            paused_at = state.parse_paused_at()
            if paused_at:
                paused_seconds += int((now - paused_at).total_seconds())
        return max(0, elapsed - paused_seconds)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _save_state(project_id: UUID, state: TimerState) -> None:
        async with async_session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(timer_state=state.model_dump())
            )
            await session.commit()

    @staticmethod
    async def _save_config(project_id: UUID, config: TimerConfig) -> None:
        async with async_session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(timer_config=config.model_dump())
            )
            await session.commit()

    @staticmethod
    async def fire_warning(
        project_id: UUID, threshold_pct: int,
    ) -> bool:
        """記錄 warning 已 fire，回 True 表示首次 fire（需廣播）。"""
        state = await TimerService.get_state(project_id)
        if state is None or threshold_pct in state.warnings_fired:
            return False
        new_fired = list(state.warnings_fired) + [threshold_pct]
        new_state = state.model_copy(update={"warnings_fired": new_fired})
        await TimerService._save_state(project_id, new_state)
        return True
