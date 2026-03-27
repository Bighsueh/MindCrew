from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.llm.base import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)


class VLLMProvider(LLMProvider):
    """LLM provider backed by a vLLM-compatible OpenAI endpoint."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.VLLM_BASE_URL,
            api_key=settings.VLLM_API_KEY,
        )
        self._model = settings.VLLM_MODEL_NAME
        self._timeout = settings.LLM_CALL_TIMEOUT_SECONDS

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send a chat completion request, with a hard timeout."""
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("vLLM chat_completion timed out after %ss", self._timeout)
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
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
        )

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
