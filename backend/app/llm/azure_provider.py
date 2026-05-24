"""Azure OpenAI provider (Phase 25).

Implements ``LLMProvider`` against Azure OpenAI's Chat Completions API. Used
by the multi-provider router alongside vLLM. The Azure-specific ``deployment``
name and ``api_version`` are read from the provider row (DB) — no env-level
config is required when called via the registry.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from openai import AsyncAzureOpenAI

from app.llm.base import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(LLMProvider):
    """LLM provider backed by Azure OpenAI."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-02-15-preview",
        model: str | None = None,
        timeout_seconds: int = 30,
        connect_timeout_seconds: int = 15,
    ) -> None:
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint,
        )
        # Azure routes by deployment name; we pass it as the "model" argument.
        self._deployment = deployment
        # Reported model (for logging / response.model). Falls back to deployment.
        self._model_label = model or deployment
        self._timeout = timeout_seconds
        self._connect_timeout = connect_timeout_seconds

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._deployment,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Azure chat_completion timed out after %ss", self._timeout
            )
            raise

        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            model=response.model or self._model_label,
            finish_reason=choice.finish_reason or "stop",
        )

    async def chat_completion_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._deployment,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                ),
                timeout=self._connect_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Azure chat_completion_stream connect timed out after %ss",
                self._connect_timeout,
            )
            raise

        try:
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except asyncio.TimeoutError:
            logger.warning("Azure streaming chunk timed out after %ss", self._timeout)
            raise

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(self._client.models.list(), timeout=5.0)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Azure health_check failed: %s", exc)
            return False
