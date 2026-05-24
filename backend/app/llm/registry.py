"""Provider registry — loads DB-backed LLM provider configs and instantiates
concrete ``LLMProvider`` instances, bucketed by tier.

Refreshed at startup (``warmup``) and after admin mutations (``invalidate``).
Cached entries are reused across requests; a soft TTL guards against stale
caches if an admin operation skips the explicit invalidation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.config import settings
from app.db.models.llm_provider import LLMProvider as LLMProviderRow
from app.db.session import async_session_factory
from app.llm.azure_provider import AzureOpenAIProvider
from app.llm.base import LLMProvider
from app.llm.vllm_provider import VLLMProvider
from app.security.secrets import decrypt_secret

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderEntry:
    """Bundle of a DB row and its instantiated provider."""

    row: LLMProviderRow
    instance: LLMProvider

    @property
    def tier(self) -> int:
        return self.row.tier


def _build_instance(row: LLMProviderRow) -> LLMProvider:
    # Phase 26 / S2: api_key is stored encrypted (envelope-encryption).
    # Decrypt at instantiation time so plaintext stays only in memory.
    api_key_plain = decrypt_secret(row.api_key)
    if row.kind == "vllm":
        return VLLMProvider(
            base_url=row.base_url,
            api_key=api_key_plain or "dummy",
            model=row.model,
        )
    if row.kind == "azure_openai":
        return AzureOpenAIProvider(
            endpoint=row.base_url,
            api_key=api_key_plain,
            deployment=row.azure_deployment or row.model,
            api_version=row.azure_api_version or "2024-02-15-preview",
            model=row.model,
            timeout_seconds=row.timeout_seconds,
        )
    raise ValueError(f"Unknown provider kind: {row.kind}")


class ProviderRegistry:
    """In-process cache of enabled LLM providers, grouped by tier."""

    _entries: list[ProviderEntry] = []
    _last_loaded_at: float = 0.0
    _lock = asyncio.Lock()

    @classmethod
    async def warmup(cls) -> None:
        await cls.get_entries(force=True)

    @classmethod
    def invalidate(cls) -> None:
        """Mark cache stale; next access reloads from DB."""
        cls._last_loaded_at = 0.0

    @classmethod
    async def get_entries(cls, *, force: bool = False) -> list[ProviderEntry]:
        ttl = settings.LLM_PROVIDER_REGISTRY_TTL_SECONDS
        now = time.monotonic()
        if (
            not force
            and cls._entries
            and now - cls._last_loaded_at < ttl
        ):
            return cls._entries

        async with cls._lock:
            # Re-check after acquiring the lock — another caller may have
            # populated the cache while we waited.
            if (
                not force
                and cls._entries
                and time.monotonic() - cls._last_loaded_at < ttl
            ):
                return cls._entries

            rows = await cls._load_rows()
            entries: list[ProviderEntry] = []
            for row in rows:
                try:
                    entries.append(ProviderEntry(row=row, instance=_build_instance(row)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Skipping provider %s (id=%s): %s", row.name, row.id, exc
                    )
            # Stable ordering: tier asc, then by name for round-robin determinism.
            entries.sort(key=lambda e: (e.row.tier, e.row.name))
            cls._entries = entries
            cls._last_loaded_at = time.monotonic()
            logger.info(
                "ProviderRegistry loaded %d providers across tiers %s",
                len(entries),
                sorted({e.row.tier for e in entries}),
            )
            return entries

    @classmethod
    async def _load_rows(cls) -> list[LLMProviderRow]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(LLMProviderRow).where(LLMProviderRow.enabled.is_(True))
            )
            return list(result.scalars().all())

    @classmethod
    async def by_tier(cls) -> dict[int, list[ProviderEntry]]:
        entries = await cls.get_entries()
        buckets: dict[int, list[ProviderEntry]] = {}
        for entry in entries:
            buckets.setdefault(entry.row.tier, []).append(entry)
        return buckets
