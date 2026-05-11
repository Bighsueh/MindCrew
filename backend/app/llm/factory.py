from __future__ import annotations

import logging
from typing import AsyncIterator

from app.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class LLMService:
    """Wraps a primary provider with an optional fallback.

    Retry strategy:
    - Primary is attempted once.
    - On failure, retry primary once more.
    - If the second attempt also fails and a fallback is configured, try fallback.
    - If fallback is unavailable, re-raise the last exception.
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        last_exc: Exception | None = None

        # Attempt primary twice.
        for attempt in range(2):
            try:
                return await self._primary.chat_completion(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Primary LLM attempt %d failed: %s", attempt + 1, exc
                )

        # Try fallback if configured.
        if self._fallback is not None:
            try:
                logger.info("Switching to fallback LLM provider")
                return await self._fallback.chat_completion(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as exc:
                last_exc = exc
                logger.error("Fallback LLM also failed: %s", exc)

        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_exc}"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream from primary provider only — no fallback for streaming.

        Streaming halfway through and switching providers would produce
        garbled output. Callers should fall back to the non-streaming
        ``chat_completion`` path if streaming fails.
        """
        async for chunk in self._primary.chat_completion_stream(
            messages, temperature=temperature, max_tokens=max_tokens
        ):
            yield chunk

    async def health_check(self) -> bool:
        """Return True if at least one provider is healthy."""
        primary_ok = await self._primary.health_check()
        if primary_ok:
            return True
        if self._fallback is not None:
            return await self._fallback.health_check()
        return False


class LLMProviderFactory:
    """Build and cache the application-wide LLMService singleton."""

    _instance: LLMService | None = None

    @classmethod
    def get_service(cls) -> LLMService:
        if cls._instance is None:
            cls._instance = cls._build()
        return cls._instance

    @classmethod
    def _build(cls) -> LLMService:
        from app.config import settings
        from app.llm.vllm_provider import VLLMProvider

        primary = VLLMProvider()
        fallback: LLMProvider | None = None

        if settings.LLM_FALLBACK_PROVIDER == "azure":
            try:
                from app.llm.azure_provider import AzureOpenAIProvider  # type: ignore[import]
                fallback = AzureOpenAIProvider()
                logger.info("LLM fallback provider: Azure OpenAI")
            except ImportError:
                logger.warning("Azure fallback requested but azure_provider module not found")

        logger.info("LLMService built (primary=vllm, fallback=%s)", settings.LLM_FALLBACK_PROVIDER)
        return LLMService(primary=primary, fallback=fallback)

    @classmethod
    def reset(cls) -> None:
        """Reset cached instance (useful in tests)."""
        cls._instance = None
