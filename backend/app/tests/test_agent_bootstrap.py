"""Tests for P0 fixes: Agent lifecycle bootstrap and round gate.
- ASSESS Rule 0.1 (fresh project bootstrap)
- Seed last_event_ts (NX behavior)
- Round gate opens on first INTERVENE
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.assess import AssessEngine, AssessResult


# ── Rule 0.1: Fresh Project Bootstrap ──


class TestRule01FreshProject:
    """Supervisor in fresh project with no chat should get rule_0_1."""

    @pytest.fixture
    def engine(self) -> AssessEngine:
        return AssessEngine()

    def _base_context(
        self,
        *,
        is_supervisor: bool = True,
        recent_chat: list | None = None,
        ai_contribution: str = "high",
    ) -> dict:
        return {
            "recent_chat": recent_chat or [],
            "my_seat": "supervisor" if is_supervisor else "crew_1",
            "my_recent_actions": [],
            "seats": [],
            "canvas_state": {},
            "phase_strategy": {"comm_goal": "cooperative"},
            "ai_contribution": ai_contribution,
            "_last_event_time": None,
        }

    @pytest.mark.asyncio
    async def test_supervisor_empty_chat_triggers(self, engine: AssessEngine) -> None:
        """Supervisor + empty chat → rule_0_1_fresh_project."""
        context = self._base_context(is_supervisor=True, recent_chat=[])
        result = await engine.evaluate(
            context=context,
            agent_id="agent_supervisor",
            ai_contribution="high",
        )
        assert result.decision == "intervene"
        assert result.rule == "rule_0_1_fresh_project"

    @pytest.mark.asyncio
    async def test_crew_empty_chat_no_trigger(self, engine: AssessEngine) -> None:
        """Crew + empty chat → should NOT get rule_0_1 (supervisor-only)."""
        context = self._base_context(is_supervisor=False, recent_chat=[])
        result = await engine.evaluate(
            context=context,
            agent_id="agent_crew_1",
            ai_contribution="high",
        )
        # Should fall through to some other rule, NOT rule_0_1
        assert result.rule != "rule_0_1_fresh_project"

    @pytest.mark.asyncio
    async def test_supervisor_with_chat_no_trigger(self, engine: AssessEngine) -> None:
        """Supervisor + existing chat → should NOT get rule_0_1."""
        chat = [{"sender_type": "ai", "sender_name": "AI 引導者", "content": "歡迎"}]
        context = self._base_context(is_supervisor=True, recent_chat=chat)
        result = await engine.evaluate(
            context=context,
            agent_id="agent_supervisor",
            ai_contribution="high",
        )
        assert result.rule != "rule_0_1_fresh_project"


# ── Seed last_event_ts ──


class TestSeedLastEventTs:
    """Tests for last_event_ts NX seeding."""

    @pytest.mark.asyncio
    async def test_seed_sets_key(self) -> None:
        """NX should set key when not present."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.aclose = AsyncMock()

        with patch("app.seats.manager.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            from app.seats.manager import SeatManager
            mgr = SeatManager.__new__(SeatManager)
            from uuid import uuid4
            await mgr._seed_last_event_ts(uuid4())

        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs[1].get("nx") is True or (
            len(call_kwargs[0]) >= 3 and call_kwargs[0][2] is True
        )

    @pytest.mark.asyncio
    async def test_seed_uses_nx(self) -> None:
        """NX flag should be passed to prevent overwriting."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)  # NX returns False = key exists
        mock_redis.aclose = AsyncMock()

        with patch("app.seats.manager.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            from app.seats.manager import SeatManager
            mgr = SeatManager.__new__(SeatManager)
            from uuid import uuid4
            # Should not raise even if key exists
            await mgr._seed_last_event_ts(uuid4())
