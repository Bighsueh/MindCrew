from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.config import settings
from app.db.models.interview import InterviewExchange, InterviewSession
from app.db.models.user import User
from app.db.session import get_db_session
from app.interview.personas import persona_router
from app.interview.profiles import PRESET_ID, SCENARIO, SCENARIO_TITLE, STAKEHOLDERS, saved_scenario_snapshot, scenario_snapshot
from app.interview.scenarios import PRESET_SCENARIO_ID, get_scenario, router as scenario_router
from app.interview.provider import InterviewProvider, get_interview_provider
from app.interview.service import (
    ERROR_MESSAGES, can_retry, ensure_open, exchange_status, generate_answer,
    get_exchanges, get_session, retry_wait, skip, utcnow,
)

router = APIRouter(prefix="/api/interview", tags=["interview"])
router.include_router(persona_router)
router.include_router(scenario_router)
UserDep = Annotated[User, Depends(get_current_user)]
DBDep = Annotated[AsyncSession, Depends(get_db_session)]
ProviderDep = Annotated[InterviewProvider, Depends(get_interview_provider)]


class CustomScenario(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=2400)
    relationship: str = Field(default="", max_length=800)
    experience: str = Field(default="", max_length=1600)

    @field_validator("title", "description", "relationship", "experience")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("情境不能包含空字元。")
        return value.strip()

    @model_validator(mode="after")
    def require_background(self):
        if not self.title or not self.description:
            raise ValueError("請填寫題目名稱與情境描述。")
        return self


class StartInterview(BaseModel):
    stakeholder_id: str = Field(max_length=40)
    preset_id: Literal["campus-learning-space"] = PRESET_ID
    custom: CustomScenario | None = None
    scenario_id: UUID | None = None


class NoteBody(BaseModel):
    body: str = Field(max_length=30000)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("筆記不能包含空字元。")
        return value


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    request_id: UUID

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("請輸入有效的問題文字。")
        return value


class ResolveQuestion(BaseModel):
    action: Literal["retry", "skip"]


def session_summary(session: InterviewSession) -> dict:
    snapshot = session.scenario_snapshot or scenario_snapshot(session.stakeholder_id)
    scenario = snapshot["scenario"]
    return {
        "id": session.id, "stakeholder_id": session.stakeholder_id,
        "scenario_id": session.scenario_id or (PRESET_SCENARIO_ID if scenario["kind"] == "preset" else None),
        "scenario": {key: scenario[key] for key in ("kind", "title", "description")},
        "stakeholder": snapshot["stakeholder"],
        "started_at": session.started_at, "ended_at": session.ended_at,
    }


def exchange_data(exchange: InterviewExchange) -> dict:
    status, error = exchange_status(exchange)
    return {
        "id": exchange.id, "request_id": exchange.request_id, "sequence": exchange.sequence,
        "question": exchange.question, "asked_at": exchange.asked_at,
        "answer": exchange.answer, "answered_at": exchange.answered_at, "status": status,
        "provider": exchange.provider, "model": exchange.model, "retryable": can_retry(exchange),
        "retry_after_seconds": retry_wait(exchange),
        "error": ERROR_MESSAGES.get(error),
    }


def session_data(session: InterviewSession, exchanges: list[InterviewExchange]) -> dict:
    return {
        **session_summary(session), "exchanges": [exchange_data(exchange) for exchange in exchanges],
        "remaining_questions": max(0, settings.INTERVIEW_MAX_QUESTIONS - len(exchanges)),
    }


@router.get("/stakeholders")
async def stakeholders(user: UserDep):
    return {
        "scenario": SCENARIO, "synthetic": True, "max_question_chars": 600,
        "presets": [{"id": PRESET_ID, "title": SCENARIO_TITLE, "description": SCENARIO,
                     "stakeholder_ids": list(STAKEHOLDERS)}],
        "stakeholders": [
            {"id": key, "name": item.name, "description": item.description}
            for key, item in STAKEHOLDERS.items()
        ],
    }


@router.get("/sessions")
async def list_sessions(user: UserDep, db: DBDep, stakeholder_id: str | None = None):
    query = select(InterviewSession).where(InterviewSession.owner_id == user.id)
    if stakeholder_id:
        query = query.where(InterviewSession.stakeholder_id == stakeholder_id)
    sessions = await db.scalars(query.order_by(InterviewSession.started_at.desc(), InterviewSession.id))
    return [session_summary(session) for session in sessions]


@router.post("/sessions", status_code=201)
async def start_interview(body: StartInterview, user: UserDep, db: DBDep):
    if body.scenario_id:
        scenario = await get_scenario(db, user, body.scenario_id)
        snapshot = saved_scenario_snapshot(scenario, body.stakeholder_id)
        if snapshot is None:
            raise HTTPException(404, "找不到該情境的受訪者。")
    else:
        if body.stakeholder_id not in STAKEHOLDERS:
            raise HTTPException(404, "找不到此受訪者。")
        snapshot = scenario_snapshot(body.stakeholder_id, body.custom.model_dump() if body.custom else None)
    session = InterviewSession(
        owner_id=user.id, stakeholder_id=body.stakeholder_id, started_at=utcnow(), scenario_snapshot=snapshot,
        scenario_id=body.scenario_id,
    )
    db.add(session)
    await db.commit()
    return session_data(session, [])


@router.get("/sessions/{session_id}")
async def get_interview(session_id: UUID, user: UserDep, db: DBDep):
    session = await get_session(db, user.id, session_id)
    return session_data(session, await get_exchanges(db, session))


@router.get("/sessions/{session_id}/note")
async def get_note(session_id: UUID, user: UserDep, db: DBDep):
    session = await get_session(db, user.id, session_id)
    return {"body": session.note_body or "", "updated_at": session.note_updated_at}


@router.put("/sessions/{session_id}/note")
async def save_note(session_id: UUID, body: NoteBody, user: UserDep, db: DBDep):
    session = await get_session(db, user.id, session_id, lock=True)
    session.note_body = body.body
    session.note_updated_at = utcnow()
    await db.commit()
    return {"body": session.note_body, "updated_at": session.note_updated_at}


@router.post("/sessions/{session_id}/questions")
async def ask(session_id: UUID, body: Question, user: UserDep, db: DBDep, provider: ProviderDep):
    session = await get_session(db, user.id, session_id, lock=True)
    exchanges = await get_exchanges(db, session)
    duplicate = next((item for item in exchanges if item.request_id == body.request_id), None)
    if duplicate:
        if duplicate.question != body.question:
            raise HTTPException(409, "同一請求識別碼已用於不同問題。")
        return exchange_data(duplicate)
    ensure_open(session)
    if exchanges and exchange_status(exchanges[-1])[0] in {"waiting", "failed"}:
        raise HTTPException(409, "請先處理上一題。")
    if len(exchanges) >= settings.INTERVIEW_MAX_QUESTIONS:
        raise HTTPException(409, "本場訪談已達題數上限，可以另開一場訪談。")

    exchange = InterviewExchange(
        session_id=session.id, sequence=len(exchanges) + 1, request_id=body.request_id,
        question=body.question, asked_at=utcnow(), attempt_count=0,
    )
    db.add(exchange)
    return exchange_data(await generate_answer(db, session, exchanges, exchange, provider))


@router.post("/sessions/{session_id}/questions/{sequence}/resolve")
async def resolve(
    session_id: UUID, sequence: int, body: ResolveQuestion, user: UserDep, db: DBDep, provider: ProviderDep
):
    session = await get_session(db, user.id, session_id, lock=True)
    ensure_open(session)
    exchanges = await get_exchanges(db, session)
    if not 1 <= sequence <= len(exchanges):
        raise HTTPException(404, "找不到此問題。")
    exchange = exchanges[sequence - 1]
    status, _ = exchange_status(exchange)
    if body.action == "skip":
        if status == "skipped":
            return exchange_data(exchange)
        if status == "failed":
            skip(exchange)
            await db.commit()
            return exchange_data(exchange)
    elif sequence == len(exchanges) and can_retry(exchange):
        wait = retry_wait(exchange)
        if wait:
            raise HTTPException(429, f"請等待 {wait} 秒後重試。", headers={"Retry-After": str(wait)})
        return exchange_data(await generate_answer(db, session, exchanges[:-1], exchange, provider))
    raise HTTPException(409, "這一題目前無法執行該操作。")


@router.post("/sessions/{session_id}/end")
async def end(session_id: UUID, user: UserDep, db: DBDep):
    session = await get_session(db, user.id, session_id, lock=True)
    exchanges = await get_exchanges(db, session)
    if session.ended_at is None:
        session.ended_at = utcnow()
        if exchanges and exchanges[-1].status in {"waiting", "failed"}:
            skip(exchanges[-1])
        await db.commit()
    return session_data(session, exchanges)


@router.get("/sessions/{session_id}/transcript", response_class=PlainTextResponse)
async def transcript(session_id: UUID, user: UserDep, db: DBDep):
    session = await get_session(db, user.id, session_id)
    exchanges = await get_exchanges(db, session)
    snapshot = session.scenario_snapshot or scenario_snapshot(session.stakeholder_id)
    profile_name = snapshot["stakeholder"]["name"]
    scenario = snapshot["scenario"]
    background = [scenario["description"]]
    if scenario["kind"] != "preset":
        background.insert(0, f"題目：{scenario['title']}")
    lines = [
        "MindCrew 模擬訪談（合成資料）", *background,
        f"Session ID: {session.id}", f"受訪者：{profile_name}（{session.stakeholder_id}）",
        f"開始：{session.started_at.isoformat()}",
        f"結束：{session.ended_at.isoformat() if session.ended_at else '進行中'}",
    ]
    for item in exchanges:
        lines.extend(("", f"{item.sequence}. 訪談者 [{item.asked_at.isoformat()}]", item.question))
        if item.answer is not None:
            lines.extend((f"{profile_name} [{item.answered_at.isoformat()}]", item.answer))
        else:
            lines.append("（尚未取得回答）")
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        headers={"Content-Disposition": f'attachment; filename="interview-{session.id}.txt"', "Cache-Control": "no-store"},
    )
