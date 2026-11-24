from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.models.interview import InterviewExchange, InterviewPersona, InterviewSession
from app.db.models.user import User
from app.db.session import get_db_session
from app.interview.service import utcnow

persona_router = APIRouter(prefix="/personas")
UserDep = Annotated[User, Depends(get_current_user)]
DBDep = Annotated[AsyncSession, Depends(get_db_session)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]+$")]
FieldId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
FieldText = Annotated[str, StringConstraints(max_length=12000, pattern=r"^[^\x00]*$")]
FieldType = Literal["short", "long", "list"]
Speaker = Literal["student", "stakeholder"]

DEFAULT_FIELDS = (
    ("identity", "身分與範圍", (
        ("alias", "人物代號", "short"), ("audience", "適用對象", "short"), ("context", "使用情境", "long"),
    )),
    ("tasks", "任務與經驗", (
        ("goals", "目標", "list"), ("behaviors", "典型行為", "list"),
        ("practices", "現有做法", "long"), ("resources", "使用資源與限制", "long"),
    )),
    ("empathy", "同理理解", (
        ("pain_points", "困難／痛點", "list"), ("needs", "需求", "list"),
        ("motivations", "動機", "long"), ("feelings", "感受", "long"),
    )),
    ("evidence", "來源與待查", (
        ("sources", "訪談來源", "long"), ("reasoning", "推論理由", "long"),
        ("unknowns", "未確認事項", "list"),
    )),
)


class SourceRef(BaseModel):
    session_id: UUID
    sequence: int = Field(gt=0)
    speaker: Speaker


class PersonaField(BaseModel):
    field_id: FieldId
    label: Label
    type: FieldType
    value: FieldText | Annotated[list[FieldText], Field(max_length=100)]
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def validate_value(self):
        if (self.type == "list") != isinstance(self.value, list):
            raise ValueError("欄位值與欄位型別不符。")
        if self.type == "short" and len(self.value) > 280:
            raise ValueError("短文字最多 280 字。")
        refs = {(item.session_id, item.sequence, item.speaker) for item in self.source_refs}
        if len(refs) != len(self.source_refs):
            raise ValueError("同一欄位不可重複引用同一訊息。")
        return self


class PersonaBody(BaseModel):
    title: Label
    fields: list[PersonaField] = Field(max_length=64)

    @model_validator(mode="after")
    def validate_fields(self):
        ids = [field.field_id for field in self.fields]
        if len(set(ids)) != len(ids):
            raise ValueError("欄位 ID 不得重複。")
        if sum(len(field.value) if isinstance(field.value, str) else sum(map(len, field.value)) for field in self.fields) > 120000:
            raise ValueError("Persona 內容總長度不可超過 120000 字。")
        return self


def persona_data(row: InterviewPersona) -> dict:
    return {
        "id": row.id, "title": row.title, "fields": row.fields,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


async def owned_persona(db: AsyncSession, owner_id: UUID, persona_id: UUID) -> InterviewPersona:
    row = await db.scalar(select(InterviewPersona).where(
        InterviewPersona.id == persona_id, InterviewPersona.owner_id == owner_id,
    ))
    if row is None:
        raise HTTPException(404, "找不到 Persona。")
    return row


async def validated_fields(db: AsyncSession, owner_id: UUID, body: PersonaBody) -> list[dict]:
    refs = {(ref.session_id, ref.sequence, ref.speaker) for field in body.fields for ref in field.source_refs}
    if len(refs) > 200:
        raise HTTPException(422, "Persona 最多可引用 200 則訊息。")
    if refs:
        query = select(InterviewExchange.session_id, InterviewExchange.sequence, InterviewExchange.answer).join(
            InterviewSession, InterviewSession.id == InterviewExchange.session_id,
        ).where(
            InterviewSession.owner_id == owner_id,
            tuple_(InterviewExchange.session_id, InterviewExchange.sequence).in_(
                {(session_id, sequence) for session_id, sequence, _ in refs}
            ),
        )
        evidence = {(session_id, sequence): answer for session_id, sequence, answer in await db.execute(query)}
        for session_id, sequence, speaker in refs:
            key = (session_id, sequence)
            if key not in evidence or (speaker == "stakeholder" and evidence[key] is None):
                raise HTTPException(422, "請引用自己訪談中已保存的訊息。")
    return [
        {**field.model_dump(mode="json"), "position": position}
        for position, field in enumerate(body.fields)
    ]


@persona_router.get("")
async def list_personas(user: UserDep, db: DBDep):
    query = select(InterviewPersona).where(InterviewPersona.owner_id == user.id).order_by(
        InterviewPersona.updated_at.desc(), InterviewPersona.id,
    )
    return {
        "personas": [
            {"id": row.id, "title": row.title, "updated_at": row.updated_at}
            for row in await db.scalars(query)
        ],
        "groups": [
            {"id": group_id, "label": label, "fields": [
                {"field_id": field_id, "label": field_label, "type": field_type,
                 "value": [] if field_type == "list" else "", "source_refs": []}
                for field_id, field_label, field_type in fields
            ]}
            for group_id, label, fields in DEFAULT_FIELDS
        ],
    }


@persona_router.get("/{persona_id}")
async def get_persona(persona_id: UUID, user: UserDep, db: DBDep):
    return persona_data(await owned_persona(db, user.id, persona_id))


@persona_router.post("", status_code=201)
async def create_persona(body: PersonaBody, user: UserDep, db: DBDep):
    now = utcnow()
    row = InterviewPersona(
        owner_id=user.id, title=body.title, fields=await validated_fields(db, user.id, body),
        created_at=now, updated_at=now,
    )
    db.add(row)
    await db.commit()
    return persona_data(row)


@persona_router.put("/{persona_id}")
async def update_persona(persona_id: UUID, body: PersonaBody, user: UserDep, db: DBDep):
    row = await owned_persona(db, user.id, persona_id)
    row.fields = await validated_fields(db, user.id, body)
    row.title, row.updated_at = body.title, utcnow()
    await db.commit()
    return persona_data(row)
