"""ProviderRouter — yields provider candidates by capability_class then tier.

Two orthogonal axes (Phase 37):
  * ``capability_class`` (quality / standard) — task-difficulty pool, resolved
    from the call's ``caller`` (see ``routing_policy``). The router serves a
    request from its required class first; if the whole class is unavailable it
    **degrades across classes** (availability over exact-class match).
  * ``tier`` (1-5) — fault-tolerance order *within* a class. Tier 1 is
    round-robined across healthy providers in the same ``(class, tier)`` bucket
    (load balancing + horizontal scale); tiers 2-5 cascade sequentially.

A short cooldown on failed providers prevents repeated hammering during outage.

The actual call/retry loop lives in ``LLMService.chat_completion`` (see
``factory.py``). This module only *selects* the next candidate and tracks
transient failure state.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import AsyncIterator

from app.config import settings
from app.llm.registry import ProviderEntry, ProviderRegistry
from app.llm.routing_policy import STANDARD

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Stateless façade with class-level scheduling state."""

    # (capability_class, tier) -> next round-robin index
    _rr_index: dict[tuple[str, int], int] = defaultdict(int)
    # provider id (str) -> monotonic time at which cooldown expires
    _cooldown_until: dict[str, float] = {}
    _lock = asyncio.Lock()

    # ── public API ───────────────────────────────────────────────────────

    @classmethod
    async def iter_candidates(
        cls, required_class: str = STANDARD
    ) -> AsyncIterator[ProviderEntry]:
        """Yield one provider at a time, preferred class first then degrade.

        Within a class, tiers ascend; within each ``(class, tier)`` bucket the
        order is round-robined (tier 1) or stable (tiers 2-5). Cooled-down
        providers are skipped on this call. When the preferred class is fully
        exhausted the router falls through to the remaining class(es).
        """
        buckets = await ProviderRegistry.by_class_tier()
        for class_name in cls._class_order(required_class, buckets):
            for tier in sorted(t for (c, t) in buckets if c == class_name):
                entries = buckets[(class_name, tier)]
                if not entries:
                    continue
                for entry in cls._order_for_bucket(class_name, tier, entries):
                    if cls._in_cooldown(entry):
                        continue
                    yield entry

    @classmethod
    async def primary_for_streaming(
        cls, required_class: str = STANDARD
    ) -> ProviderEntry | None:
        """Pick a single provider for streaming (no cascade mid-stream).

        Honours capability_class (with cross-class degrade) and skips
        cooled-down providers, but never mid-stream-fails over.
        """
        buckets = await ProviderRegistry.by_class_tier()
        if not buckets:
            return None
        for class_name in cls._class_order(required_class, buckets):
            for tier in sorted(t for (c, t) in buckets if c == class_name):
                for entry in cls._order_for_bucket(
                    class_name, tier, buckets[(class_name, tier)]
                ):
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
    def cooldown_remaining(cls, provider_id: str) -> float | None:
        """剩餘 cooldown 秒數（無 cooldown / 已過期回 None）。供 admin 健康快照。"""
        until = cls._cooldown_until.get(str(provider_id))
        if until is None:
            return None
        remaining = until - time.monotonic()
        return round(remaining, 1) if remaining > 0 else None

    @classmethod
    def reset(cls) -> None:
        """Clear scheduling state (used by tests and admin actions)."""
        cls._rr_index.clear()
        cls._cooldown_until.clear()

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _class_order(
        required_class: str, buckets: dict[tuple[str, int], list[ProviderEntry]]
    ) -> list[str]:
        """Preferred class first, then remaining classes (deterministic).

        Guarantees availability: if the required class has no providers (or all
        cool down), the request still gets served from another class.
        """
        present = {c for (c, _t) in buckets}
        order: list[str] = []
        if required_class in present:
            order.append(required_class)
        for c in sorted(present):
            if c not in order:
                order.append(c)
        return order

    @classmethod
    def _order_for_bucket(
        cls, class_name: str, tier: int, entries: list[ProviderEntry]
    ) -> list[ProviderEntry]:
        """Rotate a ``(class, tier)`` bucket so the next RR slot is first.

        Tier 1 advances a per-bucket rotation cursor (round-robin load
        balancing across same-class peers); tiers > 1 return stable order
        (cascade is sequential, not load-balanced).
        """
        if not entries:
            return []
        if tier != 1:
            return list(entries)
        key = (class_name, tier)
        start = cls._rr_index[key] % len(entries)
        cls._rr_index[key] = (start + 1) % len(entries)
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
