"""共用：專案是否有「可 force-advance 的引導者」。

「引導者」＝綁定教師（`linked_teacher_id`）或 creator 為 teacher/admin。無引導者
（單人學生自建、老師代碼留空 / 全 AI 無教師）時，硬格/邊界超時若仍等教師 force 會永久
卡死——故 progression watcher（細格）與 evaluator（micro/macro 邊界）都據此啟用 time-box
安全閥（v4.17，盲測 2026-06-08）。查詢失敗保守回 True（維持「等引導者」舊行為，不貿然跳）。
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def has_facilitator(project_id: UUID) -> bool:
    from app.db.models.project import Project
    from app.db.models.user import User

    try:
        async with async_session_factory() as session:
            row = await session.execute(
                select(Project.creator_id, Project.linked_teacher_id).where(
                    Project.id == project_id
                )
            )
            rec = row.first()
            if rec is None:
                return True
            creator_id, linked_teacher_id = rec
            if linked_teacher_id is not None:
                return True
            role = (
                await session.execute(select(User.role).where(User.id == creator_id))
            ).scalar_one_or_none()
            return role in ("teacher", "admin")
    except Exception:
        logger.debug("has_facilitator failed project=%s", project_id, exc_info=True)
        return True


__all__ = ["has_facilitator"]
