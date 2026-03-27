from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThrottleParams:
    min_interval: float    # Minimum seconds between actions
    max_interval: float    # Maximum seconds between actions
    idle_threshold: float  # Seconds of idle before forced intervention check
    multi_agent_gap: float # Minimum gap between consecutive AI agents acting


# Time parameters per spec §3.1
_PARAMS: dict[str, ThrottleParams] = {
    "low": ThrottleParams(
        min_interval=15.0,
        max_interval=45.0,
        idle_threshold=60.0,
        multi_agent_gap=5.0,
    ),
    "medium": ThrottleParams(
        min_interval=8.0,
        max_interval=25.0,
        idle_threshold=30.0,
        multi_agent_gap=3.0,
    ),
    "high": ThrottleParams(
        min_interval=4.0,
        max_interval=12.0,
        idle_threshold=15.0,
        multi_agent_gap=2.0,
    ),
}

_DEFAULT_PARAMS = _PARAMS["medium"]


class ThrottleGate:
    """Manages per-agent timing to avoid flooding the conversation.

    In all-AI mode all intervals are halved (spec §6).
    """

    def __init__(
        self,
        ai_contribution: str = "medium",
        is_all_ai: bool = False,
    ) -> None:
        base = _PARAMS.get(ai_contribution, _DEFAULT_PARAMS)
        if is_all_ai:
            self._params = ThrottleParams(
                min_interval=base.min_interval / 2,
                max_interval=base.max_interval / 2,
                idle_threshold=5.0,  # spec §6: 5s in full-AI mode
                multi_agent_gap=base.multi_agent_gap / 2,
            )
        else:
            self._params = base

        self._last_action_time: float | None = None
        self._contribution = ai_contribution
        self._is_all_ai = is_all_ai

    @property
    def params(self) -> ThrottleParams:
        return self._params

    @property
    def last_action_time(self) -> float | None:
        return self._last_action_time

    def record_action(self) -> None:
        """Record that an action was just taken."""
        self._last_action_time = time.time()

    def seconds_since_last_action(self) -> float | None:
        if self._last_action_time is None:
            return None
        return time.time() - self._last_action_time

    def is_min_interval_reached(self) -> bool:
        elapsed = self.seconds_since_last_action()
        if elapsed is None:
            return True
        return elapsed >= self._params.min_interval

    async def wait(self) -> None:
        """Async wait with randomised delay between min and max interval.

        If the minimum interval has already passed, wait for a random additional
        delay up to (max - elapsed) to spread agent actions naturally.
        """
        elapsed = self.seconds_since_last_action()
        if elapsed is None:
            # First action: wait a short random delay to avoid simultaneous starts
            delay = random.uniform(0.5, self._params.multi_agent_gap)
            logger.debug("ThrottleGate first action: waiting %.1fs", delay)
            await asyncio.sleep(delay)
            return

        remaining_min = max(0.0, self._params.min_interval - elapsed)
        # Extra random delay on top of the minimum wait
        extra = random.uniform(0.0, max(0.0, self._params.max_interval - self._params.min_interval))
        total_wait = remaining_min + extra

        if total_wait > 0:
            logger.debug(
                "ThrottleGate waiting %.1fs (min_remaining=%.1f, extra=%.1f)",
                total_wait,
                remaining_min,
                extra,
            )
            await asyncio.sleep(total_wait)

    def update_contribution(self, ai_contribution: str, is_all_ai: bool | None = None) -> None:
        """Reconfigure throttle params if contribution level changes."""
        if is_all_ai is None:
            is_all_ai = self._is_all_ai
        base = _PARAMS.get(ai_contribution, _DEFAULT_PARAMS)
        if is_all_ai:
            self._params = ThrottleParams(
                min_interval=base.min_interval / 2,
                max_interval=base.max_interval / 2,
                idle_threshold=5.0,
                multi_agent_gap=base.multi_agent_gap / 2,
            )
        else:
            self._params = base
        self._contribution = ai_contribution
        self._is_all_ai = is_all_ai
