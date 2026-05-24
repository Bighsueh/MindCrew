"""Admin stats aggregations (Phase 25.K + 25.L + Phase 26).

Phase 26 changes:

- Token timeseries now supports ``30min`` granularity and **per-provider**
  series. Time axis is back-filled so empty buckets are returned as zeros.
- Success-rate trend split out into ``success_rate_trend()`` with the same
  granularity/since/until shape; default window is the last 24h × 30min.
- Top users / user filter now group by ``COALESCE(triggered_by_user_id,
  owning_user_id)`` so attribution reflects the human who actually triggered
  the call (not the project owner / admin fallback). Background agent ticks
  with no triggering user fall back to ``owning_user_id``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    CallerStatRow,
    HourlyBucket,
    LatencyBucket,
    OverviewStatsResponse,
    ProviderRef,
    SuccessRateTrendPoint,
    SuccessRateTrendResponse,
    TimeseriesPoint,
    TimeseriesResponse,
    TopUserStatRow,
)
from app.db.models.llm_provider import LLMProvider
from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.user import User


# Latency bucket boundaries — inclusive upper. 0 means open-ended (>10s).
_LATENCY_BUCKETS: list[tuple[str, int]] = [
    ("<500ms", 500),
    ("<1s", 1000),
    ("<3s", 3000),
    ("<10s", 10000),
    (">=10s", 0),
]


Granularity = Literal["30min", "hour", "day"]

_BUCKET_SECONDS: dict[str, int] = {
    "30min": 1800,
    "hour": 3600,
    "day": 86400,
}


def _bucket_expr(col, granularity: Granularity):
    """SQL expression that truncates ``col`` to the requested bucket start
    (UTC). Postgres lacks a native ``date_trunc('30 minutes', …)`` so we use
    epoch floor for the 30-minute case; the hour/day cases stay on
    ``date_trunc`` to match the existing indices."""
    if granularity == "30min":
        return func.to_timestamp(
            func.floor(func.extract("epoch", col) / 1800) * 1800
        )
    return func.date_trunc(granularity, col)


def _attributable_user(log) -> "object":
    """Column expression: who is attributed for this row.

    Prefers ``triggered_by_user_id`` (the human who actually initiated the
    call) and falls back to ``owning_user_id`` for autonomous agent ticks.
    """
    return func.coalesce(log.triggered_by_user_id, log.owning_user_id)


async def overview_stats(
    session: AsyncSession, *, days: int = 7
) -> OverviewStatsResponse:
    """Compute four aggregates (success-rate trend moved to its own endpoint).

    Each query is cheap on its own (single index scan + group), and PostgreSQL
    parallelism keeps the round-trip fast.
    """
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    log = LLMRequestLog

    # 1) caller breakdown
    caller_stmt = (
        select(
            log.caller,
            func.count(log.id).label("request_count"),
            func.coalesce(func.sum(log.total_tokens), 0).label("total_tokens"),
        )
        .where(log.created_at >= since)
        .group_by(log.caller)
        .order_by(desc("total_tokens"))
    )
    callers = [
        CallerStatRow(
            caller=r.caller,
            request_count=int(r.request_count or 0),
            total_tokens=int(r.total_tokens or 0),
        )
        for r in (await session.execute(caller_stmt)).all()
    ]

    # 2) top users — Phase 26: attribute to COALESCE(triggered_by, owning).
    u = User
    attr_user = _attributable_user(log).label("attr_user_id")
    user_stmt = (
        select(
            attr_user,
            u.display_name,
            u.role,
            func.count(log.id).label("request_count"),
            func.coalesce(func.sum(log.total_tokens), 0).label("total_tokens"),
        )
        .outerjoin(u, u.id == _attributable_user(log))
        .where(log.created_at >= since)
        .group_by("attr_user_id", u.display_name, u.role)
        .order_by(desc("total_tokens"))
        .limit(10)
    )
    top_users = [
        TopUserStatRow(
            owning_user_id=r.attr_user_id,
            display_name=r.display_name,
            role=r.role,
            request_count=int(r.request_count or 0),
            total_tokens=int(r.total_tokens or 0),
        )
        for r in (await session.execute(user_stmt)).all()
        if r.attr_user_id is not None
    ]

    # 3) hourly heatmap — 24 buckets, hour 0..23 UTC
    hour_col = func.extract("hour", log.created_at).label("hour")
    hour_stmt = (
        select(
            hour_col,
            func.count(log.id).label("request_count"),
            func.coalesce(func.sum(log.total_tokens), 0).label("total_tokens"),
        )
        .where(log.created_at >= since)
        .group_by(hour_col)
        .order_by(hour_col)
    )
    raw_hours = {
        int(r.hour): (int(r.request_count or 0), int(r.total_tokens or 0))
        for r in (await session.execute(hour_stmt)).all()
    }
    hourly = [
        HourlyBucket(
            hour=h,
            request_count=raw_hours.get(h, (0, 0))[0],
            total_tokens=raw_hours.get(h, (0, 0))[1],
        )
        for h in range(24)
    ]

    # 4) latency buckets — single CASE WHEN
    latency_case = case(
        (log.latency_ms < 500, "<500ms"),
        (log.latency_ms < 1000, "<1s"),
        (log.latency_ms < 3000, "<3s"),
        (log.latency_ms < 10000, "<10s"),
        else_=">=10s",
    ).label("bucket")
    lat_stmt = (
        select(latency_case, func.count(log.id).label("request_count"))
        .where(log.created_at >= since)
        .group_by(latency_case)
    )
    raw_lat = {
        r.bucket: int(r.request_count or 0)
        for r in (await session.execute(lat_stmt)).all()
    }
    latency_buckets = [
        LatencyBucket(label=label, upper_ms=upper, request_count=raw_lat.get(label, 0))
        for label, upper in _LATENCY_BUCKETS
    ]

    return OverviewStatsResponse(
        days=days,
        callers=callers,
        top_users=top_users,
        hourly=hourly,
        latency_buckets=latency_buckets,
    )


# ── timeseries (Phase 25.L + Phase 26 provider/30min) ───────────────────


def _resolve_granularity(
    since: datetime, until: datetime, requested: Literal["auto", "30min", "hour", "day"]
) -> Granularity:
    """Pick a sensible bucket size when caller asks for ``auto``; otherwise
    honor the explicit choice but reject combos that would explode the SVG
    client (too many buckets)."""
    delta = until - since
    if requested == "auto":
        if delta <= timedelta(hours=48):
            return "30min"
        if delta <= timedelta(days=7):
            return "hour"
        return "day"
    if requested == "30min" and delta > timedelta(days=3):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="granularity=30min requires a range ≤ 3 days",
        )
    if requested == "hour" and delta > timedelta(days=14):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="granularity=hour requires a range ≤ 14 days",
        )
    return requested


def _floor_to_bucket(ts: datetime, granularity: Granularity) -> datetime:
    """Floor a UTC timestamp to the start of its bucket (matches the SQL
    expression in ``_bucket_expr``)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    epoch = int(ts.timestamp())
    step = _BUCKET_SECONDS[granularity]
    if granularity == "day":
        # date_trunc('day') keeps local midnight in UTC; epoch floor matches
        # because day == 86400s and UTC has no DST.
        floored = epoch - (epoch % step)
    else:
        floored = epoch - (epoch % step)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _enumerate_buckets(
    since: datetime, until: datetime, granularity: Granularity
) -> list[datetime]:
    """Generate the full bucket sequence ``[since_floor, …, < until)``."""
    step = timedelta(seconds=_BUCKET_SECONDS[granularity])
    cur = _floor_to_bucket(since, granularity)
    out: list[datetime] = []
    while cur < until:
        out.append(cur)
        cur = cur + step
    return out


async def token_timeseries(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    user_id: UUID | None = None,
    provider_ids: list[UUID] | None = None,
    granularity: Literal["auto", "30min", "hour", "day"] = "auto",
) -> TimeseriesResponse:
    """Token usage bucketed by time × provider.

    Returns one row per ``(bucket_ts, provider_id)`` pair, with empty
    buckets back-filled as zeros so the frontend can render a continuous
    timeline.
    """
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

    resolved = _resolve_granularity(since, until, granularity)

    log = LLMRequestLog
    bucket = _bucket_expr(log.created_at, resolved).label("bucket")

    where_clauses = [log.created_at >= since, log.created_at < until]
    if user_id is not None:
        # Attribution: who is using the system right now (triggered_by) takes
        # priority; agent ticks attributed to project owner via fallback.
        where_clauses.append(_attributable_user(log) == user_id)
    if provider_ids:
        where_clauses.append(log.provider_id.in_(provider_ids))

    stmt = (
        select(
            bucket,
            log.provider_id.label("provider_id"),
            func.count(log.id).label("request_count"),
            func.coalesce(func.sum(log.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(log.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(log.total_tokens), 0).label("total_tokens"),
        )
        .where(*where_clauses)
        .group_by("bucket", log.provider_id)
        .order_by("bucket")
    )

    raw_rows = (await session.execute(stmt)).all()

    # Resolve the set of providers that should appear in the chart.
    # We always return every provider that has data in-range (so the legend
    # shows all relevant series), plus any explicitly requested ones (so the
    # frontend can lock the legend even when a series is currently empty).
    provider_ids_in_data = {row.provider_id for row in raw_rows if row.provider_id is not None}
    if provider_ids:
        provider_ids_in_data.update(provider_ids)

    if provider_ids_in_data:
        prov_stmt = select(LLMProvider.id, LLMProvider.name).where(
            LLMProvider.id.in_(provider_ids_in_data)
        )
        provider_rows = (await session.execute(prov_stmt)).all()
        providers = [ProviderRef(id=r.id, name=r.name) for r in provider_rows]
        providers.sort(key=lambda p: p.name)
    else:
        providers = []

    # Index raw rows for back-fill.
    indexed: dict[tuple[datetime, UUID], dict[str, int]] = {}
    for row in raw_rows:
        key_ts = row.bucket
        if key_ts.tzinfo is None:
            key_ts = key_ts.replace(tzinfo=timezone.utc)
        indexed[(key_ts, row.provider_id)] = {
            "request_count": int(row.request_count or 0),
            "prompt_tokens": int(row.prompt_tokens or 0),
            "completion_tokens": int(row.completion_tokens or 0),
            "total_tokens": int(row.total_tokens or 0),
        }

    buckets = _enumerate_buckets(since, until, resolved)
    points: list[TimeseriesPoint] = []
    if providers:
        for b in buckets:
            for p in providers:
                vals = indexed.get((b, p.id))
                points.append(
                    TimeseriesPoint(
                        bucket_ts=b,
                        provider_id=p.id,
                        request_count=(vals or {}).get("request_count", 0),
                        prompt_tokens=(vals or {}).get("prompt_tokens", 0),
                        completion_tokens=(vals or {}).get("completion_tokens", 0),
                        total_tokens=(vals or {}).get("total_tokens", 0),
                    )
                )
    else:
        # No data and no explicit provider filter — emit zero-only buckets so
        # the chart still draws an empty grid spanning the requested range.
        for b in buckets:
            points.append(
                TimeseriesPoint(
                    bucket_ts=b,
                    provider_id=None,
                    request_count=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                )
            )

    return TimeseriesResponse(
        granularity=resolved,
        providers=providers,
        points=points,
    )


# ── success rate trend (Phase 26) ──────────────────────────────────────


async def success_rate_trend(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    granularity: Literal["auto", "30min", "hour", "day"] = "auto",
) -> SuccessRateTrendResponse:
    """Success rate by time bucket, with the full timeline back-filled.

    Empty buckets are returned with ``request_count=0`` and ``rate=None`` so
    the chart can render a gap rather than a misleading 0% point.
    """
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

    resolved = _resolve_granularity(since, until, granularity)

    log = LLMRequestLog
    bucket = _bucket_expr(log.created_at, resolved).label("bucket")
    success_count = func.sum(case((log.success.is_(True), 1), else_=0)).label(
        "success_count"
    )
    stmt = (
        select(
            bucket,
            func.count(log.id).label("request_count"),
            success_count,
        )
        .where(log.created_at >= since, log.created_at < until)
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = (await session.execute(stmt)).all()

    indexed: dict[datetime, tuple[int, int]] = {}
    for r in rows:
        key_ts = r.bucket
        if key_ts.tzinfo is None:
            key_ts = key_ts.replace(tzinfo=timezone.utc)
        indexed[key_ts] = (int(r.request_count or 0), int(r.success_count or 0))

    points: list[SuccessRateTrendPoint] = []
    for b in _enumerate_buckets(since, until, resolved):
        rc, sc = indexed.get(b, (0, 0))
        points.append(
            SuccessRateTrendPoint(
                bucket_ts=b,
                request_count=rc,
                success_count=sc,
                rate=(sc / rc) if rc else None,
            )
        )

    return SuccessRateTrendResponse(granularity=resolved, points=points)
