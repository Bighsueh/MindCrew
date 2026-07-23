"""Admin log explorer: caller / model / triggered-by filters + the model
column denormalized from the provider join."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.db.models.llm_provider import LLMProvider
from app.db.models.llm_request_log import LLMRequestLog
from app.db.models.user import User

pytestmark = pytest.mark.asyncio


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 22, 10, minute, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def providers(db_session: AsyncSession) -> tuple[LLMProvider, LLMProvider]:
    a = LLMProvider(
        id=uuid.uuid4(), name="alpha", kind="vllm", tier=1, weight=1,
        base_url="https://a/v1", model="gemma-26b",
    )
    b = LLMProvider(
        id=uuid.uuid4(), name="beta", kind="vllm", tier=2, weight=1,
        base_url="https://b/v1", model="gpt-4o",
    )
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> tuple[User, User]:
    owner = User(
        id=uuid.uuid4(), email="owner@x.com", password_hash="x",
        display_name="Owner", role="student",
    )
    human = User(
        id=uuid.uuid4(), email="human@x.com", password_hash="x",
        display_name="Human", role="student",
    )
    db_session.add_all([owner, human])
    await db_session.flush()
    return owner, human


async def _log(
    session: AsyncSession, *, provider: LLMProvider, owning: uuid.UUID,
    caller: str, triggered: uuid.UUID | None = None, success: bool = True,
    minute: int = 5,
) -> None:
    session.add(
        LLMRequestLog(
            created_at=_ts(minute), owning_user_id=owning,
            triggered_by_user_id=triggered, provider_id=provider.id,
            tier_used=provider.tier, prompt_tokens=10, completion_tokens=10,
            total_tokens=20, latency_ms=42, success=success, caller=caller,
        )
    )
    await session.flush()


async def test_model_column_comes_from_provider_join(
    db_session: AsyncSession, providers, users
) -> None:
    a, _ = providers
    owner, _ = users
    await _log(db_session, provider=a, owning=owner.id, caller="agent_think")

    res = await admin_service.list_logs(db_session)

    assert res.total == 1
    assert res.items[0].model == "gemma-26b"
    assert res.items[0].provider_name == "alpha"


async def test_filter_by_caller(db_session: AsyncSession, providers, users) -> None:
    a, _ = providers
    owner, _ = users
    await _log(db_session, provider=a, owning=owner.id, caller="agent_think", minute=5)
    await _log(db_session, provider=a, owning=owner.id, caller="dt_coach", minute=6)

    res = await admin_service.list_logs(db_session, caller="dt_coach")

    assert res.total == 1
    assert res.items[0].caller == "dt_coach"


async def test_filter_by_model(db_session: AsyncSession, providers, users) -> None:
    a, b = providers
    owner, _ = users
    await _log(db_session, provider=a, owning=owner.id, caller="x", minute=5)
    await _log(db_session, provider=b, owning=owner.id, caller="x", minute=6)

    res = await admin_service.list_logs(db_session, model="gpt-4o")

    assert res.total == 1
    assert res.items[0].model == "gpt-4o"
    assert res.items[0].provider_name == "beta"


async def test_filter_by_triggered_by_user(
    db_session: AsyncSession, providers, users
) -> None:
    a, _ = providers
    owner, human = users
    # autonomous tick (no trigger) + human-triggered call
    await _log(db_session, provider=a, owning=owner.id, caller="agent_think", minute=5)
    await _log(
        db_session, provider=a, owning=human.id, triggered=human.id,
        caller="dt_coach", minute=6,
    )

    res = await admin_service.list_logs(db_session, triggered_by_user_id=human.id)

    assert res.total == 1
    assert res.items[0].triggered_by_user_id == human.id
