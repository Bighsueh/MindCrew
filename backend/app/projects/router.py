import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.constraints import (
    ConstraintSuggester,
    ConstraintSuggestionError,
)
from app.agents.personas.generator import (
    PersonaGenerationError,
    PersonaGenerator,
)
# template_suggest import 已移除（Phase 42 補正 R3／P1-6 ARCHIVE，見下方端點原址註記）。
from app.auth.jwt import get_current_user
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import get_db_session
from app.projects.deps import require_project_viewer
from app.projects.schemas import (
    CanvasStateResponse,
    JoinRequest,
    JoinResponse,
    LinkTeacherRequest,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectTimerInitRequest,
    ProjectUpdateRequest,
    SeatResponse,
    StakeholderSuggestionPayload,
    SuggestConstraintsRequest,
    SuggestConstraintsResponse,
    SuggestStakeholdersRequest,
    SuggestStakeholdersResponse,
    TourAcknowledgeResponse,
    TurnPolicyResponse,
    TurnPolicyUpdateRequest,
)
from app.projects.service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Phase 27: Open Brief 三步驟 wizard draft endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/draft/suggest-constraints",
    response_model=SuggestConstraintsResponse,
)
async def suggest_constraints(
    request: SuggestConstraintsRequest,
    current_user: User = Depends(get_current_user),
) -> SuggestConstraintsResponse:
    """Phase 27 Step 1：根據 title+description 列建議的限制條件（chip 形式）。

     與  Open Brief 原則。
    """
    suggester = ConstraintSuggester()
    try:
        suggestions = await suggester.suggest(
            title=request.title,
            description=request.description,
            owning_user_id=current_user.id,
        )
    except ConstraintSuggestionError as exc:
        logger.warning("Constraint suggestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 限制條件建議失敗，請稍後再試或自行填寫。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SuggestConstraintsResponse(**suggestions.as_dict())


@router.post(
    "/draft/suggest-stakeholders",
    response_model=SuggestStakeholdersResponse,
)
async def suggest_stakeholders(
    request: SuggestStakeholdersRequest,
    current_user: User = Depends(get_current_user),
) -> SuggestStakeholdersResponse:
    """Phase 27 Step 2：根據 title+description+constraints 列 6–10 位具體利害關係人。

    。
    """
    generator = PersonaGenerator()
    try:
        suggestions = await generator.suggest_stakeholders(
            title=request.title,
            description=request.description,
            constraints=request.constraints,
            owning_user_id=current_user.id,
            existing_names=request.existing_names,
        )
    except PersonaGenerationError as exc:
        logger.warning("Stakeholder suggestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 利害關係人建議失敗，請稍後再試。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    payloads = [
        StakeholderSuggestionPayload(
            id=s.id,
            name=s.name,
            role=s.role,
            relevance=s.relevance,
        )
        for s in suggestions
    ]
    return SuggestStakeholdersResponse(suggestions=payloads)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.create_project(request, current_user)
    # Commit happens via get_db_session dependency; flush already ran.
    # 不在建立流程啟動 AI：所有席位建立時皆為 DORMANT，AI 於真人入座
    # （join_project → activate_dormant_seats）時才啟動。過去這裡 await
    # start_all_agents 對全 dormant 席位等於空轉，卻多開一條 DB 連線並阻塞
    # HTTP 回應；併發建立時拖過 nginx proxy_read_timeout(60s) → 前端 Network Error。
    await session.commit()
    return result


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectListItem]:
    service = ProjectService(session)
    return await service.list_projects(current_user)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    return await service.get_project(project_id, current_user)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    request: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    return await service.update_project(project_id, request, current_user)


@router.patch(
    "/{project_id}/turn-policy",
    response_model=TurnPolicyResponse,
)
async def update_turn_policy(
    project_id: UUID,
    request: TurnPolicyUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TurnPolicyResponse:
    """Phase 28。

    教師（必須是該專案 linked_teacher）或 admin 切換輪流規則。下一個 ASSESS tick
    （≤ 1 秒）即生效；前端透過 WS ``turn_policy_changed`` event 即時同步。
    """
    service = ProjectService(session)
    policy, applied_at = await service.update_turn_policy(
        project_id, request.policy, current_user
    )
    return TurnPolicyResponse(policy=policy, applied_at=applied_at)


# ARCHIVE（Phase 42 補正 R3／P1-6，user 裁定 2026-07-07）：
# 「AI 起稿」endpoint `POST /{project_id}/templates/{template_id}/suggest` 下架。
# 理由：前端零 caller；5 個 prompt builder 有 3 個教現行模板的禁字/錯句型
# （`from:`、「我們如何」、「｜佐證」、訪談筆記）＋殘留 persona 參數——
# 「打了必 502 或教錯示範」的中間態不留。復活條件＝依 spec 23 v2.0 模板
# 重寫全部 builder（spec 23 v2.2 註記）。模組留 app/agents/template_suggest/
# 標 ARCHIVE 供參考，不再有進入點。


@router.post(
    "/{project_id}/acknowledge-tour",
    response_model=TourAcknowledgeResponse,
)
async def acknowledge_tour(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TourAcknowledgeResponse:
    """Phase 30 (spec/22 §2.1)：紀錄當前 user 完成 0.1 DEMO 導覽。

    前端進入 workspace 時若 current_user.id 不在 project.tour_acknowledged_by，
    渲染 0.1 sub_phase 的 DEMO tour；user 按「完成」後呼叫此端點寫入。
    """
    service = ProjectService(session)
    ack_map = await service.acknowledge_tour(project_id, current_user)
    await session.commit()
    return TourAcknowledgeResponse(tour_acknowledged_by=ack_map)


@router.get("/{project_id}/seats", response_model=list[SeatResponse])
async def get_seats(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[SeatResponse]:
    service = ProjectService(session)
    return await service.get_seats(project_id, current_user)


@router.post("/{project_id}/join", response_model=JoinResponse)
async def join_project(
    project_id: UUID,
    request: JoinRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JoinResponse:
    service = ProjectService(session)
    return await service.join_project(project_id, request, current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = ProjectService(session)
    await service.delete_project(project_id, current_user)
    await session.commit()


# Phase 22: 學生 creator 將活動列管於某老師
@router.post("/{project_id}/link-teacher", response_model=ProjectResponse)
async def link_teacher(
    project_id: UUID,
    payload: LinkTeacherRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.link_teacher(project_id, payload.signature_code, current_user)
    await session.commit()
    return result


@router.delete("/{project_id}/link-teacher", response_model=ProjectResponse)
async def unlink_teacher(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.unlink_teacher(project_id, current_user)
    await session.commit()
    return result


@router.get("/{project_id}/canvas-state", response_model=CanvasStateResponse)
async def get_canvas_state(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CanvasStateResponse:
    service = ProjectService(session)
    return await service.get_canvas_state(project_id, current_user)


@router.post("/{project_id}/summary", response_model=ProjectSummaryResponse)
async def generate_summary(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectSummaryResponse:
    service = ProjectService(session)
    return await service.generate_summary(project_id, user=current_user)


@router.post("/{project_id}/leave")
async def leave_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = ProjectService(session)
    return await service.leave_project(project_id, current_user)


# ---------------------------------------------------------------------------
# Spec 13 — 人類強制送出便條（force_publish）
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class HumanNoteRequest(BaseModel):
    text: str = Field(..., min_length=1)
    color: str = Field("yellow", pattern="^(yellow|pink|blue|green)$")
    x: float
    y: float
    sub_phase_id: str = Field(..., max_length=8)
    force_publish: bool = False
    # Spec 27 (Phase 36)：人類也可寫分類標籤便條 / 帶主題群（§6 / §4）。
    kind: str = Field("content", pattern="^(content|label)$")
    group_id: str | None = None
    # Phase 42 C0 (spec 06 v4.25)：引用鏈。本模型**刻意不收 time_box_forced**——
    # 該欄位只有 C2 的 time-box 強推路徑可寫，人類與 crew 均不可（spec 06 v4.25）。
    cites: list[str] | None = Field(default=None, max_length=20)


async def _resolve_project_sub_phase(project_id: UUID) -> str:
    """讀 project 權威 current_sub_phase（fallback current_stage）。

    timer 未啟用時前端 timer 快照的 current_sub_phase 為 null，便條會送空 sub_phase；
    以 project 權威值補上（與 round_lock `process_group_input` 同源、不信前端 timer 快照），
    否則便條被擋在本地永不送出 → agent 永遠看不到真人貼的便條（組長一直問「貼了嗎？」）。
    """
    from sqlalchemy import select

    from app.db.models.project import Project
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Project.current_sub_phase, Project.current_stage).where(
                    Project.id == project_id
                )
            )
        ).first()
    if row is None:
        return ""
    return (row[0] or row[1] or "").strip()


@router.post("/{project_id}/canvas/notes")
async def human_create_note(
    project_id: UUID,
    payload: HumanNoteRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Human-facing create_note endpoint with Spec 13 gates + force_publish support."""
    from app.canvas.tools_manipulation import tool_create_note

    # timer 未啟用時前端拿不到 sub_phase（送空字串）；用 project 權威值補上，否則便條
    # 進不了 agent 視野（gate 仍以正確 sub_phase 評估，無「誤送 gate」風險）。
    sub_phase_id = payload.sub_phase_id or await _resolve_project_sub_phase(project_id)

    result = await tool_create_note(
        project_id=project_id,
        text=payload.text,
        color=payload.color,
        position=f"absolute:{payload.x},{payload.y}",
        author_id=str(current_user.id),
        author_name=current_user.display_name,
        author_type="human",
        sub_phase_id=sub_phase_id,
        force_publish=payload.force_publish,
        kind=payload.kind,
        group_id=payload.group_id,
        cites=payload.cites,
    )
    # Phase 42 A2 補強：便條成功落地 → 實質檢核 → note 型回合鎖解鎖（spec 20
    # §11.4/§12；#23「human create_note endpoint」即本端點）。背景任務、不影響
    # 回應；sub_phase 由 process_group_input 讀 DB 鮮值（不信前端 payload）。
    if result.get("success"):
        import asyncio

        from app.agents.human_input_check import process_group_input

        asyncio.create_task(
            process_group_input(project_id, current_user.id, payload.text, "note")
        )
    return result


class NoteCitesRequest(BaseModel):
    """Phase 42 C0 (spec 06 v4.25)：人類點選引用 UI 的全量覆蓋請求。"""

    cites: list[str] = Field(..., max_length=20)


@router.patch("/{project_id}/canvas/notes/{note_id}")
async def update_human_note_cites(
    project_id: UUID,
    note_id: str,
    payload: NoteCitesRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """人類為**自己的**便條覆蓋引用鏈（cites only；403=非作者，404=便條不存在）。

    作者驗證（C0 裁定 3，單真人席前提）：note.author 後綴 "(human)" ＋ current_user
    佔本專案真人席。NoteShape 無 author_id 欄位；未來開放多真人席要改驗真正 author_id。
    """
    from app.bridge.canvas_ops import canvas_ops
    from app.db.models.seat import Seat
    from sqlalchemy import select

    shapes = await canvas_ops.get_canvas_state_full(project_id)
    note = next((s for s in shapes if s.get("id") == note_id), None)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="便條不存在")

    author = str(note.get("author") or "")
    occupies_human_seat = (
        await session.execute(
            select(Seat.id).where(
                Seat.project_id == project_id,
                Seat.occupant_type == "human",
                Seat.user_id == current_user.id,
            )
        )
    ).first() is not None
    if not author.endswith("(human)") or not occupies_human_seat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能編輯自己便條的引用",
        )

    ok = await canvas_ops.update_note_cites(project_id, note_id, payload.cites)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="便條不存在")
    return {"success": True, "note_id": note_id, "cites": payload.cites}


# ---------------------------------------------------------------------------
# Spec 14 N2: Crew Advance Vote endpoints
# ---------------------------------------------------------------------------


# Crew advance-vote 端點（GET/POST/POST /advance-vote{,/cast,/cancel}）已於 v4.15
# 移除：單鑽石改用「引導者節奏推進」（progression_watcher，無 REST 端點）。
# 推進邏輯見 specs/04-06 §5.8；macro 推進已改組長宣布（spec 04-06 §5.8 v4.25）。


# ---------------------------------------------------------------------------
# Spec 15: Timer control endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 35 (spec/16 §3.1)：Timer 控制端點 RBAC dependency
# pause / resume / extend 限教師或專案建立者；對齊 spec [Teacher Only] 設計
# ---------------------------------------------------------------------------


async def require_teacher_or_creator(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Spec/16 §3.1：限教師（role == 'teacher'）或專案建立者操作 Timer 控制。

    與 `admin/dependencies.py:require_admin` 對齊；與 `service.py:320`
    既有「creator or linked_teacher」邏輯精神一致。
    """
    from sqlalchemy import select
    from app.db.models.project import Project

    project = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="專案不存在")
    if current_user.role == "teacher" or current_user.id == project.creator_id:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="只有教師或專案建立者可控制計時器",
    )


@router.get("/{project_id}/human-gate")
async def get_human_gate_state(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    _project: Project = Depends(require_project_viewer),
) -> dict:
    """Phase 42 補正 R4（A-P1，spec 05 Flow 12）：user_task／回合鎖等待的水合快照。

    TaskBanner／WaitingIndicator 原本只靠 live WS 事件存在——刷新、斷線重連、
    休眠喚醒（room_resumed 不重發）後全部消失，且 waiting_for_human 有同回合
    NX 去重永不重發。前端於掛載與每次 WS (re)connect 呼叫本端點對齊 server truth。
    """
    from app.agents import round_lock, user_task_state

    task = await user_task_state.get_current(project_id)
    waiting: dict | None = None
    sub_phase = _project.current_sub_phase
    if sub_phase:
        state = await round_lock.get_state(project_id, sub_phase)
        if state.get("waiting") and state.get("has_human"):
            waiting = {
                "sub_phase": sub_phase,
                "round": state.get("round", 1),
                "required": state.get("required", {}),
            }
    return {"user_task": task, "waiting": waiting, "sub_phase": sub_phase}


@router.get("/{project_id}/timer")
async def get_timer_state(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    _project: Project = Depends(require_project_viewer),
) -> dict:
    from app.timer.service import TimerService
    from app.timer.calculator import get_phase_budget_seconds

    state = await TimerService.get_state(project_id)
    config = await TimerService.get_config(project_id)
    if state is None or config is None:
        return {"available": False}

    budget = 0
    used_pct = 0.0
    used_seconds = 0
    if state.current_sub_phase:
        budget = get_phase_budget_seconds(config, state.current_sub_phase)
        used_seconds = TimerService._compute_used_seconds(state)
        if budget > 0:
            used_pct = used_seconds / budget * 100

    # current_sub_phase_label：友善階段名（與 WS timer_state 事件同源），讓 5s REST poll 與
    # 初始載入也帶 label，避免 TimerBadge 退回顯示 raw 代號「剩餘·1.1a」（盲測 2026-06-09）。
    from app.timer.events import _sub_phase_label

    # Spec 16 v2.0 §4.5（Phase 42 WP1）：暖場團隊目標——與 WS timer_state 同一計算來源。
    # Spec 28 §3.1：暖場軟目標秒數（固定 180）——同源計算，前端標示 3 分軟目標。
    from app.timer.scaling import warmup_goal_for, warmup_soft_seconds_for

    return {
        "available": True,
        "current_sub_phase": state.current_sub_phase,
        "current_sub_phase_label": _sub_phase_label(state.current_sub_phase),
        "budget_seconds": budget,
        "used_seconds": used_seconds,
        "used_pct": used_pct,
        "paused": state.is_paused(),
        # Spec 16 v2.0 §4.5：本關上限/已用的明確化別名（與 budget/used 同值）＋暖場目標。
        "sub_phase_budget_seconds": budget,
        "sub_phase_used_seconds": used_seconds,
        "warmup_goal": warmup_goal_for(state.current_sub_phase, config),
        "warmup_soft_seconds": warmup_soft_seconds_for(state.current_sub_phase, config),
        "config": config.model_dump(),
        "state": state.model_dump(),
    }


@router.post("/{project_id}/timer/pause")
async def timer_pause(
    project_id: UUID,
    current_user: User = Depends(require_teacher_or_creator),
) -> dict:
    from app.timer.service import TimerService
    new_state = await TimerService.pause(project_id)
    return {"success": new_state is not None, "state": new_state.model_dump() if new_state else None}


@router.post("/{project_id}/timer/resume")
async def timer_resume(
    project_id: UUID,
    current_user: User = Depends(require_teacher_or_creator),
) -> dict:
    from app.timer.service import TimerService
    new_state = await TimerService.resume(project_id)
    return {"success": new_state is not None, "state": new_state.model_dump() if new_state else None}


class TimerExtendRequest(BaseModel):
    # spec/16 §3.1: additional_minutes (1..30)
    additional_minutes: int = Field(..., ge=1, le=30)


@router.post("/{project_id}/timer/extend")
async def timer_extend(
    project_id: UUID,
    payload: TimerExtendRequest,
    current_user: User = Depends(require_teacher_or_creator),
) -> dict:
    from app.timer.service import TimerService
    new_config = await TimerService.extend(project_id, payload.additional_minutes)
    return {"success": new_config is not None}


@router.post("/{project_id}/timer/init")
async def timer_init(
    project_id: UUID,
    payload: ProjectTimerInitRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """為尚未啟用 timer 的專案補上 timer_config + 啟動目前 sub_phase。

    僅限 project creator；timer 已啟用回 409。config=None 走 DEFAULT_PRESET（90 分）。

    Phase 38 (spec/28 §2.2)：專案建立即進暖場 macro stage（current_sub_phase=0.0a）。
    本端點過去寫死 start_phase("1.1a")——那是 Phase 38 前「discover 第一格＝入口」的假設，
    會在 timer 初始化時把 sub_phase 從 0.0a 直接跳到 1.1a、**整段跳過暖場**（且造成
    current_stage=warmup 與 current_sub_phase=1.1a 的 desync）。改為啟動專案**目前**的
    sub_phase（新專案＝暖場 0.0a；舊專案＝其既有格），暖場才不會被 timer 初始化吃掉。
    """
    from fastapi import HTTPException
    from app.timer.service import TimerService

    project = await ProjectService(session).repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    if project.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有建立者可啟用計時器")
    if project.timer_config is not None:
        raise HTTPException(status_code=409, detail="計時器已啟用")

    await TimerService.initialize_project(project_id, config=payload.config)
    # 啟動專案目前的 sub_phase（暖場新專案＝0.0a），不再寫死 1.1a 跳過暖場。
    start_sub = project.current_sub_phase or "0.0a"
    await TimerService.start_phase(project_id, start_sub)

    # Phase 42 補正 R4（D5 縫 a）：LLM 判定 down 期間新建/啟用的房——立即以
    # llm_down 暫停＋banner，與 fail-stop 全房狀態一致（否則 outage 中新房照跑、
    # agent 全靜默、無異常說明）。
    try:
        from app.llm.health_monitor import health_monitor

        if health_monitor.is_down():
            from app.events.bus import event_bus
            from app.events.types import RoomPausedEvent

            await TimerService.pause(project_id, reason="llm_down")
            await event_bus.publish(
                RoomPausedEvent(project_id=project_id, reason="llm_down")
            )
    except Exception:
        logger.exception("timer_init llm_down pause failed project=%s", project_id)
    return {"ok": True}
