"""共用 FastAPI 依賴：專案層級存取守門。

集中「載入 project + 檢查 viewer 權限」的邏輯，供 stages / chat / timer 等跨模組
router 重用，避免每支讀取端點各自重寫守門（或漏寫造成跨使用者外洩）。

存取矩陣以 :mod:`app.projects.access` 為單一真理來源：
creator / 列管老師 / admin 可讀，其餘 403；查無此專案 404。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import get_db_session
from app.projects.access import LEVEL_VIEWER, assert_project_access
from app.projects.repository import ProjectRepository


async def require_project_viewer(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Project:
    """確認 ``current_user`` 對 ``project_id`` 具 viewer 權限，回傳該 Project。

    - 查無專案 → 404 Not Found
    - 有專案但無權（既非 creator / 列管老師 / admin）→ 403 Forbidden

    端點可忽略回傳值（僅作守門），或直接取用以省去重複查詢。
    """
    project = await ProjectRepository(session).get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    assert_project_access(project, current_user, level=LEVEL_VIEWER)
    return project
