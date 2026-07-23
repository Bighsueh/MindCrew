from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.auth.codes import generate_code
from app.db.models.project import Project
from app.db.models.seat import (
    Seat,
    SEAT_ROLE_SUPERVISOR,
    SEAT_ROLE_HUMAN_CREATOR,
    SEAT_STATE_DORMANT,
    SEAT_STATE_AI_RUNNING,
    SEAT_STATE_VACANT,
)
from app.db.models.user import User
from app.events.bus import event_bus
from app.events.types import TurnPolicyChangedEvent
from app.projects.access import (
    assert_project_access,
    viewer_role_for,
    LEVEL_VIEWER,
)
from app.projects.repository import ProjectRepository
from app.projects.schemas import (
    ALLOWED_TURN_POLICIES,
    CanvasNoteResponse,
    CanvasStateResponse,
    DEFAULT_TURN_POLICY,
    JoinRequest,
    JoinResponse,
    LinkedTeacherInfo,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
    SeatResponse,
)
from app.seats.colors import seed_seat_colors
from app.seats.manager import seat_manager


async def _allocate_invite_code(session: AsyncSession) -> str:
    """為新專案分配唯一 invite_code（碰撞重試）。"""
    for _ in range(16):
        code = generate_code()
        existing = await session.execute(
            select(Project.id).where(Project.invite_code == code)
        )
        if existing.first() is None:
            return code
    raise RuntimeError("Unable to allocate unique invite_code")


async def _resolve_teacher_by_signature(
    session: AsyncSession, signature_code: str
) -> User:
    """查 teacher，否則 422。"""
    result = await session.execute(
        select(User).where(
            User.signature_code == signature_code.strip().upper(),
            User.role == "teacher",
        )
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="找不到此老師代碼",
        )
    return teacher


async def _load_linked_teacher(
    session: AsyncSession, teacher_id: UUID | None
) -> LinkedTeacherInfo | None:
    if teacher_id is None:
        return None
    teacher = await session.get(User, teacher_id)
    if teacher is None:
        return None
    return LinkedTeacherInfo(id=teacher.id, display_name=teacher.display_name)


async def _publish_turn_policy_changed(
    project_id: UUID, policy: str, changed_by: str
) -> None:
    """Phase 28：廣播 turn_policy 變更（ws/chat_ws.py forwarder 已加白名單）。

    publish 失敗不應該阻塞 API（agent loop 每次 ASSESS 重讀 DB 也會即時生效），
    所以 catch 起來只 log。
    """
    try:
        await event_bus.publish(
            TurnPolicyChangedEvent(
                project_id=project_id, policy=policy, changed_by=changed_by
            )
        )
    except Exception as exc:  # pragma: no cover - best-effort broadcast
        logging.getLogger(__name__).warning(
            "Failed to publish turn_policy_changed for %s: %s", project_id, exc
        )

logger = logging.getLogger(__name__)

def _seat_roles_for(ai_crew_count: int) -> list[str]:
    """Phase 21：依教師選的人數動態產生席位清單。Supervisor 固定一位，crew 從 crew_1 開始連續。"""
    return ["supervisor"] + [f"crew_{i}" for i in range(1, ai_crew_count + 1)]


# Phase 21: 在第一位真人入座前，AI 座位以此狀態存放（不啟動 agent、前端顯示「待加入」）。
# SEAT_STATE_* / SEAT_ROLE_* 常數定義集中於 app.db.models.seat（單一真理來源），於檔首匯入。


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)
        self.session = session

    async def create_project(
        self, request: ProjectCreateRequest, user: User
    ) -> ProjectResponse:
        if user.role == "student" and not user.can_create_project:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create projects",
            )

        invite_code = await _allocate_invite_code(self.session)

        linked_teacher_id: UUID | None = None
        if request.teacher_signature_code:
            teacher = await _resolve_teacher_by_signature(
                self.session, request.teacher_signature_code
            )
            linked_teacher_id = teacher.id

        # Phase 27：stakeholders 已由 schema validator 確保（若提供則 len == ai_crew_count）。
        # 有 stakeholders 表示走 Open Brief 三步驟 wizard，標記 task_brief_kind='open'。
        stakeholders_payload: list[dict[str, str]] = []
        if request.stakeholders:
            stakeholders_payload = [
                {
                    "id": s.id or "",
                    "name": s.name,
                    "role": s.role,
                    "relevance": s.relevance or "",
                    "selected": True,
                }
                for s in request.stakeholders
            ]
        task_brief_kind = "open" if stakeholders_payload else "legacy"

        project_kwargs: dict[str, object] = dict(
            name=request.name,
            description=request.description,
            constraints=request.constraints,
            stakeholders=stakeholders_payload,
            task_brief_kind=task_brief_kind,
            creator_id=user.id,
            ai_contribution=request.ai_contribution,
            invite_code=invite_code,
            linked_teacher_id=linked_teacher_id,
        )
        # Phase 28：建立時若有提供 turn_policy 就帶入，否則由 DB server_default 補 'cued'。
        if request.turn_policy is not None:
            project_kwargs["turn_policy"] = request.turn_policy
        project = Project(**project_kwargs)
        project = await self.repo.create(project)

        # Build persona lookup from request (if supplied)
        persona_by_role: dict[str, dict] = {}
        if request.personas:
            for assignment in request.personas:
                payload = assignment.persona.model_dump()
                if hasattr(assignment.persona.lens_affinities, "model_dump"):
                    payload["lens_affinities"] = (
                        assignment.persona.lens_affinities.model_dump()
                    )
                persona_by_role[assignment.seat_role] = payload

        seat_roles = _seat_roles_for(request.ai_crew_count)
        seats: list[Seat] = []
        for role in seat_roles:
            seat = Seat(
                project_id=project.id,
                seat_role=role,
                occupant_type="ai",
                # Phase 21：建立時 AI agents 全部 dormant，agent_id 留空，
                # 等第一位真人入座才會被 seat_manager 激活。
                agent_id=None,
                state=SEAT_STATE_DORMANT,
                persona=persona_by_role.get(role) if role != "supervisor" else None,
            )
            self.session.add(seat)
            seats.append(seat)

        # 真人專屬席（額外 +1）：綁定 creator，但 user_id 留空到入座為止。
        # 以 occupant_type="human" + user_id=NULL + state="vacant" 表示「空席」，
        # 如此所有 occupant_type=="ai" 的 agent 生成路徑都會天生跳過它。
        human_seat = Seat(
            project_id=project.id,
            seat_role=SEAT_ROLE_HUMAN_CREATOR,
            occupant_type="human",
            user_id=None,
            agent_id=None,
            state=SEAT_STATE_VACANT,
            persona=None,
        )
        self.session.add(human_seat)
        seats.append(human_seat)

        # Phase 22：seed 每個席位的 sticky_color（shuffle 8 色）
        seed_seat_colors(seats)
        await self.session.flush()

        # ：建立專案時同步初始化 timer。
        # timer_config 為必填欄位（schemas.py），由建立者明確選擇。
        # 失敗不再 swallow——沒 timer 的 project 不該存在。
        from app.timer.schemas import TimerState, now_iso
        from app.timer.service import TimerService
        config = await TimerService.initialize_project(
            project.id, config=request.timer_config
        )
        # 專案入口 = 暖場 macro stage 的第一格 0.0a（Alternative Uses 破冰遊戲）。
        await TimerService.start_phase(project.id, "0.0a")
        # 直接在本 session 寫頂層欄位（保證活動建立即就位）。
        # 上面兩個 TimerService 走獨立 session、在本 session 尚未 commit 時對未可見的
        # project row UPDATE 為 no-op；故 current_* **以及 timer_config / timer_state** 都
        # 必須在此 session 直接寫到 project 物件，否則：
        #   - current_sub_phase NULL → progression_watcher 永不開工（keystone）；
        #   - timer_config 不落 → get_config fallback DEFAULT_PRESET、創建者選的 preset 被吞；
        #   - timer_state.phase_started_at 不落 → 暖場計時器永不啟動：5 分硬上限兜底失效
        #     （spec 28 §5.3 防死鎖）、watcher 永不廣播 timer_state → 真人便條拿不到 sub_phase。
        project.timer_config = config.model_dump()
        project.timer_state = TimerState(
            current_sub_phase="0.0a", phase_started_at=now_iso()
        ).model_dump()
        project.current_stage = "warmup"
        project.current_micro_phase = "0.0"
        project.current_sub_phase = "0.0a"
        await self.session.flush()

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            constraints=project.constraints,
            stakeholders=list(project.stakeholders or []),
            task_brief_kind=project.task_brief_kind,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
            invite_code=project.invite_code,
            linked_teacher=await _load_linked_teacher(
                self.session, project.linked_teacher_id
            ),
            turn_policy=project.turn_policy,
            tour_acknowledged_by=dict(project.tour_acknowledged_by or {}),
            # 剛建立者必為 creator。
            viewer_role=viewer_role_for(project, user),
        )

    async def list_projects(self, user: User) -> list[ProjectListItem]:
        projects = await self.repo.list_user_projects(user.id)
        result = []
        for p in projects:
            seats = await self.repo.get_seats(p.id)
            human_count = sum(
                1 for s in seats if s.occupant_type == "human" and s.user_id is not None
            )
            ai_count = sum(1 for s in seats if s.occupant_type == "ai")
            result.append(
                ProjectListItem(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    current_stage=p.current_stage,
                    status=p.status,
                    creator_id=p.creator_id,
                    seat_summary={"human": human_count, "ai": ai_count},
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    invite_code=p.invite_code,
                    linked_teacher=await _load_linked_teacher(
                        self.session, p.linked_teacher_id
                    ),
                    turn_policy=p.turn_policy,
                )
            )
        return result

    async def get_project(self, project_id: UUID, user: User) -> ProjectResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        # 存取守門：creator / 列管老師 / admin 才可讀，其餘 403。
        assert_project_access(project, user, level=LEVEL_VIEWER)
        seats = await self.repo.get_seats(project_id)
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            constraints=project.constraints,
            stakeholders=list(project.stakeholders or []),
            task_brief_kind=project.task_brief_kind,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
            invite_code=project.invite_code,
            linked_teacher=await _load_linked_teacher(
                self.session, project.linked_teacher_id
            ),
            turn_policy=project.turn_policy,
            tour_acknowledged_by=dict(project.tour_acknowledged_by or {}),
            viewer_role=viewer_role_for(project, user),
        )

    async def link_teacher(
        self, project_id: UUID, signature_code: str, user: User
    ) -> ProjectResponse:
        """學生（creator）將活動列管於指定老師。"""
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        if project.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator may link a teacher",
            )
        if project.linked_teacher_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此活動已列管於其他老師，請先解除",
            )
        teacher = await _resolve_teacher_by_signature(self.session, signature_code)
        project.linked_teacher_id = teacher.id
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return await self.get_project(project_id, user)

    async def unlink_teacher(
        self, project_id: UUID, user: User
    ) -> ProjectResponse:
        """creator 或目前列管的老師都可解除。"""
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        if project.linked_teacher_id is None:
            return await self.get_project(project_id, user)
        if user.id not in (project.creator_id, project.linked_teacher_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only creator or linked teacher may unlink",
            )
        project.linked_teacher_id = None
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return await self.get_project(project_id, user)

    async def track_by_invite_code(
        self, invite_code: str, teacher: User
    ) -> ProjectResponse:
        """老師輸入活動 invite_code 列管之。"""
        if teacher.role != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only teachers can track activities",
            )
        result = await self.session.execute(
            select(Project).where(
                Project.invite_code == invite_code.strip().upper()
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到此活動代碼",
            )
        if (
            project.linked_teacher_id is not None
            and project.linked_teacher_id != teacher.id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此活動已列管於其他老師",
            )
        project.linked_teacher_id = teacher.id
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return await self.get_project(project.id, teacher)

    async def update_project(
        self, project_id: UUID, request: ProjectUpdateRequest, user: User
    ) -> ProjectResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        if project.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator may update this project",
            )
        if request.name is not None:
            project.name = request.name
        if request.description is not None:
            project.description = request.description
        if request.constraints is not None:
            project.constraints = request.constraints
        if request.ai_contribution is not None:
            project.ai_contribution = request.ai_contribution
        turn_policy_changed = False
        if request.turn_policy is not None and request.turn_policy != project.turn_policy:
            project.turn_policy = request.turn_policy
            turn_policy_changed = True
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        if turn_policy_changed:
            await _publish_turn_policy_changed(
                project_id, project.turn_policy, str(user.id)
            )

        seats = await self.repo.get_seats(project_id)
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            constraints=project.constraints,
            stakeholders=list(project.stakeholders or []),
            task_brief_kind=project.task_brief_kind,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
            invite_code=project.invite_code,
            linked_teacher=await _load_linked_teacher(
                self.session, project.linked_teacher_id
            ),
            turn_policy=project.turn_policy,
            tour_acknowledged_by=dict(project.tour_acknowledged_by or {}),
        )

    async def update_turn_policy(
        self, project_id: UUID, policy: str, user: User
    ) -> tuple[str, datetime]:
        """Phase 28：教師/admin 切換專案 turn_policy。

        權限：``user.role == 'teacher'`` 且（``project.linked_teacher_id == user.id``
        或 ``user.role == 'admin'``）。creator 想改自己的專案請走 ``PATCH /api/projects/{id}``。
        """
        if policy not in ALLOWED_TURN_POLICIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"policy 必須為 {ALLOWED_TURN_POLICIES} 其中之一",
            )

        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # admin 可改任何專案；teacher 只能改自己列管的專案
        is_admin = user.role == "admin"
        is_linked_teacher = (
            user.role == "teacher" and project.linked_teacher_id == user.id
        )
        if not (is_admin or is_linked_teacher):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the linked teacher or an admin may change turn_policy",
            )

        if project.turn_policy != policy:
            project.turn_policy = policy
            project.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            await _publish_turn_policy_changed(project_id, policy, str(user.id))

        return project.turn_policy, project.updated_at

    async def acknowledge_tour(
        self, project_id: UUID, user: User
    ) -> dict[str, str]:
        """Phase 30 (spec/22 §2.1)：紀錄 ``user`` 完成了 0.1 DEMO 導覽。

        idempotent：重複呼叫不報錯，只更新時戳。回傳目前該專案完整 ack map。
        """
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        # JSONB column: mutate dict + reassign so SQLAlchemy detects change
        ack_map = dict(project.tour_acknowledged_by or {})
        ack_map[str(user.id)] = now_iso
        project.tour_acknowledged_by = ack_map
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return ack_map

    async def get_seats(
        self, project_id: UUID, user: User
    ) -> list[SeatResponse]:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        assert_project_access(project, user, level=LEVEL_VIEWER)
        seats = await self.repo.get_seats(project_id)
        return [self._seat_to_response(s) for s in seats]

    async def join_project(
        self, project_id: UUID, request: JoinRequest, user: User
    ) -> JoinResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Supervisor 為 AI 專屬、鎖死。
        if request.seat_role == SEAT_ROLE_SUPERVISOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Supervisor seat is AI-only and cannot be occupied by humans",
            )
        # crew_* 為常駐 AI，永不可被真人頂替；唯一可入座的是真人專屬席。
        if request.seat_role != SEAT_ROLE_HUMAN_CREATOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Crew seats are AI-only; only the dedicated human seat can be occupied",
            )
        # 真人專屬席綁定 creator：只有專案建立者能入座（老師只能旁觀、不可入座）。
        if user.id != project.creator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the project creator may occupy the human seat",
            )

        all_seats = await self.repo.get_seats(project_id)
        seat = next(
            (s for s in all_seats if s.seat_role == SEAT_ROLE_HUMAN_CREATOR),
            None,
        )
        if not seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This project has no human seat",
            )
        # 已被佔（user_id 非空）→ 409。空席以 user_id IS NULL 表示。
        if seat.user_id is not None:
            detail = (
                "You already occupy the human seat in this project"
                if seat.user_id == user.id
                else "The human seat is already occupied"
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

        # Delegate to SeatManager: updates DB/Redis, broadcasts event
        await seat_manager.assign_human(
            project_id=project_id,
            seat_role=request.seat_role,
            user_id=user.id,
            user_name=user.display_name,
            session=self.session,
        )
        await self.session.flush()

        # creator 入座 → 啟動所有 dormant AI（supervisor 立即、crew 錯開）。
        # idempotent：重新入座時若 AI 已在跑，activate_dormant_seats 找不到 dormant 即 no-op。
        # 傳 self.session 讓 supervisor 同步激活與本次 request 同交易（測試 fixture 不 commit 也可見）。
        await seat_manager.activate_dormant_seats(project_id, session=self.session)

        # Re-read seat from DB for the response
        await self.session.refresh(seat)

        return JoinResponse(
            seat=self._seat_to_response(seat),
            workspace_url=f"/projects/{project_id}/workspace",
        )

    async def leave_project(self, project_id: UUID, user: User) -> dict:
        seats = await self.repo.get_seats(project_id)
        user_seat = next(
            (s for s in seats if s.user_id == user.id),
            None,
        )
        if not user_seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not in any seat",
            )

        # Delegate to SeatManager: updates DB/Redis, starts AI agent, sends greeting
        await seat_manager.release_human(
            project_id=project_id,
            seat_role=user_seat.seat_role,
            session=self.session,
        )
        await self.session.flush()

        return {"message": "Left successfully"}

    async def delete_project(self, project_id: UUID, user: User) -> None:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        if project.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator may delete this project",
            )
        # Stop running agents before deleting
        try:
            await seat_manager.stop_all(project_id)
        except Exception as exc:
            logger.warning("Failed to stop agents for project %s: %s", project_id, exc)
        await self.repo.delete(project)

    async def get_canvas_state(
        self, project_id: UUID, user: User
    ) -> CanvasStateResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        assert_project_access(project, user, level=LEVEL_VIEWER)
        from app.bridge.canvas_ops import canvas_ops

        raw = await canvas_ops.get_canvas_state(project_id)
        return CanvasStateResponse(
            total_notes=raw.get("total_notes", 0),
            groups=[
                {"name": g.get("name", ""), "notes": g.get("notes", [])}
                for g in raw.get("groups", [])
            ],
            ungrouped=raw.get("ungrouped", []),
            notes=[
                CanvasNoteResponse(
                    id=n.get("id", ""),
                    content=n.get("content", ""),
                    color=n.get("color", "yellow"),
                    author=n.get("author", ""),
                    group_name=n.get("group_name"),
                    # Spec 27 (Phase 36) 便條欄位
                    kind=n.get("kind", "content"),
                    group_id=n.get("group_id"),
                    # Phase 42 C0 (spec 06 v4.25)
                    cites=n.get("cites") or [],
                    time_box_forced=bool(n.get("time_box_forced", False)),
                )
                for n in raw.get("notes", [])
            ],
        )

    async def generate_summary(
        self, project_id: UUID, *, user: User
    ) -> ProjectSummaryResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        assert_project_access(project, user, level=LEVEL_VIEWER)
        owning_user_id = user.id

        from app.agents.prompts.summary import LOBBY_SUMMARY_PROMPT
        from app.bridge.canvas_ops import canvas_ops
        from app.chat.repository import MessageRepository
        from app.chinese.converter import chinese_converter
        from app.llm.factory import LLMProviderFactory

        # Gather context
        msg_repo = MessageRepository(self.session)
        messages = await msg_repo.get_messages(project_id, limit=30)
        canvas_state = await canvas_ops.get_canvas_state(project_id)

        # Cap each chat line at 200 chars so a runaway long message can't blow up the prompt
        chat_text = "\n".join(
            f"[{m.sender_type}] {m.sender_name}: {m.content[:200]}"
            for m in messages
        ) or "（尚無對話）"

        # vLLM context limit is 32K tokens. A long-running project can accumulate
        # thousands of notes; dumping them all overflows the prompt. Cap to the
        # most recent 60 notes (max ~120 chars each ≈ 8K tokens worst-case).
        _NOTE_TEXT_CAP = 120
        _NOTE_COUNT_CAP = 60
        all_notes = canvas_state.get("notes", [])
        recent_notes = all_notes[-_NOTE_COUNT_CAP:] if len(all_notes) > _NOTE_COUNT_CAP else all_notes
        notes_text_body = "\n".join(
            f"- {n.get('content', '')[:_NOTE_TEXT_CAP]}" for n in recent_notes
        ) or "（尚無便條紙）"
        if len(all_notes) > _NOTE_COUNT_CAP:
            notes_text = (
                f"（共 {len(all_notes)} 張便條紙，僅顯示最新 {_NOTE_COUNT_CAP} 張）\n"
                f"{notes_text_body}"
            )
        else:
            notes_text = notes_text_body

        user_content = (
            f"目前階段：{project.current_stage}\n\n"
            f"=== 對話紀錄 ===\n{chat_text}\n\n"
            f"=== 白板便條紙 ===\n{notes_text}"
        )

        llm = LLMProviderFactory.get_service()
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": LOBBY_SUMMARY_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=512,
            caller="project_summary",
            owning_user_id=owning_user_id,
            triggered_by_user_id=owning_user_id,
            project_id=project_id,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            data = {
                "summary": response.content,
                "topics": [],
                "current_focus": "",
                "blind_spots": [],
            }

        return ProjectSummaryResponse(
            summary=chinese_converter.convert(data.get("summary", "")),
            topics=[chinese_converter.convert(t) for t in data.get("topics", [])],
            current_focus=chinese_converter.convert(data.get("current_focus", "")),
            blind_spots=[
                chinese_converter.convert(b) for b in data.get("blind_spots", [])
            ],
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _seat_to_response(seat: Seat) -> SeatResponse:
        from app.agents.personas.display import resolve_display_name

        persona_payload = getattr(seat, "persona", None)
        is_dormant = seat.state == SEAT_STATE_DORMANT
        # 空置的真人專屬席（occupant_type="human" 但無 user_id）視同未啟用，
        # 前端據此畫成「待入座」空椅而非「在場真人」。
        is_vacant_human = seat.occupant_type == "human" and seat.user_id is None
        display_name: str | None = None
        # Phase 21：dormant AI 不對外揭露 persona 姓名（前端顯示「待加入」）。
        if seat.occupant_type == "ai" and not is_dormant:
            display_name = resolve_display_name(seat.seat_role, persona_payload)
        return SeatResponse(
            seat_role=seat.seat_role,
            occupant_type=seat.occupant_type,
            user_id=seat.user_id,
            agent_id=seat.agent_id,
            display_name=display_name,
            # 仍把 persona 帶出，讓教師 / 建立者預覽 — 真正切換到 UI 上的「代理中」需要 is_active=True
            persona=persona_payload,
            is_active=not (is_dormant or is_vacant_human),
            sticky_color=getattr(seat, "sticky_color", None),
        )
