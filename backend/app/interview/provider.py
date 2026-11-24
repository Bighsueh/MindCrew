"""Provider boundary for the interview. Crew routing remains independent."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import ceil
from typing import Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.config import settings
from app.llm.base import TokenUsage


class GenerationError(Exception):
    def __init__(self, code: str, retry_after: int | None = None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def retry_delay(value: str) -> int | None:
    if value.isascii() and value.isdecimal() and len(value) <= 9:
        return int(value)
    try:
        until = parsedate_to_datetime(value)
        if until.tzinfo is not None:
            return max(0, ceil((until - datetime.now(timezone.utc)).total_seconds()))
    except (ValueError, OverflowError):
        pass
    return None


@dataclass(frozen=True)
class InterviewReply:
    content: str
    model: str
    usage: TokenUsage | None = None


class InterviewProvider(Protocol):
    name: str

    async def generate(self, instructions: str, messages: list[dict]) -> InterviewReply: ...

    async def generate_profiles(self, instructions: str, messages: list[dict]) -> InterviewReply: ...


class OpenAIInterviewProvider:
    name = "openai"

    async def generate(self, instructions: str, messages: list[dict]) -> InterviewReply:
        return await self._respond(instructions, messages, {})

    async def generate_profiles(self, instructions: str, messages: list[dict]) -> InterviewReply:
        return await self._respond(instructions, messages, {"text": {"format": {"type": "json_object"}}}, 3600)

    async def _respond(self, instructions: str, messages: list[dict], options: dict, max_tokens: int | None = None) -> InterviewReply:
        model = settings.INTERVIEW_LLM_MODEL.strip()
        key = settings.OPENAI_API_KEY.get_secret_value().strip()
        if not key:
            raise GenerationError("missing_key")
        if not model:
            raise GenerationError("missing_model")

        try:
            async with AsyncOpenAI(
                api_key=key,
                base_url="https://api.openai.com/v1",
                timeout=settings.INTERVIEW_LLM_TIMEOUT_SECONDS,
                max_retries=0,
            ) as client:
                result = await client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=messages,
                    max_output_tokens=max_tokens or settings.INTERVIEW_LLM_MAX_OUTPUT_TOKENS,
                    store=False,
                    truncation="disabled",
                    **options,
                )
        except APITimeoutError:
            raise GenerationError("openai_timeout") from None
        except APIConnectionError:
            raise GenerationError("openai_connection") from None
        except APIStatusError as exc:
            if exc.code == "context_length_exceeded":
                raise GenerationError("context_limit") from None
            if exc.status_code == 401:
                raise GenerationError("openai_auth") from None
            if exc.status_code in {403, 404} or exc.code == "model_not_found":
                raise GenerationError("openai_model") from None
            if exc.code in {
                "insufficient_quota", "billing_hard_limit_reached",
                "credit_balance_exhausted", "organization_usage_limit_exceeded",
            }:
                raise GenerationError("openai_quota") from None
            if exc.status_code == 429:
                raise GenerationError("openai_rate_limit", retry_delay(exc.response.headers.get("Retry-After", "").strip())) from None
            if exc.status_code >= 500:
                raise GenerationError("openai_unavailable", retry_delay(exc.response.headers.get("Retry-After", "").strip())) from None
            raise GenerationError("openai_request") from None

        refused = any(part.type == "refusal" for item in result.output if item.type == "message" for part in item.content)
        if result.status != "completed" or refused or not result.output_text.strip():
            raise GenerationError("invalid_reply")
        usage = result.usage
        return InterviewReply(
            content=result.output_text,
            usage=TokenUsage(usage.input_tokens, usage.output_tokens, usage.total_tokens) if usage else None,
            model=result.model or model,
        )


def get_interview_provider() -> InterviewProvider:
    if settings.INTERVIEW_LLM_PROVIDER.strip().lower() != "openai":
        return UnconfiguredProvider()
    return OpenAIInterviewProvider()


class UnconfiguredProvider:
    name = "unconfigured"

    async def generate(self, instructions: str, messages: list[dict]) -> InterviewReply:
        raise GenerationError("unsupported_provider")

    generate_profiles = generate
