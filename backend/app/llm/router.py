"""ProviderRouter — yields provider candidates in tier order.

Tier 1 is round-robined across all healthy providers; tiers 2-5 cascade
sequentially. A short cooldown on failed providers prevents repeated
hammering during outage.

The actual call/retry loop lives in ``LLMService.chat_completion`` (see
``factory.py``). This module is only responsible for *selecting* the next
candidate and tracking transient failure state.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import AsyncIterator

from app.config import settings
from app.llm.registry import ProviderEntry, ProviderRegistry

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Stateless façade with class-level scheduling state."""

    # tier -> next round-robin index
    _rr_index: dict[int, int] = defaultdict(int)
    # provider id (str) -> monotonic time at which cooldown expires
    _cooldown_until: dict[str, float] = {}
    _lock = asyncio.Lock()

    # ── public API ───────────────────────────────────────────────────────

    @classmethod
    async def iter_candidates(cls) -> AsyncIterator[ProviderEntry]:
        """Yield one provider at a time across tiers.

        Within a tier, providers are returned in a round-robin order with
        cooled-down providers skipped on this call (they may be retried on a
        later call once the cooldown expires). When the entire tier is
        exhausted without success the caller proceeds to the next tier.
        """
        buckets = await ProviderRegistry.by_tier()
        for tier in sorted(buckets.keys()):
            entries = buckets[tier]
            if not entries:
                continue
            for entry in cls._order_for_tier(tier, entries):
                if cls._in_cooldown(entry):
                    continue
                yield entry

    @classmethod
    async def primary_for_streaming(cls) -> ProviderEntry | None:
        """Pick a single tier-1 provider for streaming (no cascade mid-stream)."""
        buckets = await ProviderRegistry.by_tier()
        if not buckets:
            return None
        # Start at tier 1 and walk up if every provider there is cooling down.
        for tier in sorted(buckets.keys()):
            for entry in cls._order_for_tier(tier, buckets[tier]):
                if not cls._in_cooldown(entry):
                    return entry
        return None

    @classmethod
    def mark_failure(cls, entry: ProviderEntry) -> None:
        cooldown = settings.LLM_PROVIDER_COOLDOWN_SECONDS
        cls._cooldown_until[str(entry.row.id)] = time.monotonic() + cooldown
        logger.warning(
            "Provider %s entered cooldown for %ss", entry.row.name, cooldown
        )

    @classmethod
    def mark_success(cls, entry: ProviderEntry) -> None:
        cls._cooldown_until.pop(str(entry.row.id), None)

    @classmethod
    def reset(cls) -> None:
        """Clear scheduling state (used by tests and admin actions)."""
        cls._rr_index.clear()
        cls._cooldown_until.clear()

    # ── internals ────────────────────────────────────────────────────────

    @classmethod
    def _order_for_tier(
        cls, tier: int, entries: list[ProviderEntry]
    ) -> list[ProviderEntry]:
        """Return entries rotated so the next round-robin slot is first.

        Tiers > 1 are returned in their stable order (cascade is sequential,
        not load-balanced); tier 1 advances the rotation cursor on each call.
        """
        if not entries:
            return []
        if tier != 1:
            return list(entries)
        start = cls._rr_index[tier] % len(entries)
        cls._rr_index[tier] = (start + 1) % len(entries)
        return entries[start:] + entries[:start]

    @classmethod
    def _in_cooldown(cls, entry: ProviderEntry) -> bool:
        until = cls._cooldown_until.get(str(entry.row.id))
        if until is None:
            return False
        if time.monotonic() >= until:
            cls._cooldown_until.pop(str(entry.row.id), None)
            return False
        return True
