from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.db.base import Base
from app.db.session import get_db_session
from app.events.bus import event_bus
from app.main import app

# Import all models
from app.db.models.user import User  # noqa: F401
from app.db.models.project import Project  # noqa: F401
from app.db.models.seat import Seat  # noqa: F401
from app.db.models.message import Message  # noqa: F401
from app.db.models.stage_history import StageHistory  # noqa: F401
from app.db.models.agent_decision_trace import AgentDecisionTrace  # noqa: F401
from app.db.models.stage_evaluation_log import StageEvaluationLog  # noqa: F401

# Replace only the database name (last path segment)
_base_url = settings.DATABASE_URL.rsplit("/", 1)[0]
TEST_DB_URL = f"{_base_url}/dtai_test"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session
        await session.rollback()

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db_session] = override_get_db

    # Ensure EventBus is initialised for tests that trigger seat manager events.
    # Always re-initialize: prior test teardowns may have closed the Redis connection.
    await event_bus.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
