"""Phase 26 admin stats: success-rate trend with 30-min granularity and
back-filled timeline (empty buckets emit rate=None)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
async def setup_provider_user(db_session: AsyncSession) -> tuple[LLMProvider, User]:
    prov = LLMProvider(
        id=uuid.uuid4(),
        name="solo",
        kind="vllm",
        tier=1,
        weight=1,
        base_url="https://x/v1",
        model="m",
    )
    user = User(
        id=uuid.uuid4(),
        email="u@example.com",
        password_hash="x",
        display_name="U",
        role="student",
    )
    db_session.add_all([prov, user])
    await db_session.flush()
    return prov, user


async def _log(
    session: AsyncSession,
    *,
    when: datetime,
    provider: LLMProvider,
    owning_user_id: uuid.UUID,
    success: bool,
) -> None:
    session.add(
        LLMRequestLog(
            created_at=when,
            owning_user_id=owning_user_id,
            provider_id=provider.id,
            tier_used=provider.tier,
            total_tokens=10,
            latency_ms=10,
            success=success,
            caller="t",
        )
    )
    await session.flush()


async def test_30min_buckets_and_back_fill(
    db_session: AsyncSession,
    setup_provider_user: tuple[LLMProvider, User],
) -> None:
    prov, user = setup_provider_user
    # Bucket 10:00–10:30 → 2 success, 1 fail = 2/3
    await _log(db_session, when=_ts(2026, 5, 22, 10, 5), provider=prov, owning_user_id=user.id, success=True)
    await _log(db_session, when=_ts(2026, 5, 22, 10, 15), provider=prov, owning_user_id=user.id, success=True)
    await _log(db_session, when=_ts(2026, 5, 22, 10, 25), provider=prov, owning_user_id=user.id, success=False)
    # Bucket 10:30–11:00 has nothing.
    # Bucket 11:00–11:30 → 1 success = 100%
    await _log(db_session, when=_ts(2026, 5, 22, 11, 10), provider=prov, owning_user_id=user.id, success=True)

    result = await admin_stats.success_rate_trend(
        db_session,
        since=_ts(2026, 5, 22, 10, 0),
        until=_ts(2026, 5, 22, 11, 30),
        granularity="30min",
    )
    assert result.granularity == "30min"
    assert len(result.points) == 3
    assert result.points[0].bucket_ts == _ts(2026, 5, 22, 10, 0)
    assert result.points[0].request_count == 3
    assert result.points[0].success_count == 2
    assert result.points[0].rate is not None
    assert abs(result.points[0].rate - 2 / 3) < 1e-9
    # Empty bucket gets rate=None.
    assert result.points[1].request_count == 0
    assert result.points[1].rate is None
    assert result.points[2].request_count == 1
    assert result.points[2].rate == 1.0
