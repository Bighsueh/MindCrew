from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncContextManager
from uuid import UUID

logger = logging.getLogger(__name__)

# Spec §3.2: queue timeout before auto-abandon
_QUEUE_TIMEOUT_SECONDS = 30.0

# Rate limits (spec §3): per-project and global RPM
_PROJECT_RPM_LIMIT = 30
_GLOBAL_RPM_LIMIT = 300
_RPM_WINDOW_SECONDS = 60.0


@dataclass
class _QueueEntry:
    agent_id: str
    is_supervisor: bool
    enqueued_at: float = field(default_factory=time.time)
    event: asyncio.Event = field(default_factory=asyncio.Event)


class _ProjectQueue:
    """Serialises AI agent actions within a single project."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._queue: deque[_QueueEntry] = deque()
        self._current: str | None = None  # agent_id currently holding the lock
        # Round gate: blocks crew until supervisor completes first action
        self._supervisor_first_round_done: bool = False
        self._round_gate: asyncio.Event = asyncio.Event()

    async def acquire(self, agent_id: str, is_supervisor: bool) -> bool:
        """Request exclusive action rights.

        Returns True if acquired within the queue timeout; False if abandoned.
        Supervisor entries are promoted to the front of the queue.
        """
        entry = _QueueEntry(agent_id=agent_id, is_supervisor=is_supervisor)

        # Insert supervisor at front, crew at back (spec §3.2)
        # Supervisor preempts: evict waiting crew to speak sooner
        async with self._lock:
            if is_supervisor:
                evicted = [e for e in self._queue if not e.is_supervisor]
                if evicted:
                    self._queue = deque(e for e in self._queue if e.is_supervisor)
                    logger.debug(
                        "Supervisor %s preempted %d crew entries",
                        agent_id,
                        len(evicted),
                    )
                self._queue.appendleft(entry)
            else:
                self._queue.append(entry)

        # Wait until we are at the front
        deadline = time.time() + _QUEUE_TIMEOUT_SECONDS
        while True:
            async with self._lock:
                if self._queue and self._queue[0].agent_id == agent_id and self._queue[0] is entry:
                    # We are next; acquire
                    self._queue.popleft()
                    self._current = agent_id
                    return True

            remaining = deadline - time.time()
            if remaining <= 0:
                # Timed out — remove from queue and abandon
                async with self._lock:
                    try:
                        self._queue.remove(entry)
                    except ValueError:
                        pass
                logger.warning(
                    "Agent %s abandoned queue after %ss timeout",
                    agent_id,
                    _QUEUE_TIMEOUT_SECONDS,
                )
                return False

            await asyncio.sleep(0.1)

    def queue_depth(self) -> int:
        """Return the number of agents queued or acting."""
        return len(self._queue) + (1 if self._current else 0)

    def mark_supervisor_first_round_done(self) -> None:
        """Called after Supervisor completes its first action."""
        self._supervisor_first_round_done = True
        self._round_gate.set()

    async def wait_for_round_gate(self) -> None:
        """Crew agents wait here until Supervisor has spoken first."""
        if self._supervisor_first_round_done:
            return
        try:
            await asyncio.wait_for(self._round_gate.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Round gate timeout — proceeding without Supervisor")

    async def release(self, agent_id: str) -> None:
        async with self._lock:
            if self._current == agent_id:
                self._current = None


class _RateLimiter:
    """Sliding-window rate limiter."""

    def __init__(self, max_rpm: int) -> None:
        self._max_rpm = max_rpm
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def check_and_record(self) -> bool:
        """Return True and record if within limit; False if limit exceeded."""
        async with self._lock:
            now = time.time()
            cutoff = now - _RPM_WINDOW_SECONDS
            # Purge old entries
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max_rpm:
                return False
            self._timestamps.append(now)
            return True


class AgentCoordinator:
    """Coordinates AI agent actions across all projects.

    Responsibilities:
    - Per-project exclusive action queue (Supervisor priority, FIFO for crew)
    - 30-second queue timeout (auto-abandon)
    - Per-project rate limit: ≤ 30 RPM
    - Global rate limit: ≤ 300 RPM
    """

    def __init__(self) -> None:
        self._project_queues: dict[UUID, _ProjectQueue] = {}
        self._project_rate_limiters: dict[UUID, _RateLimiter] = {}
        self._global_rate_limiter = _RateLimiter(_GLOBAL_RPM_LIMIT)
        self._meta_lock = asyncio.Lock()

    async def _get_project_queue(self, project_id: UUID) -> _ProjectQueue:
        async with self._meta_lock:
            if project_id not in self._project_queues:
                self._project_queues[project_id] = _ProjectQueue()
            return self._project_queues[project_id]

    async def _get_project_rate_limiter(self, project_id: UUID) -> _RateLimiter:
        async with self._meta_lock:
            if project_id not in self._project_rate_limiters:
                self._project_rate_limiters[project_id] = _RateLimiter(_PROJECT_RPM_LIMIT)
            return self._project_rate_limiters[project_id]

    async def acquire(
        self,
        project_id: UUID,
        agent_id: str,
        is_supervisor: bool = False,
    ) -> bool:
        """Attempt to acquire the action lock for this project.

        Checks rate limits before queuing; returns False immediately if either
        rate limit is exceeded without waiting.

        Returns True on success, False if rate-limited or queue-timed-out.
        """
        # Check global rate limit first
        global_ok = await self._global_rate_limiter.check_and_record()
        if not global_ok:
            logger.warning(
                "Global RPM limit (%d) reached — agent %s skipped",
                _GLOBAL_RPM_LIMIT,
                agent_id,
            )
            return False

        # Check per-project rate limit
        project_rl = await self._get_project_rate_limiter(project_id)
        project_ok = await project_rl.check_and_record()
        if not project_ok:
            logger.warning(
                "Project %s RPM limit (%d) reached — agent %s skipped",
                project_id,
                _PROJECT_RPM_LIMIT,
                agent_id,
            )
            return False

        # Enqueue for exclusive execution
        queue = await self._get_project_queue(project_id)
        acquired = await queue.acquire(agent_id, is_supervisor)
        return acquired

    async def release(self, project_id: UUID, agent_id: str) -> None:
        """Release the action lock for this project."""
        if project_id in self._project_queues:
            await self._project_queues[project_id].release(agent_id)

    def get_queue_depth(self, project_id: UUID) -> int:
        """Return the number of agents queued or acting in this project."""
        queue = self._project_queues.get(project_id)
        return 0 if queue is None else queue.queue_depth()

    async def mark_supervisor_done(self, project_id: UUID, agent_id: str) -> None:
        """Notify that the supervisor completed its first action (round gate)."""
        queue = self._project_queues.get(project_id)
        if queue is not None:
            queue.mark_supervisor_first_round_done()
            logger.info(
                "Supervisor %s marked first round done for project %s",
                agent_id,
                project_id,
            )

    async def wait_for_round_gate(self, project_id: UUID) -> None:
        """Crew agents wait for the supervisor's first action."""
        queue = await self._get_project_queue(project_id)
        await queue.wait_for_round_gate()

    def is_agent_acting(self, project_id: UUID) -> bool:
        """Return True if any agent currently holds the project lock."""
        queue = self._project_queues.get(project_id)
        if queue is None:
            return False
        return queue._current is not None


# Module-level singleton
agent_coordinator = AgentCoordinator()
