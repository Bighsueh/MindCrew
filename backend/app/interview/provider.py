"""Provider boundary for the interview. Crew routing remains independent."""

from dataclasses import dataclass
from typing import Protocol

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from app.config import settings
from app.llm.base import TokenUsage


class GenerationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class InterviewReply:
    content: str
    model: str
    usage: TokenUsage | None = None


class InterviewProvider(Protocol):
    name: str

    async def generate(self, instructions: str, messages: list[dict]) -> InterviewReply: ...


class OpenAIInterviewProvider:
    name = "openai"

    async def generate(self, instructions: str, messages: list[dict]) -> InterviewReply:
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
                    max_output_tokens=settings.INTERVIEW_LLM_MAX_OUTPUT_TOKENS,
                    store=False,
                    truncation="disabled",
                )
        except APIConnectionError:
            raise GenerationError("temporary") from None
        except APIStatusError as exc:
            if exc.code == "context_length_exceeded":
                raise GenerationError("context_limit") from None
            if exc.status_code == 401:
                raise GenerationError("openai_auth") from None
            if exc.status_code in {403, 404} or exc.code == "model_not_found":
                raise GenerationError("openai_model") from None
            if exc.code in {"insufficient_quota", "billing_hard_limit_reached"}:
                raise GenerationError("openai_quota") from None
            if exc.status_code >= 500 or exc.status_code == 429:
                raise GenerationError("temporary") from None
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
