"""Phase 26 admin stats: token timeseries 30-min granularity, provider
breakdown, time-axis back-fill, and triggered-by attribution."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import stats as admin_stats
from app.db.models.llm_provider import LLMProvider
from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.user import User


pytestmark = pytest.mark.asyncio


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def two_providers(db_session: AsyncSession) -> tuple[LLMProvider, LLMProvider]:
    a = LLMProvider(
        id=uuid.uuid4(),
        name="alpha",
        kind="vllm",
        tier=1,
        weight=1,
        base_url="https://a/v1",
        model="m-a",
    )
    b = LLMProvider(
        id=uuid.uuid4(),
        name="beta",
        kind="vllm",
        tier=2,
        weight=1,
        base_url="https://b/v1",
        model="m-b",
    )
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


@pytest_asyncio.fixture
async def two_users(db_session: AsyncSession) -> tuple[User, User]:
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
    )
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        password_hash="x",
        display_name="Student",
        role="student",
    )
    db_session.add_all([admin, student])
    await db_session.flush()
    return admin, student


async def _log(
    session: AsyncSession,
    *,
    when: datetime,
    provider: LLMProvider,
    owning_user_id: uuid.UUID,
    triggered_by_user_id: uuid.UUID | None = None,
    total_tokens: int = 100,
    success: bool = True,
) -> None:
    session.add(
        LLMRequestLog(
            created_at=when,
            owning_user_id=owning_user_id,
            triggered_by_user_id=triggered_by_user_id,
            provider_id=provider.id,
            tier_used=provider.tier,
            prompt_tokens=total_tokens // 2,
            completion_tokens=total_tokens - total_tokens // 2,
            total_tokens=total_tokens,
            latency_ms=42,
            success=success,
            caller="test",
        )
    )
    await session.flush()


async def test_30min_buckets_are_aligned(
    db_session: AsyncSession,
    two_providers: tuple[LLMProvider, LLMProvider],
    two_users: tuple[User, User],
) -> None:
    a, _b = two_providers
    admin, _student = two_users
    # Two requests in the same 30-min bucket, one in the next bucket.
    await _log(db_session, when=_ts(2026, 5, 22, 10, 5), provider=a, owning_user_id=admin.id, total_tokens=200)
    await _log(db_session, when=_ts(2026, 5, 22, 10, 25), provider=a, owning_user_id=admin.id, total_tokens=100)
    await _log(db_session, when=_ts(2026, 5, 22, 10, 45), provider=a, owning_user_id=admin.id, total_tokens=50)

    result = await admin_stats.token_timeseries(
        db_session,
        since=_ts(2026, 5, 22, 10, 0),
        until=_ts(2026, 5, 22, 11, 0),
        granularity="30min",
    )
    assert result.granularity == "30min"
    # 2 buckets × 1 provider = 2 points
    assert len(result.points) == 2
    assert result.points[0].bucket_ts == _ts(2026, 5, 22, 10, 0)
    assert result.points[0].total_tokens == 300  # 200 + 100
    assert result.points[1].bucket_ts == _ts(2026, 5, 22, 10, 30)
    assert result.points[1].total_tokens == 50


async def test_provider_breakdown_keeps_zero_buckets(
    db_session: AsyncSession,
    two_providers: tuple[LLMProvider, LLMProvider],
    two_users: tuple[User, User],
) -> None:
    a, b = two_providers
    admin, _ = two_users
    # Provider A in bucket 1; provider B in bucket 2; bucket 0 empty.
    await _log(db_session, when=_ts(2026, 5, 22, 10, 35), provider=a, owning_user_id=admin.id, total_tokens=100)
    await _log(db_session, when=_ts(2026, 5, 22, 11, 5), provider=b, owning_user_id=admin.id, total_tokens=200)

    result = await admin_stats.token_timeseries(
        db_session,
        since=_ts(2026, 5, 22, 10, 0),
        until=_ts(2026, 5, 22, 11, 30),
        granularity="30min",
    )
    # 3 buckets × 2 providers = 6 points, every cell present (zeros filled).
    assert len(result.points) == 6
    assert len(result.providers) == 2
    # Bucket index → provider id → tokens
    by_key = {(p.bucket_ts, p.provider_id): p.total_tokens for p in result.points}
    assert by_key[(_ts(2026, 5, 22, 10, 0), a.id)] == 0
    assert by_key[(_ts(2026, 5, 22, 10, 30), a.id)] == 100
    assert by_key[(_ts(2026, 5, 22, 10, 30), b.id)] == 0
    assert by_key[(_ts(2026, 5, 22, 11, 0), b.id)] == 200


async def test_empty_range_returns_full_timeline(
    db_session: AsyncSession,
    two_providers: tuple[LLMProvider, LLMProvider],
) -> None:
    # No logs at all. 24 buckets of 30min over 12h.
    result = await admin_stats.token_timeseries(
        db_session,
        since=_ts(2026, 5, 22, 0, 0),
        until=_ts(2026, 5, 22, 12, 0),
        granularity="30min",
    )
    # No providers had data → single zero series per bucket.
    assert len(result.providers) == 0
    assert len(result.points) == 24
    assert all(p.total_tokens == 0 for p in result.points)


async def test_user_filter_uses_triggered_by_priority(
    db_session: AsyncSession,
    two_providers: tuple[LLMProvider, LLMProvider],
    two_users: tuple[User, User],
) -> None:
    a, _ = two_providers
    admin, student = two_users
    # Background agent tick (no triggered_by) — attribute via owning.
    await _log(
        db_session,
        when=_ts(2026, 5, 22, 10, 5),
        provider=a,
        owning_user_id=admin.id,
        total_tokens=500,
    )
    # Student is triggering on an admin-owned project — must attribute to student.
    await _log(
        db_session,
        when=_ts(2026, 5, 22, 10, 35),
        provider=a,
        owning_user_id=admin.id,
        triggered_by_user_id=student.id,
        total_tokens=300,
    )

    # Filter by student.
    result = await admin_stats.token_timeseries(
        db_session,
        since=_ts(2026, 5, 22, 10, 0),
        until=_ts(2026, 5, 22, 11, 0),
        user_id=student.id,
        granularity="30min",
    )
    totals = sum(p.total_tokens for p in result.points)
    assert totals == 300

    # Filter by admin (= autonomous agent ticks attributed to project owner).
    result_admin = await admin_stats.token_timeseries(
        db_session,
        since=_ts(2026, 5, 22, 10, 0),
        until=_ts(2026, 5, 22, 11, 0),
        user_id=admin.id,
        granularity="30min",
    )
    totals_admin = sum(p.total_tokens for p in result_admin.points)
    assert totals_admin == 500


async def test_overview_top_users_attributes_triggering_human(
    db_session: AsyncSession,
    two_providers: tuple[LLMProvider, LLMProvider],
    two_users: tuple[User, User],
) -> None:
    a, _ = two_providers
    admin, student = two_users
    # Student triggers 3 calls on admin-owned project.
    for h in range(3):
        await _log(
            db_session,
            when=datetime.now(timezone.utc) - timedelta(hours=h + 1),
            provider=a,
            owning_user_id=admin.id,
            triggered_by_user_id=student.id,
            total_tokens=100,
        )

    overview = await admin_stats.overview_stats(db_session, days=7)
    top_ids = {row.owning_user_id for row in overview.top_users}
    assert student.id in top_ids
    # Admin should NOT show up because no admin-triggered calls happened.
    assert admin.id not in top_ids
