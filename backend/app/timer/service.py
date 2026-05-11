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
    DEFAULT_2HR_PRESET,
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
            config = DEFAULT_2HR_PRESET

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
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(timer_state=state.model_dump())
            )
            await session.commit()

        logger.info(
            "Timer phase started project=%s sub_phase=%s",
            project_id, sub_phase_id,
        )
        return state

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    @staticmethod
    async def pause(project_id: UUID) -> TimerState | None:
        state = await TimerService.get_state(project_id)
        if state is None or state.is_paused():
            return state
        new_state = state.model_copy(update={"paused_at": now_iso()})
        await TimerService._save_state(project_id, new_state)
        logger.info("Timer paused project=%s", project_id)
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
                return DEFAULT_2HR_PRESET
            try:
                return TimerConfig.model_validate(raw)
            except Exception:
                return DEFAULT_2HR_PRESET

    @staticmethod
    async def get_used_pct(project_id: UUID) -> float:
        """Spec 15 §7：給 Supervisor B3/B11 trigger 用。"""
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
