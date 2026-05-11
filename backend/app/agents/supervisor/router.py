"""Supervisor A/B router — Spec 14 §3.

仲裁：B 優先於 A。若兩者同時觸發，B 立即發話，A 排隊到下回合。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.supervisor.personas import (
    PersonaId,
    PersonaInvocation,
    TRIGGERS,
    build_persona_prompt,
)
from app.agents.supervisor.triggers_a import detect_a_triggers
from app.agents.supervisor.triggers_b import detect_b_triggers
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupervisorPersona:
    persona: PersonaId
    trigger_ids: list[str]
    context: dict[str, str]
    invocation: PersonaInvocation


@dataclass(frozen=True)
class SupervisorDecision:
    """Router result. None persona = fall through to default supervisor_mode."""

    persona: SupervisorPersona | None
    pending_a_queue_size: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def select_supervisor_persona(
    project_id: UUID,
    context: dict[str, Any],
) -> SupervisorDecision:
    """根據觸發訊號決定 supervisor 該以哪個 persona 發話。

    流程：
      1. 跑 B triggers（utterance-level）
      2. 跑 A triggers（phase transition / vote 前）
      3. B 優先：若 B fire → 用 PersonaB，A 排隊到 blackboard pending queue
      4. 若只 A fire → 用 PersonaA
      5. 若都沒 fire → 看 pending queue 有沒有上輪被擠掉的 A
      6. 都沒 → 回 None（fall through 既有 supervisor_mode）
    """
    try:
        b_fired = await detect_b_triggers(context)
    except Exception:
        logger.exception("B triggers failed")
        b_fired = []

    try:
        a_fired = await detect_a_triggers(context)
    except Exception:
        logger.exception("A triggers failed")
        a_fired = []

    # B priority
    if b_fired:
        if a_fired:
            await _enqueue_pending_a(project_id, a_fired)
        merged_ctx = _merge_contexts([c for _, c in b_fired])
        ids = [tid for tid, _ in b_fired]
        invocation = build_persona_prompt("B", ids, merged_ctx)
        return SupervisorDecision(
            persona=SupervisorPersona("B", ids, merged_ctx, invocation),
            pending_a_queue_size=await _pending_a_count(project_id),
        )

    if a_fired:
        merged_ctx = _merge_contexts([c for _, c in a_fired])
        ids = [tid for tid, _ in a_fired]
        invocation = build_persona_prompt("A", ids, merged_ctx)
        return SupervisorDecision(
            persona=SupervisorPersona("A", ids, merged_ctx, invocation),
            pending_a_queue_size=await _pending_a_count(project_id),
        )

    # Both empty — pop pending A
    pending = await _pop_pending_a(project_id)
    if pending:
        ctx = pending.get("context", {})
        ids = pending.get("trigger_ids", [])
        invocation = build_persona_prompt("A", ids, ctx)
        return SupervisorDecision(
            persona=SupervisorPersona("A", ids, ctx, invocation),
            pending_a_queue_size=await _pending_a_count(project_id),
        )

    return SupervisorDecision(persona=None)


# ---------------------------------------------------------------------------
# Pending A queue (Redis)
# ---------------------------------------------------------------------------

_PENDING_KEY_TMPL = "supervisor_pending_a:{project_id}"


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _enqueue_pending_a(
    project_id: UUID,
    fired: list[tuple[str, dict[str, str]]],
) -> None:
    """把被 B 擠掉的 A 觸發排到佇列。"""
    if not fired:
        return
    ids = [tid for tid, _ in fired]
    merged = _merge_contexts([c for _, c in fired])
    payload = json.dumps({"trigger_ids": ids, "context": merged})
    try:
        r = await _get_redis()
        try:
            await r.rpush(_PENDING_KEY_TMPL.format(project_id=project_id), payload)
            await r.expire(_PENDING_KEY_TMPL.format(project_id=project_id), 600)
        finally:
            await r.aclose()
    except Exception:
        logger.debug("Pending A enqueue failed", exc_info=True)


async def _pop_pending_a(project_id: UUID) -> dict | None:
    try:
        r = await _get_redis()
        try:
            raw = await r.lpop(_PENDING_KEY_TMPL.format(project_id=project_id))
        finally:
            await r.aclose()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def _pending_a_count(project_id: UUID) -> int:
    try:
        r = await _get_redis()
        try:
            return int(await r.llen(_PENDING_KEY_TMPL.format(project_id=project_id)))
        finally:
            await r.aclose()
    except Exception:
        return 0


def _merge_contexts(ctx_list: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in ctx_list:
        out.update(c)
    return out
