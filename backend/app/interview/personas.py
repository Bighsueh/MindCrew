from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, ValidationError, model_validator
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
    ("identity", "基本資料", "Basic information", (
        ("alias", "人物代號", "Alias", "short"), ("name", "姓名", "Name", "short"), ("age", "年齡", "Age", "short"),
        ("occupation", "職業／身分", "Occupation / role", "short"),
        ("context", "背景或生活情境", "Background or context", "long"),
        ("audience", "適用對象", "Audience", "short"),
    )),
    ("tasks", "目標與動機", "Goals and motivations", (
        ("goals", "主要目標", "Goals", "list"), ("motivations", "動機", "Motivation", "long"),
        ("needs", "需求", "Needs", "list"),
    )),
    ("empathy", "行為與痛點", "Behaviors and pain points", (
        ("behaviors", "行為", "Behaviors", "list"), ("habits", "習慣", "Habits", "long"),
        ("pain_points", "困難／痛點", "Pain points", "list"), ("practices", "現有做法", "Practices", "long"),
        ("resources", "使用資源與限制", "Resources and constraints", "long"),
        ("feelings", "感受", "Feelings", "long"),
    )),
    ("evidence", "來源與待查", "Sources and unknowns", (
        ("sources", "訪談來源", "Interview sources", "long"),
        ("reasoning", "推論理由", "Reasoning", "long"), ("unknowns", "未確認事項", "Unknowns", "list"),
    )),
)


class SourceRef(BaseModel):
    session_id: UUID
    sequence: int = Field(gt=0)
    speaker: Speaker


DEFAULT_ALIASES = {
    "occupation": ["工作", "職業", "身分", "occupation", "job", "role"],
    "name": ["名字", "full name"], "goals": ["目的", "objective"],
    "identity": ["個人資料", "profile"], "tasks": ["目標", "動機", "goals"],
    "empathy": ["行為", "痛點", "empathy"], "evidence": ["證據", "evidence"],
}


class DefinitionName(BaseModel):
    label: Label
    name_zh: Label | None = None
    name_en: Label | None = None
    aliases: list[Label] = Field(default_factory=list, max_length=24)


class GroupRef(DefinitionName):
    id: FieldId


class PersonaField(DefinitionName):
    field_id: FieldId
    group_id: FieldId | None = None
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
    groups: list[GroupRef] | None = Field(default=None, max_length=64)
    fields: list[PersonaField] = Field(max_length=64)

    @model_validator(mode="after")
    def validate_fields(self):
        if self.groups is not None:
            group_ids = {group.id for group in self.groups}
            if len(group_ids) != len(self.groups) or any(
                field.group_id is not None and field.group_id not in group_ids for field in self.fields
            ):
                raise ValueError("欄位群組無效。")
        ids = [field.field_id for field in self.fields]
        if len(set(ids)) != len(ids):
            raise ValueError("欄位 ID 不得重複。")
        if sum(len(field.value) if isinstance(field.value, str) else sum(map(len, field.value)) for field in self.fields) > 120000:
            raise ValueError("Persona 內容總長度不可超過 120000 字。")
        return self


def persona_data(row: InterviewPersona) -> dict:
    is_document = isinstance(row.fields, dict)
    return {
        "id": row.id, "title": row.title,
        "fields": row.fields["fields"] if is_document else row.fields,
        "groups": row.fields["groups"] if is_document else None,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


async def owned_persona(db: AsyncSession, owner_id: UUID, persona_id: UUID) -> InterviewPersona:
    row = await db.scalar(select(InterviewPersona).where(
        InterviewPersona.id == persona_id, InterviewPersona.owner_id == owner_id,
    ))
    if row is None:
        raise HTTPException(404, "找不到 Persona。")
    return row


async def validated_fields(db: AsyncSession, owner_id: UUID, body: PersonaBody) -> list[dict] | dict:
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
    fields = [
        {**field.model_dump(mode="json"), "position": position}
        for position, field in enumerate(body.fields)
    ]
    if body.groups is None:
        return fields
    return {"fields": fields, "groups": [group.model_dump() for group in body.groups]}


@persona_router.get("")
async def list_personas(user: UserDep, db: DBDep):
    query = select(InterviewPersona).where(InterviewPersona.owner_id == user.id).order_by(
        InterviewPersona.updated_at.desc(), InterviewPersona.id,
    )
    rows = list(await db.scalars(query))
    definitions = {}
    group_definitions = {}
    for row in rows:
        saved = persona_data(row)
        for group in saved["groups"] or []:
            group_definitions.setdefault(group["id"], {
                key: group[key] for key in ("id", "label", "name_zh", "name_en", "aliases") if key in group
            })
        for field in saved["fields"]:
            definitions.setdefault(field["field_id"], {
                **{key: field[key] for key in ("field_id", "label", "name_zh", "name_en", "aliases", "type") if key in field},
                "value": [] if field["type"] == "list" else "", "source_refs": [],
            })
    return {
        "definitions": list(definitions.values()),
        "group_definitions": list(group_definitions.values()),
        "personas": [
            {"id": row.id, "title": row.title, "updated_at": row.updated_at}
            for row in rows
        ],
        "groups": [
            {"id": group_id, "label": label, "name_zh": label, "name_en": english, "aliases": DEFAULT_ALIASES.get(group_id, []), "fields": [
                {"field_id": field_id, "label": field_label, "name_zh": field_label, "name_en": field_en, "group_id": group_id, "type": field_type,
                 "value": [] if field_type == "list" else "", "source_refs": [],
                 "aliases": DEFAULT_ALIASES.get(field_id, [])}
                for field_id, field_label, field_en, field_type in fields
            ]}
            for group_id, label, english, fields in DEFAULT_FIELDS
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
    saved = persona_data(row)
    if saved["fields"] or saved["groups"] is not None:
        previous = {field["field_id"]: field for field in saved["fields"]}
        fields = []
        for field in body.fields:
            data = field.model_dump(exclude_unset=True)
            stored = previous.get(field.field_id, {})
            for key in ("group_id", "name_zh", "name_en", "aliases"):
                if (key not in data or (key == "group_id" and body.groups is None and data[key] is None)) and key in stored:
                    data[key] = stored[key]
            fields.append(data)
        try:
            existing_groups = {group["id"]: group for group in saved["groups"] or []}
            groups = saved["groups"] if body.groups is None else [
                {**existing_groups.get(group.id, {}), **group.model_dump(exclude_unset=True)}
                for group in body.groups
            ]
            body = PersonaBody.model_validate({"title": body.title, "groups": groups, "fields": fields})
        except ValidationError:
            raise HTTPException(422, "欄位群組無效。") from None
    row.fields = await validated_fields(db, user.id, body)
    row.title, row.updated_at = body.title, utcnow()
    await db.commit()
    return persona_data(row)
