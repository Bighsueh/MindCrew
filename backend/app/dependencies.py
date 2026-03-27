from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session


async def get_db(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    return session
