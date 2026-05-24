"""Admin console business logic (Phase 25 + 25.J).

Provides CRUD over ``llm_providers``, log list/detail with denormalized
user/project names, and audit access on payload reads. Stats aggregations
moved to ``app.admin.stats`` in Phase 25.L to respect the 500-line file cap.

Phase 25.J: list_logs LEFT JOINs ``user`` (twice, once each for owning and
triggered) and ``project`` so the frontend never has to issue N+1 fetches.
get_log_detail JOINs ``llm_request_payloads`` and writes an
``admin_payload_access`` row so the team can audit PII exposure.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.admin.schemas import (
    HealthCheckResponse,
    LogDetailResponse,
    LogEntryResponse,
    LogListResponse,
    LogMessage,
    PayloadAccessEntry,
    PayloadAccessListResponse,
    ProviderCreateRequest,
    ProviderResponse,
    ProviderUpdateRequest,
    mask_api_key,
)
from app.db.models.admin_payload_access import AdminPayloadAccess
from app.db.models.llm_provider import LLMProvider as LLMProviderRow
from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.llm_request_payload import LLMRequestPayload
from app.db.models.project import Project
from app.db.models.user import User
from app.llm.registry import ProviderRegistry, _build_instance
from app.llm.router import ProviderRouter
from app.security.secrets import decrypt_secret, encrypt_secret


def _to_response(row: LLMProviderRow) -> ProviderResponse:
    return ProviderResponse(
        id=row.id,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        tier=row.tier,
        weight=row.weight,
        base_url=row.base_url,
        model=row.model,
        api_key_masked=mask_api_key(decrypt_secret(row.api_key) or ""),
        azure_api_version=row.azure_api_version,
        azure_deployment=row.azure_deployment,
        enabled=row.enabled,
        max_retries=row.max_retries,
        timeout_seconds=row.timeout_seconds,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ── provider CRUD (unchanged from Phase 25 core) ─────────────────────────


async def list_providers(session: AsyncSession) -> list[ProviderResponse]:
    result = await session.execute(
        select(LLMProviderRow).order_by(LLMProviderRow.tier, LLMProviderRow.name)
    )
    return [_to_response(r) for r in result.scalars().all()]


async def create_provider(
    session: AsyncSession, payload: ProviderCreateRequest
) -> ProviderResponse:
    existing = await session.execute(
        select(LLMProviderRow).where(LLMProviderRow.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider name '{payload.name}' already exists",
        )
    row = LLMProviderRow(
        name=payload.name,
        kind=payload.kind,
        tier=payload.tier,
        weight=payload.weight,
        base_url=payload.base_url,
        model=payload.model,
        api_key=encrypt_secret(payload.api_key or ""),
        azure_api_version=payload.azure_api_version,
        azure_deployment=payload.azure_deployment,
        enabled=payload.enabled,
        max_retries=payload.max_retries,
        timeout_seconds=payload.timeout_seconds,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    ProviderRegistry.invalidate()
    ProviderRouter.reset()
    return _to_response(row)


async def update_provider(
    session: AsyncSession, provider_id: UUID, payload: ProviderUpdateRequest
) -> ProviderResponse:
    row = await session.get(LLMProviderRow, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "api_key":
            if value is None or value == "":
                continue
            value = encrypt_secret(value)
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    ProviderRegistry.invalidate()
    ProviderRouter.reset()
    return _to_response(row)


async def delete_provider(session: AsyncSession, provider_id: UUID) -> None:
    row = await session.get(LLMProviderRow, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider not found")
    await session.delete(row)
    await session.commit()
    ProviderRegistry.invalidate()
    ProviderRouter.reset()


async def health_check_provider(
    session: AsyncSession, provider_id: UUID
) -> HealthCheckResponse:
    row = await session.get(LLMProviderRow, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider not found")
    instance = _build_instance(row)
    t0 = time.monotonic()
    error: str | None = None
    try:
        ok = await instance.health_check()
    except Exception as exc:  # noqa: BLE001
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    return HealthCheckResponse(
        ok=ok,
        provider_id=row.id,
        name=row.name,
        latency_ms=int((time.monotonic() - t0) * 1000),
        error=error,
    )


# ── logs (Phase 25.J: name JOINs + detail) ──────────────────────────────


async def list_logs(
    session: AsyncSession,
    *,
    provider_id: UUID | None = None,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    success: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> LogListResponse:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    log = LLMRequestLog
    prov = LLMProviderRow
    owning = aliased(User, name="owning_user")
    triggered = aliased(User, name="triggered_user")
    proj = aliased(Project, name="proj")

    conditions = []
    if provider_id is not None:
        conditions.append(log.provider_id == provider_id)
    if user_id is not None:
        conditions.append(log.owning_user_id == user_id)
    if project_id is not None:
        conditions.append(log.project_id == project_id)
    if since is not None:
        conditions.append(log.created_at >= since)
    if until is not None:
        conditions.append(log.created_at < until)
    if success is not None:
        conditions.append(log.success.is_(success))

    count_stmt = select(func.count(log.id))
    for c in conditions:
        count_stmt = count_stmt.where(c)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(
            log,
            prov.name.label("provider_name"),
            owning.display_name.label("owning_display_name"),
            triggered.display_name.label("triggered_display_name"),
            proj.name.label("project_name"),
        )
        .outerjoin(prov, prov.id == log.provider_id)
        .outerjoin(owning, owning.id == log.owning_user_id)
        .outerjoin(triggered, triggered.id == log.triggered_by_user_id)
        .outerjoin(proj, proj.id == log.project_id)
        .order_by(log.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    for c in conditions:
        stmt = stmt.where(c)

    rows = (await session.execute(stmt)).all()
    items = [_log_row_to_entry(row) for row in rows]
    return LogListResponse(total=total, limit=limit, offset=offset, items=items)


def _log_row_to_entry(row) -> LogEntryResponse:
    log = row.LLMRequestLog
    return LogEntryResponse(
        id=log.id,
        created_at=log.created_at,
        provider_id=log.provider_id,
        provider_name=row.provider_name,
        owning_user_id=log.owning_user_id,
        owning_user_display_name=row.owning_display_name,
        triggered_by_user_id=log.triggered_by_user_id,
        triggered_by_display_name=row.triggered_display_name,
        project_id=log.project_id,
        project_name=row.project_name,
        tier_used=log.tier_used,
        cascade_from_tier=log.cascade_from_tier,
        prompt_tokens=log.prompt_tokens,
        completion_tokens=log.completion_tokens,
        total_tokens=log.total_tokens,
        latency_ms=log.latency_ms,
        success=log.success,
        error_class=log.error_class,
        error_message=log.error_message,
        caller=log.caller,
    )


async def get_log_detail(
    session: AsyncSession, log_id: int, *, admin_user_id: UUID
) -> LogDetailResponse:
    """Return full log + payload; record an admin_payload_access row."""
    log = LLMRequestLog
    prov = LLMProviderRow
    owning = aliased(User, name="owning_user")
    triggered = aliased(User, name="triggered_user")
    proj = aliased(Project, name="proj")
    payload = LLMRequestPayload

    stmt = (
        select(
            log,
            prov.name.label("provider_name"),
            owning.display_name.label("owning_display_name"),
            triggered.display_name.label("triggered_display_name"),
            proj.name.label("project_name"),
            payload.messages,
            payload.response_content,
            payload.response_finish_reason,
            payload.messages_bytes,
        )
        .outerjoin(prov, prov.id == log.provider_id)
        .outerjoin(owning, owning.id == log.owning_user_id)
        .outerjoin(triggered, triggered.id == log.triggered_by_user_id)
        .outerjoin(proj, proj.id == log.project_id)
        .outerjoin(payload, payload.request_log_id == log.id)
        .where(log.id == log_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Log not found")

    # Audit: every successful detail read is logged. Use a try/except so a
    # transient audit-write failure never blocks the actual content.
    try:
        session.add(
            AdminPayloadAccess(
                admin_user_id=admin_user_id,
                request_log_id=log_id,
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()

    base = _log_row_to_entry(row)
    msgs_raw = row.messages or []
    messages = [
        LogMessage(
            role=str(m.get("role", "user")),
            content=str(m.get("content", "")),
            truncated_chars=m.get("truncated_chars"),
        )
        for m in msgs_raw
        if isinstance(m, dict)
    ]
    return LogDetailResponse(
        **base.model_dump(),
        messages=messages,
        response_content=row.response_content,
        response_finish_reason=row.response_finish_reason,
        messages_bytes=row.messages_bytes or 0,
    )


# ── audit (Phase 25.J) ──────────────────────────────────────────────────


async def list_payload_access(
    session: AsyncSession, *, limit: int = 50
) -> PayloadAccessListResponse:
    limit = max(1, min(limit, 500))
    audit = AdminPayloadAccess
    u = User
    total = (await session.execute(select(func.count(audit.id)))).scalar_one()
    stmt = (
        select(audit, u.display_name.label("admin_display_name"))
        .outerjoin(u, u.id == audit.admin_user_id)
        .order_by(audit.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        PayloadAccessEntry(
            id=r.AdminPayloadAccess.id,
            created_at=r.AdminPayloadAccess.created_at,
            admin_user_id=r.AdminPayloadAccess.admin_user_id,
            admin_display_name=r.admin_display_name,
            request_log_id=r.AdminPayloadAccess.request_log_id,
        )
        for r in rows
    ]
    return PayloadAccessListResponse(total=total, items=items)


# Stats aggregations live in ``app.admin.stats`` to keep this file under the
# CLAUDE.md 500-line limit. See ``stats.overview_stats`` and
# ``stats.token_timeseries``.
