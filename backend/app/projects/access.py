"""專案層級存取守門。

存取矩陣（單一真理來源）：
- creator（學生本人）：唯一可入座參與者；可讀可寫。
- 列管老師（``project.linked_teacher_id == user.id``）：唯讀旁觀，不可入座。
- admin：等同旁觀層級（可讀，不佔席）。
- 其餘任何登入者：403。

供 router / service 共用，集中 RBAC，避免散落各端點的零散判斷。
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.db.models.project import Project
from app.db.models.user import User

# viewer_role 對前端的語意值
VIEWER_ROLE_CREATOR = "creator"      # 可入座
VIEWER_ROLE_OBSERVER = "observer"    # 只能旁觀（列管老師 / admin）

# assert_project_access 的存取層級
LEVEL_PARTICIPANT = "participant"    # 僅 creator（含 admin）
LEVEL_VIEWER = "viewer"              # creator / 列管老師 / admin


def _is_admin(user: User) -> bool:
    return getattr(user, "role", None) == "admin"


def is_creator(project: Project, user: User) -> bool:
    return project.creator_id == user.id


def is_linked_teacher(project: Project, user: User) -> bool:
    return (
        getattr(user, "role", None) == "teacher"
        and project.linked_teacher_id is not None
        and project.linked_teacher_id == user.id
    )


def viewer_role_for(project: Project, user: User) -> str | None:
    """回傳 user 對 project 的角色：``creator`` / ``observer`` / ``None``（無權）。"""
    if is_creator(project, user):
        return VIEWER_ROLE_CREATOR
    if is_linked_teacher(project, user) or _is_admin(user):
        return VIEWER_ROLE_OBSERVER
    return None


def assert_project_access(
    project: Project, user: User, *, level: str = LEVEL_VIEWER
) -> None:
    """檢查 user 是否有權限存取 project，否則丟 403。

    ``level=participant`` → 僅 creator / admin；``level=viewer`` → 另含列管老師。
    """
    if is_creator(project, user) or _is_admin(user):
        return
    if level == LEVEL_VIEWER and is_linked_teacher(project, user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this project",
    )
