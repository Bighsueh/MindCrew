"""FastAPI routes for /api/admin (Phase 25 + 25.J/K/L).

All routes require ``role == 'admin'`` via the ``require_admin`` dependency.
Phase 25.J adds ``GET /logs/{id}`` and ``GET /audit/payload-access``.
Phase 25.K adds ``GET /stats/overview``.
Phase 25.L replaces ``GET /stats/daily`` with ``GET /stats/timeseries``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin import stats as admin_stats
from app.admin.dependencies import require_admin
from app.admin.schemas import (
    HealthCheckResponse,
    LogDetailResponse,
    LogListResponse,
    OverviewStatsResponse,
    PayloadAccessListResponse,
    ProviderCreateRequest,
    ProviderResponse,
    ProviderUpdateRequest,
    SuccessRateTrendResponse,
    TimeseriesResponse,
)
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ── providers ───────────────────────────────────────────────────────────


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderResponse]:
    return await admin_service.list_providers(session)


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    payload: ProviderCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProviderResponse:
    return await admin_service.create_provider(session, payload)


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: UUID,
    payload: ProviderUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProviderResponse:
    return await admin_service.update_provider(session, provider_id, payload)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await admin_service.delete_provider(session, provider_id)


@router.post(
    "/providers/{provider_id}/health-check", response_model=HealthCheckResponse
)
async def health_check_provider(
    provider_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> HealthCheckResponse:
    return await admin_service.health_check_provider(session, provider_id)


# ── logs + audit ────────────────────────────────────────────────────────


@router.get("/logs", response_model=LogListResponse)
async def list_logs(
    provider_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    success: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> LogListResponse:
    return await admin_service.list_logs(
        session,
        provider_id=provider_id,
        user_id=user_id,
        project_id=project_id,
        since=since,
        until=until,
        success=success,
        limit=limit,
        offset=offset,
    )


@router.get("/logs/{log_id}", response_model=LogDetailResponse)
async def get_log_detail(
    log_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin_user: User = Depends(require_admin),
) -> LogDetailResponse:
    return await admin_service.get_log_detail(
        session, log_id, admin_user_id=admin_user.id
    )


@router.get("/audit/payload-access", response_model=PayloadAccessListResponse)
async def list_payload_access(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> PayloadAccessListResponse:
    return await admin_service.list_payload_access(session, limit=limit)


# ── stats ───────────────────────────────────────────────────────────────


@router.get("/stats/overview", response_model=OverviewStatsResponse)
async def overview_stats(
    days: int = Query(default=7, ge=1, le=90),
    session: AsyncSession = Depends(get_db_session),
) -> OverviewStatsResponse:
    return await admin_stats.overview_stats(session, days=days)


@router.get("/stats/timeseries", response_model=TimeseriesResponse)
async def token_timeseries(
    since: datetime = Query(..., description="ISO 8601 UTC; inclusive"),
    until: datetime = Query(..., description="ISO 8601 UTC; exclusive"),
    user_id: UUID | None = Query(
        default=None,
        description=(
            "Filter by attributable user — matches "
            "COALESCE(triggered_by_user_id, owning_user_id)."
        ),
    ),
    provider_ids: list[UUID] | None = Query(
        default=None,
        description="Repeat to filter to a subset of providers (multi-select).",
    ),
    granularity: Literal["auto", "30min", "hour", "day"] = Query(default="auto"),
    session: AsyncSession = Depends(get_db_session),
) -> TimeseriesResponse:
    """Token usage line chart data, split by provider, with full-range
    back-fill so the X axis has no gaps.

    ``granularity=auto`` picks ``30min`` for ≤ 48h, ``hour`` for ≤ 7d, else
    ``day``. ``30min`` is capped at 3 days, ``hour`` at 14 days, range total
    at 90 days (all 422 on violation).
    """
    return await admin_stats.token_timeseries(
        session,
        since=since,
        until=until,
        user_id=user_id,
        provider_ids=provider_ids,
        granularity=granularity,
    )


@router.get("/stats/success-rate", response_model=SuccessRateTrendResponse)
async def success_rate_trend(
    since: datetime = Query(..., description="ISO 8601 UTC; inclusive"),
    until: datetime = Query(..., description="ISO 8601 UTC; exclusive"),
    granularity: Literal["auto", "30min", "hour", "day"] = Query(default="auto"),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessRateTrendResponse:
    """Success-rate trend with the same bucket semantics as token timeseries.

    Phase 26 split this out of overview-stats so the frontend can pick its
    own window (default in the UI: last 24h × 30min) and refresh
    independently.
    """
    return await admin_stats.success_rate_trend(
        session,
        since=since,
        until=until,
        granularity=granularity,
    )
