"""Latency analytics for the admin Stats page.

The original Stats page only showed coarse latency *buckets* (request counts
per <500ms / <1s / … band). This module adds the detail admins actually need
to spot a slow provider:

- **Per-provider percentiles** — p50 / p95 / p99 / max / avg / count, plus an
  overall aggregate row. Uses Postgres ``percentile_cont`` (continuous
  interpolation) within group.
- **Latency trend** — avg + p95 per time bucket, with the full range
  back-filled so the line chart has no gaps.

Time-bucket helpers (``_resolve_granularity`` / ``_bucket_expr`` /
``_enumerate_buckets``) are reused from :mod:`app.admin.stats` so the latency
trend lines up exactly with the token / success-rate charts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    LatencyPercentileRow,
    LatencyStatsResponse,
    LatencyTrendPoint,
)
from app.admin.stats import (
    _bucket_expr,
    _enumerate_buckets,
    _resolve_granularity,
)
from app.db.models.llm_provider import LLMProvider
from app.db.models.llm_request_log import LLMRequestLog


def _validate_range(since: datetime, until: datetime) -> None:
    if until <= since:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="until must be strictly greater than since",
        )
    if (until - since) > timedelta(days=90):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="range must be ≤ 90 days",
        )


def _pct(col, q: float):
    """``percentile_cont(q) WITHIN GROUP (ORDER BY col)`` — continuous
    interpolation over latency_ms."""
    return func.percentile_cont(q).within_group(col)


async def latency_stats(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    provider_ids: list[UUID] | None = None,
    granularity: Literal["auto", "30min", "hour", "day"] = "auto",
) -> LatencyStatsResponse:
    """Per-provider latency percentiles + an overall row + a latency trend."""
    _validate_range(since, until)
    resolved = _resolve_granularity(since, until, granularity)

    log = LLMRequestLog
    where = [log.created_at >= since, log.created_at < until]
    if provider_ids:
        where.append(log.provider_id.in_(provider_ids))

    rows = [
        await _overall_row(session, where),
        *await _per_provider_rows(session, log, where),
    ]
    trend = await _latency_trend(session, log, where, since, until, resolved)
    return LatencyStatsResponse(granularity=resolved, rows=rows, trend=trend)


async def _overall_row(session: AsyncSession, where) -> LatencyPercentileRow:
    log = LLMRequestLog
    stmt = select(
        func.count(log.id).label("c"),
        _pct(log.latency_ms, 0.5).label("p50"),
        _pct(log.latency_ms, 0.95).label("p95"),
        _pct(log.latency_ms, 0.99).label("p99"),
        func.max(log.latency_ms).label("mx"),
        func.avg(log.latency_ms).label("avg"),
    ).where(*where)
    r = (await session.execute(stmt)).one()
    return _to_row(None, "全部 (overall)", r)


async def _per_provider_rows(
    session: AsyncSession, log, where
) -> list[LatencyPercentileRow]:
    stmt = (
        select(
            log.provider_id.label("pid"),
            func.count(log.id).label("c"),
            _pct(log.latency_ms, 0.5).label("p50"),
            _pct(log.latency_ms, 0.95).label("p95"),
            _pct(log.latency_ms, 0.99).label("p99"),
            func.max(log.latency_ms).label("mx"),
            func.avg(log.latency_ms).label("avg"),
        )
        .where(*where)
        .group_by(log.provider_id)
    )
    raw = (await session.execute(stmt)).all()
    pids = [r.pid for r in raw if r.pid is not None]
    names: dict[UUID, str] = {}
    if pids:
        prov_rows = (
            await session.execute(
                select(LLMProvider.id, LLMProvider.name).where(
                    LLMProvider.id.in_(pids)
                )
            )
        ).all()
        names = {pr.id: pr.name for pr in prov_rows}
    out = [
        _to_row(r.pid, names.get(r.pid) if r.pid else None, r) for r in raw
    ]
    # Highest p95 first — slowest provider surfaces at the top.
    out.sort(key=lambda x: (x.p95_ms or 0), reverse=True)
    return out


def _to_row(pid, name, r) -> LatencyPercentileRow:
    count = int(r.c or 0)
    return LatencyPercentileRow(
        provider_id=pid,
        provider_name=name,
        request_count=count,
        p50_ms=round(float(r.p50), 1) if r.p50 is not None else None,
        p95_ms=round(float(r.p95), 1) if r.p95 is not None else None,
        p99_ms=round(float(r.p99), 1) if r.p99 is not None else None,
        max_ms=int(r.mx) if r.mx is not None else None,
        avg_ms=round(float(r.avg), 1) if r.avg is not None else None,
    )


async def _latency_trend(
    session: AsyncSession, log, where, since, until, resolved
) -> list[LatencyTrendPoint]:
    bucket = _bucket_expr(log.created_at, resolved).label("bucket")
    stmt = (
        select(
            bucket,
            func.count(log.id).label("c"),
            func.avg(log.latency_ms).label("avg"),
            _pct(log.latency_ms, 0.95).label("p95"),
        )
        .where(*where)
        .group_by("bucket")
        .order_by("bucket")
    )
    indexed: dict[datetime, tuple[int, float | None, float | None]] = {}
    for r in (await session.execute(stmt)).all():
        key_ts = r.bucket
        if key_ts.tzinfo is None:
            key_ts = key_ts.replace(tzinfo=timezone.utc)
        indexed[key_ts] = (
            int(r.c or 0),
            round(float(r.avg), 1) if r.avg is not None else None,
            round(float(r.p95), 1) if r.p95 is not None else None,
        )

    points: list[LatencyTrendPoint] = []
    for b in _enumerate_buckets(since, until, resolved):
        c, avg, p95 = indexed.get(b, (0, None, None))
        points.append(
            LatencyTrendPoint(bucket_ts=b, request_count=c, avg_ms=avg, p95_ms=p95)
        )
    return points
