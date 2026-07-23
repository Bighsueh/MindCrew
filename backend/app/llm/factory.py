"""Multi-provider LLM service.

Routes each call through ``ProviderRouter`` which yields candidates in tier
order (tier 1 round-robin, tier 2-5 sequential). Every attempt — success or
failure — is logged via ``log_service.record``. Failed providers are placed
into a short cooldown to avoid hammering them.

Phase 25.J extension: callers must supply ``owning_user_id`` (NOT NULL in
DB). Other attribution fields (project_id, triggered_by_user_id, caller) are
optional but strongly encouraged so the admin console can answer who/what.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator
from uuid import UUID

from app.llm.base import LLMResponse, TokenUsage
from app.llm import log_service
from app.llm.health_monitor import health_monitor
from app.llm.registry import ProviderRegistry
from app.llm.router import ProviderRouter
from app.llm.routing_policy import resolve_class

logger = logging.getLogger(__name__)


_EMPTY_USAGE = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


class LLMService:
    """Public surface used by all callers."""

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        owning_user_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        project_id: UUID | None = None,
        triggered_by_user_id: UUID | None = None,
        caller: str = "unknown",
    ) -> LLMResponse:
        last_exc: Exception | None = None
        attempted = 0
        first_tier_attempted: int | None = None
        required_class = resolve_class(caller)

        async for entry in ProviderRouter.iter_candidates(required_class):
            attempted += 1
            if first_tier_attempted is None:
                first_tier_attempted = entry.row.tier
            cascade_from = (
                first_tier_attempted
                if entry.row.tier != first_tier_attempted
                else None
            )
            # Two attempts per provider before moving on.
            for attempt in range(2):
                t0 = time.monotonic()
                try:
                    response = await entry.instance.chat_completion(
                        messages, temperature=temperature, max_tokens=max_tokens
                    )
                except Exception as exc:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    last_exc = exc
                    logger.warning(
                        "Provider %s attempt %d failed: %s",
                        entry.row.name,
                        attempt + 1,
                        exc,
                    )
                    log_service.record(
                        entry,
                        usage=_EMPTY_USAGE,
                        latency_ms=latency_ms,
                        success=False,
                        error_msg=f"{type(exc).__name__}: {exc}",
                        owning_user_id=owning_user_id,
                        triggered_by_user_id=triggered_by_user_id,
                        project_id=project_id,
                        messages=messages,
                        response_content=None,
                        caller=caller,
                        cascade_from_tier=cascade_from,
                    )
                    continue

                latency_ms = int((time.monotonic() - t0) * 1000)
                ProviderRouter.mark_success(entry)
                log_service.record(
                    entry,
                    usage=response.usage,
                    latency_ms=latency_ms,
                    success=True,
                    owning_user_id=owning_user_id,
                    triggered_by_user_id=triggered_by_user_id,
                    project_id=project_id,
                    messages=messages,
                    response_content=response.content,
                    response_finish_reason=response.finish_reason,
                    caller=caller,
                    cascade_from_tier=cascade_from,
                )
                # Phase 42 D5 (G14, spec 20 §13.2)：任一成功 → reactive 計數歸零。
                try:
                    await health_monitor.record_success()
                except Exception:  # noqa: BLE001 — 監測不可影響正常呼叫
                    logger.debug("health_monitor.record_success failed", exc_info=True)
                return response

            # Both attempts on this provider failed — cool it down.
            ProviderRouter.mark_failure(entry)

        if attempted == 0:
            raise RuntimeError(
                "No LLM providers configured. Add one via the admin console (/admin)."
            )
        # Phase 42 D5 (G14, spec 20 §13.2)：所有 tier×class 候選皆失敗＝備援耗盡點，
        # 計一次 reactive 硬失敗（連續達門檻 → health_monitor 觸發全房 fail-stop）。
        try:
            await health_monitor.record_exhaustion(
                str(last_exc) if last_exc else None
            )
        except Exception:  # noqa: BLE001
            logger.debug("health_monitor.record_exhaustion failed", exc_info=True)
        raise RuntimeError(
            f"All LLM providers failed across {attempted} tier(s). Last error: {last_exc}"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict],
        *,
        owning_user_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        project_id: UUID | None = None,
        triggered_by_user_id: UUID | None = None,
        caller: str = "unknown",
    ) -> AsyncIterator[str]:
        """Stream from a single tier-1 provider. No mid-stream fallback.

        Accumulates yielded chunks so the full assembled response can be
        written to llm_request_payloads on completion.
        """
        entry = await ProviderRouter.primary_for_streaming(resolve_class(caller))
        if entry is None:
            # Phase 42 D5 (G14, spec 20 §13.2)：串流無任何可用 provider＝備援耗盡 → 計一次硬失敗。
            try:
                await health_monitor.record_exhaustion("stream: no healthy provider")
            except Exception:  # noqa: BLE001
                logger.debug("health_monitor.record_exhaustion failed", exc_info=True)
            raise RuntimeError("No healthy LLM provider available for streaming")

        t0 = time.monotonic()
        chunks: list[str] = []
        failed = False
        error_text: str | None = None
        try:
            async for chunk in entry.instance.chat_completion_stream(
                messages, temperature=temperature, max_tokens=max_tokens
            ):
                chunks.append(chunk)
                yield chunk
        except Exception as exc:
            failed = True
            error_text = f"stream:{type(exc).__name__}: {exc}"
            ProviderRouter.mark_failure(entry)
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            assembled = "".join(chunks) if chunks else None
            if failed:
                # Phase 42 D5 (G14, spec 20 §13.2)：串流無 mid-stream fallback，單次失敗＝
                # 該呼叫終局（候選耗盡）→ 計一次 reactive 硬失敗。
                try:
                    await health_monitor.record_exhaustion(error_text)
                except Exception:  # noqa: BLE001
                    logger.debug("health_monitor.record_exhaustion failed", exc_info=True)
                log_service.record(
                    entry,
                    usage=_EMPTY_USAGE,
                    latency_ms=latency_ms,
                    success=False,
                    error_msg=error_text,
                    owning_user_id=owning_user_id,
                    triggered_by_user_id=triggered_by_user_id,
                    project_id=project_id,
                    messages=messages,
                    response_content=assembled,
                    caller=caller,
                )
            else:
                ProviderRouter.mark_success(entry)
                # Phase 42 D5 (G14, spec 20 §13.2)：任一成功 → reactive 計數歸零。
                try:
                    await health_monitor.record_success()
                except Exception:  # noqa: BLE001
                    logger.debug("health_monitor.record_success failed", exc_info=True)
                log_service.record(
                    entry,
                    usage=_EMPTY_USAGE,  # streaming doesn't return usage reliably
                    latency_ms=latency_ms,
                    success=True,
                    owning_user_id=owning_user_id,
                    triggered_by_user_id=triggered_by_user_id,
                    project_id=project_id,
                    messages=messages,
                    response_content=assembled,
                    caller=caller,
                )

    async def health_check(self) -> bool:
        """Return True if at least one configured provider is reachable."""
        entries = await ProviderRegistry.get_entries(force=True)
        for entry in entries:
            try:
                if await entry.instance.health_check():
                    return True
            except Exception:  # noqa: BLE001 — keep probing other providers
                continue
        return False


class LLMProviderFactory:
    """Backward-compatible singleton accessor."""

    _instance: LLMService | None = None

    @classmethod
    def get_service(cls) -> LLMService:
        if cls._instance is None:
            cls._instance = LLMService()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None
