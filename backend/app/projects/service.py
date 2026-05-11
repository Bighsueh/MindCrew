from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.user import User
from app.projects.repository import ProjectRepository
from app.projects.schemas import (
    CanvasNoteResponse,
    CanvasStateResponse,
    JoinRequest,
    JoinResponse,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
    SeatResponse,
)
from app.seats.manager import seat_manager

logger = logging.getLogger(__name__)

SEAT_ROLES = ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]


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

        project = Project(
            name=request.name,
            description=request.description,
            creator_id=user.id,
            ai_contribution=request.ai_contribution,
        )
        project = await self.repo.create(project)

        seats = []
        for role in SEAT_ROLES:
            seat = Seat(
                project_id=project.id,
                seat_role=role,
                occupant_type="ai",
                agent_id=f"agent_{role}",
                state="ai_running",
            )
            self.session.add(seat)
            seats.append(seat)
        await self.session.flush()

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
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
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
        )

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
        if request.ai_contribution is not None:
            project.ai_contribution = request.ai_contribution
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        seats = await self.repo.get_seats(project_id)
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
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

        seat = await self.repo.get_seat(project_id, request.seat_role)
        if not seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid seat role"
            )
        if request.seat_role == "supervisor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Supervisor seat is AI-only and cannot be occupied by humans",
            )
        if seat.occupant_type == "human":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seat is already occupied by a human",
            )

        # Delegate to SeatManager: stops AI agent, updates DB/Redis, broadcasts event
        # Pass our session so the DB update stays within this transaction
        await seat_manager.assign_human(
            project_id=project_id,
            seat_role=request.seat_role,
            user_id=user.id,
            user_name=user.display_name,
            session=self.session,
        )
        await self.session.flush()

        # Ensure all other AI seats have running agents
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

    async def generate_summary(self, project_id: UUID) -> ProjectSummaryResponse:
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

    _AI_DISPLAY_NAMES: dict[str, str] = {
        "supervisor": "AI 引導者",
        "crew_1": "AI 同理心專家",
        "crew_2": "AI 結構化專家",
        "crew_3": "AI 創意專家",
        "crew_4": "AI 可行性專家",
    }

    @staticmethod
    def _seat_to_response(seat: Seat) -> SeatResponse:
        display_name = None
        if seat.occupant_type == "ai":
            display_name = ProjectService._AI_DISPLAY_NAMES.get(
                seat.seat_role, f"AI {seat.seat_role}"
            )
        return SeatResponse(
            seat_role=seat.seat_role,
            occupant_type=seat.occupant_type,
            user_id=seat.user_id,
            agent_id=seat.agent_id,
            display_name=display_name,
        )
