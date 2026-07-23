"""Latency analytics: per-provider percentiles + overall row + trend."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import stats_latency as admin_latency
from app.db.models.llm_provider import LLMProvider
from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.user import User

pytestmark = pytest.mark.asyncio


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 22, 10, minute, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def provider(db_session: AsyncSession) -> LLMProvider:
    p = LLMProvider(
        id=uuid.uuid4(), name="alpha", kind="vllm", tier=1, weight=1,
        base_url="https://a/v1", model="m-a",
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(), email="u@x.com", password_hash="x",
        display_name="U", role="student",
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _log(
    session: AsyncSession, *, provider: LLMProvider, owning: uuid.UUID,
    latency_ms: int, minute: int = 5,
) -> None:
    session.add(
        LLMRequestLog(
            created_at=_ts(minute), owning_user_id=owning, provider_id=provider.id,
            tier_used=provider.tier, prompt_tokens=1, completion_tokens=1,
            total_tokens=2, latency_ms=latency_ms, success=True, caller="test",
        )
    )
    await session.flush()


async def test_percentiles_and_overall_row(
    db_session: AsyncSession, provider, user
) -> None:
    # latencies 100..1000 (10 evenly spaced)
    for i, lat in enumerate(range(100, 1100, 100)):
        await _log(db_session, provider=provider, owning=user.id, latency_ms=lat, minute=i)

    res = await admin_latency.latency_stats(
        db_session, since=_ts(0), until=_ts(59), granularity="30min"
    )

    overall = res.rows[0]
    assert overall.provider_id is None
    assert overall.request_count == 10
    assert overall.max_ms == 1000
    # p50 of [100..1000] continuous interpolation = 550
    assert overall.p50_ms == pytest.approx(550, abs=1)
    # p95 should be high (near the top of the distribution)
    assert overall.p95_ms is not None and overall.p95_ms > overall.p50_ms

    # one per-provider row beneath the overall row
    prov_rows = [r for r in res.rows if r.provider_id == provider.id]
    assert len(prov_rows) == 1
    assert prov_rows[0].provider_name == "alpha"
    assert prov_rows[0].request_count == 10


async def test_trend_backfills_empty_buckets(
    db_session: AsyncSession, provider, user
) -> None:
    await _log(db_session, provider=provider, owning=user.id, latency_ms=200, minute=5)

    res = await admin_latency.latency_stats(
        db_session, since=_ts(0), until=_ts(59), granularity="30min"
    )

    # 2 × 30-min buckets in the hour; first has the call, second is empty.
    assert len(res.trend) == 2
    assert res.trend[0].request_count == 1
    assert res.trend[0].avg_ms == 200
    assert res.trend[1].request_count == 0
    assert res.trend[1].avg_ms is None
    assert res.trend[1].p95_ms is None
