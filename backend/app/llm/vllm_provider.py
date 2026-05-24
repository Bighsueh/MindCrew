from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.config import settings
from app.llm.base import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)


class VLLMProvider(LLMProvider):
    """LLM provider backed by a vLLM-compatible OpenAI endpoint.

    Phase 25：base_url / api_key / model 必須由呼叫端（``ProviderRegistry``）
    從 DB row 明確帶入；不再從 env 帶 fallback。沒帶 → 直接拋錯。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
    ) -> None:
        if not base_url or not model:
            raise ValueError(
                "VLLMProvider requires base_url and model — configure via admin console."
            )
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )
        self._model = model
        self._timeout = settings.LLM_CALL_TIMEOUT_SECONDS
        self._connect_timeout = settings.LLM_STREAM_CONNECT_TIMEOUT_SECONDS

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send a streaming chat completion request, with a hard timeout.

        ``stream_options.include_usage=True`` is required (per the OpenAI
        streaming spec) for the final chunk to carry prompt/completion token
        counts — without it ``chunk.usage`` is always None and the admin
        stats end up flat-at-zero.
        """
        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                ),
                timeout=self._connect_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "vLLM chat_completion connect timed out after %ss",
                self._connect_timeout,
            )
            raise

        chunks: list[str] = []
        finish_reason = "stop"
        model = self._model
        usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

        try:
            async for chunk in stream:
                if chunk.model:
                    model = chunk.model
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        chunks.append(delta.content)
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
                if chunk.usage:
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
        except asyncio.TimeoutError:
            logger.warning("vLLM streaming timed out after %ss", self._timeout)
            raise

        return LLMResponse(
            content="".join(chunks),
            usage=usage,
            model=model,
            finish_reason=finish_reason,
        )

    async def chat_completion_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Yield content delta strings as the LLM streams its response.

        Raises asyncio.TimeoutError if the initial connect or any chunk
        exceeds the configured timeout.
        """
        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                ),
                timeout=self._connect_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "vLLM chat_completion_stream connect timed out after %ss",
                self._connect_timeout,
            )
            raise

        try:
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except asyncio.TimeoutError:
            logger.warning(
                "vLLM streaming chunk timed out after %ss", self._timeout
            )
            raise

    async def health_check(self) -> bool:
        """Return True if the vLLM endpoint can list its models."""
        try:
            await asyncio.wait_for(
                self._client.models.list(),
                timeout=5.0,
            )
            return True
        except Exception as exc:
            logger.warning("vLLM health_check failed: %s", exc)
            return False
