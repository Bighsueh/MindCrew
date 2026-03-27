"""Seed database with test accounts.

Creates 1 teacher + 4 students if they don't already exist.
Idempotent: safe to run multiple times.
"""
import asyncio
import logging

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models.user import User

logger = logging.getLogger(__name__)

TEACHER = {
    "email": "teacher@test.com",
    "password": "teacher123",
    "display_name": "王老師",
    "role": "teacher",
    "can_create_project": True,
}

STUDENTS = [
    {"email": "student1@test.com", "password": "student123", "display_name": "學生一"},
    {"email": "student2@test.com", "password": "student123", "display_name": "學生二"},
    {"email": "student3@test.com", "password": "student123", "display_name": "學生三"},
    {"email": "student4@test.com", "password": "student123", "display_name": "學生四"},
]


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def seed_test_accounts(session: AsyncSession) -> None:
    """Insert test accounts if they don't exist."""
    # --- Teacher ---
    result = await session.execute(
        select(User).where(User.email == TEACHER["email"])
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        teacher = User(
            email=TEACHER["email"],
            password_hash=_hash(TEACHER["password"]),
            display_name=TEACHER["display_name"],
            role="teacher",
            can_create_project=True,
        )
        session.add(teacher)
        await session.flush()
        logger.info("Created teacher: %s", TEACHER["email"])
    else:
        logger.info("Teacher already exists: %s", TEACHER["email"])

    # --- Students ---
    for s in STUDENTS:
        result = await session.execute(
            select(User).where(User.email == s["email"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            student = User(
                email=s["email"],
                password_hash=_hash(s["password"]),
                display_name=s["display_name"],
                role="student",
                can_create_project=False,
                created_by=teacher.id,
            )
            session.add(student)
            logger.info("Created student: %s", s["email"])
        else:
            logger.info("Student already exists: %s", s["email"])

    await session.commit()
    logger.info("Seed complete.")


async def run_seed() -> None:
    """Standalone entry point for seeding."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await seed_test_accounts(session)
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_seed())
