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
from app.db.models.seat import Seat
from app.db.models.user import User
from app.projects.repository import ProjectRepository
from app.projects.schemas import (
    CanvasNoteResponse,
    CanvasStateResponse,
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

logger = logging.getLogger(__name__)

def _seat_roles_for(ai_crew_count: int) -> list[str]:
    """Phase 21：依教師選的人數動態產生席位清單。Supervisor 固定一位，crew 從 crew_1 開始連續。"""
    return ["supervisor"] + [f"crew_{i}" for i in range(1, ai_crew_count + 1)]


# Phase 21: 在第一位真人入座前，AI 座位以此狀態存放（不啟動 agent、前端顯示「待加入」）。
SEAT_STATE_DORMANT = "dormant"
SEAT_STATE_AI_RUNNING = "ai_running"


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

        project = Project(
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

        # Phase 22：seed 每個席位的 sticky_color（shuffle 8 色）
        seed_seat_colors(seats)
        await self.session.flush()

        # specs/16-timer-system.md：建立專案時同步初始化 timer。
        # timer_config 為必填欄位（schemas.py），由建立者明確選擇。
        # 失敗不再 swallow——沒 timer 的 project 不該存在。
        from app.timer.service import TimerService
        await TimerService.initialize_project(
            project.id, config=request.timer_config
        )
        await TimerService.start_phase(project.id, "1.1a")

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
        )

    async def list_projects(self, user: User) -> list[ProjectListItem]:
        projects = await self.repo.list_user_projects(user.id)
        result = []
        for p in projects:
            seats = await self.repo.get_seats(p.id)
            human_count = sum(1 for s in seats if s.occupant_type == "human")
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
                )
            )
        return result

    async def get_project(self, project_id: UUID) -> ProjectResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
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
        return await self.get_project(project_id)

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
            return await self.get_project(project_id)
        if user.id not in (project.creator_id, project.linked_teacher_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only creator or linked teacher may unlink",
            )
        project.linked_teacher_id = None
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return await self.get_project(project_id)

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
        return await self.get_project(project.id)

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
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

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
        )

    async def get_seats(self, project_id: UUID) -> list[SeatResponse]:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
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

        # Supervisor lock 最高優先（Phase 18 規則）。
        if request.seat_role == "supervisor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Supervisor seat is AI-only and cannot be occupied by humans",
            )

        all_seats = await self.repo.get_seats(project_id)
        seat = next(
            (s for s in all_seats if s.seat_role == request.seat_role),
            None,
        )
        if not seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid seat role"
            )
        # Phase 21: 一個人類在同一專案僅能佔一個席位。
        if any(s.user_id == user.id for s in all_seats):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already occupy a seat in this project",
            )
        # Phase 22: 每個專案最多只能有一個人類參與者。
        if any(s.occupant_type == "human" for s in all_seats):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This project already has a human participant",
            )
        if seat.occupant_type == "human":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seat is already occupied by a human",
            )

        # Phase 21：偵測「第一位真人入座」事件，
        # 若是，則由 seat_manager 把 dormant AI 席位陸續激活（supervisor 立即、crew 錯開）。
        is_first_human = not any(s.occupant_type == "human" for s in all_seats)

        # Delegate to SeatManager: stops AI agent (if any), updates DB/Redis, broadcasts event
        await seat_manager.assign_human(
            project_id=project_id,
            seat_role=request.seat_role,
            user_id=user.id,
            user_name=user.display_name,
            session=self.session,
        )
        await self.session.flush()

        if is_first_human:
            # 第一位真人 → 把所有 dormant AI 座位激活（含 supervisor + 其他 crew）。
            # 傳 self.session 進去，讓 supervisor 的同步激活與本次 request 同交易，
            # 確保測試 fixture（不 commit）也能看到狀態。
            await seat_manager.activate_dormant_seats(
                project_id, session=self.session
            )
        else:
            # 其他真人 → 只確認既有 AI agents 在跑（idempotent）。
            await seat_manager.start_all_agents(project_id)

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

    async def get_canvas_state(self, project_id: UUID) -> CanvasStateResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
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
                )
                for n in raw.get("notes", [])
            ],
        )

    async def generate_summary(
        self, project_id: UUID, *, owning_user_id: UUID
    ) -> ProjectSummaryResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

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
            is_active=not is_dormant,
            sticky_color=getattr(seat, "sticky_color", None),
        )
