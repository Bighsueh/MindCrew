"""Fire-and-forget persistence of LLM request attempts + payloads.

Phase 25.J extension: every ``record()`` call writes TWO rows in a single
transaction —

  1. ``llm_request_logs``  — hot, indexed, scanned by stats queries.
  2. ``llm_request_payloads`` — cold, holds full messages + response.

The LLM critical path never awaits the DB write — ``asyncio.create_task``
schedules the insert as a background task and any failure is swallowed at
WARN level so logging can never break a live request.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.llm_request_payload import LLMRequestPayload
from app.db.session import async_session_factory
from app.llm.base import TokenUsage
from app.llm.registry import ProviderEntry

logger = logging.getLogger(__name__)

# Per-message content cap. system prompts in this codebase routinely exceed
# 4KB; 8KB lets us keep most intact while preventing 50KB+ prompt explosions
# from filling the DB. Truncation is recorded so the admin UI can flag it.
_MAX_MESSAGE_CONTENT_BYTES = 8 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024


def _truncate_messages(messages: list[dict]) -> tuple[list[dict], int]:
    """Return (truncated copy, total byte size after truncation)."""
    out: list[dict] = []
    total = 0
    for msg in messages:
        role = str(msg.get("role", "user"))[:32]
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        encoded = content.encode("utf-8")
        truncated_chars: int | None = None
        if len(encoded) > _MAX_MESSAGE_CONTENT_BYTES:
            # Cut on byte boundary then back off to a valid UTF-8 char.
            cut = encoded[:_MAX_MESSAGE_CONTENT_BYTES].decode(
                "utf-8", errors="ignore"
            )
            truncated_chars = len(content) - len(cut)
            content = cut
        entry: dict = {"role": role, "content": content}
        if truncated_chars:
            entry["truncated_chars"] = truncated_chars
        out.append(entry)
        total += len(content.encode("utf-8"))
    return out, total


def _truncate_response(content: str | None) -> str | None:
    if content is None:
        return None
    encoded = content.encode("utf-8")
    if len(encoded) <= _MAX_RESPONSE_BYTES:
        return content
    cut = encoded[:_MAX_RESPONSE_BYTES].decode("utf-8", errors="ignore")
    return cut + f"\n[truncated {len(content) - len(cut)} chars]"


def record(
    entry: ProviderEntry,
    *,
    usage: TokenUsage,
    latency_ms: int,
    success: bool,
    owning_user_id: UUID,
    messages: list[dict],
    response_content: str | None = None,
    response_finish_reason: str | None = None,
    project_id: UUID | None = None,
    triggered_by_user_id: UUID | None = None,
    caller: str = "unknown",
    cascade_from_tier: int | None = None,
    error_msg: str | None = None,
) -> None:
    """Schedule an async write of log + payload without awaiting it.

    ``owning_user_id`` is required (Phase 25.J): every call must be
    attributable. Callers without a direct user pass the project's
    linked teacher id (or the seeded admin for ad-hoc paths).
    """
    error_class: str | None = None
    error_message: str | None = None
    if error_msg:
        if ":" in error_msg:
            error_class, _, error_message = error_msg.partition(":")
            error_class = error_class.strip()[:64]
            error_message = error_message.strip()
        else:
            error_class = error_msg[:64]

    safe_messages, messages_bytes = _truncate_messages(messages or [])
    safe_response = _truncate_response(response_content)

    payload = {
        "owning_user_id": owning_user_id,
        "triggered_by_user_id": triggered_by_user_id,
        "project_id": project_id,
        "provider_id": entry.row.id,
        "tier_used": entry.row.tier,
        "cascade_from_tier": cascade_from_tier,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "latency_ms": latency_ms,
        "success": success,
        "error_class": error_class,
        "error_message": error_message,
        "caller": (caller or "unknown")[:64],
    }
    payload_extras = {
        "messages": safe_messages,
        "response_content": safe_response,
        "response_finish_reason": (response_finish_reason or None),
        "messages_bytes": messages_bytes,
    }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("log_service.record called outside event loop; skipping")
        return

    loop.create_task(_write(payload, payload_extras))


async def _write(log_payload: dict, payload_extras: dict) -> None:
    try:
        async with async_session_factory() as session:
            log_row = LLMRequestLog(**log_payload)
            session.add(log_row)
            await session.flush()  # get log_row.id

            session.add(
                LLMRequestPayload(
                    request_log_id=log_row.id,
                    **payload_extras,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — never let logging break the request
        # Surface the offending payload at DEBUG so dev can spot schema drift,
        # but don't dump full messages to INFO/WARN — they may contain PII.
        logger.warning("Failed to persist llm_request_log: %s", exc)
        logger.debug("Payload that failed: %s", json.dumps(log_payload, default=str))
