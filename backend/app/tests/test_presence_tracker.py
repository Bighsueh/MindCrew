"""Tests for the Human Presence Gate (PresenceTracker + BaseAgent integration)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.ws.presence_tracker import PresenceTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker() -> PresenceTracker:
    """Return a fresh PresenceTracker per test (not the global singleton)."""
    return PresenceTracker()


# ---------------------------------------------------------------------------
# PresenceTracker unit tests
# ---------------------------------------------------------------------------


class TestPresenceTracker:
    """Core counting, event, and grace-period behaviour."""

    def test_new_event_starts_cleared(self, tracker: PresenceTracker) -> None:
        pid = uuid4()
        event = tracker.get_presence_event(pid)
        assert not event.is_set()
        assert not tracker.is_human_present(pid)

    def test_connect_sets_event(self, tracker: PresenceTracker) -> None:
        pid = uuid4()
        event = tracker.get_presence_event(pid)
        tracker.on_human_connect(pid)
        assert event.is_set()
        assert tracker.is_human_present(pid)

    def test_multiple_connects_and_partial_disconnect(
        self, tracker: PresenceTracker
    ) -> None:
        pid = uuid4()
        event = tracker.get_presence_event(pid)
        tracker.on_human_connect(pid)
        tracker.on_human_connect(pid)
        assert tracker._counts[str(pid)] == 2

        tracker.on_human_disconnect(pid)
        # Still one human → event stays set
        assert event.is_set()
        assert tracker.is_human_present(pid)

    def test_disconnect_below_zero_ignored(
        self, tracker: PresenceTracker
    ) -> None:
        pid = uuid4()
        # Should not raise or go negative
        tracker.on_human_disconnect(pid)
        assert tracker._counts.get(str(pid), 0) == 0

    @pytest.mark.asyncio
    async def test_grace_period_clears_event(
        self, tracker: PresenceTracker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After the last human disconnects, the event clears after grace period."""
        import app.ws.presence_tracker as mod

        monkeypatch.setattr(mod, "_GRACE_PERIOD_SECONDS", 0.1)

        pid = uuid4()
        event = tracker.get_presence_event(pid)
        tracker.on_human_connect(pid)
        assert event.is_set()

        tracker.on_human_disconnect(pid)
        # Event still set (grace period hasn't expired)
        assert event.is_set()

        # Wait for grace period to expire
        await asyncio.sleep(0.2)
        assert not event.is_set()
        assert not tracker.is_human_present(pid)

    @pytest.mark.asyncio
    async def test_reconnect_cancels_grace_timer(
        self, tracker: PresenceTracker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reconnecting before grace expires keeps the event set."""
        import app.ws.presence_tracker as mod

        monkeypatch.setattr(mod, "_GRACE_PERIOD_SECONDS", 0.3)

        pid = uuid4()
        event = tracker.get_presence_event(pid)
        tracker.on_human_connect(pid)
        tracker.on_human_disconnect(pid)

        # Reconnect before grace fires
        await asyncio.sleep(0.1)
        tracker.on_human_connect(pid)

        # Wait past original grace deadline
        await asyncio.sleep(0.3)
        assert event.is_set()

    def test_separate_projects_independent(
        self, tracker: PresenceTracker
    ) -> None:
        pid_a = uuid4()
        pid_b = uuid4()
        event_a = tracker.get_presence_event(pid_a)
        event_b = tracker.get_presence_event(pid_b)

        tracker.on_human_connect(pid_a)
        assert event_a.is_set()
        assert not event_b.is_set()

    def test_get_presence_event_idempotent(
        self, tracker: PresenceTracker
    ) -> None:
        pid = uuid4()
        e1 = tracker.get_presence_event(pid)
        e2 = tracker.get_presence_event(pid)
        assert e1 is e2


# ---------------------------------------------------------------------------
# _wait_for_any unit tests
# ---------------------------------------------------------------------------


class TestWaitForAny:
    """Test the helper used by BaseAgent to wait on presence OR stop."""

    @pytest.mark.asyncio
    async def test_returns_immediately_if_set(self) -> None:
        from app.agents.base_agent import _wait_for_any

        e1 = asyncio.Event()
        e2 = asyncio.Event()
        e1.set()
        # Should not block
        await asyncio.wait_for(_wait_for_any(e1, e2), timeout=0.1)

    @pytest.mark.asyncio
    async def test_blocks_until_one_is_set(self) -> None:
        from app.agents.base_agent import _wait_for_any

        e1 = asyncio.Event()
        e2 = asyncio.Event()

        async def _set_later() -> None:
            await asyncio.sleep(0.05)
            e2.set()

        asyncio.create_task(_set_later())
        await asyncio.wait_for(_wait_for_any(e1, e2), timeout=0.5)

    @pytest.mark.asyncio
    async def test_times_out_when_none_set(self) -> None:
        from app.agents.base_agent import _wait_for_any

        e1 = asyncio.Event()
        e2 = asyncio.Event()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(_wait_for_any(e1, e2), timeout=0.1)
