from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.timer.schemas import TimerConfig


# ---------------------------------------------------------------------------
# Persona schemas (Phase 19)
# ---------------------------------------------------------------------------


class LensAffinitiesPayload(BaseModel):
    empathy: float = 0.5
    structure: float = 0.5
    creativity: float = 0.5
    feasibility: float = 0.5

    @field_validator("empathy", "structure", "creativity", "feasibility")
    @classmethod
    def _clamp(cls, value: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5


class PersonaPayload(BaseModel):
    """Per-project AI persona snapshot.

    Mirrors :class:`app.agents.personas.models.Persona` for transport.
    """

    name: str = Field(..., min_length=1, max_length=64)
    role: str = Field(..., min_length=1, max_length=128)
    expertise: str = Field("", max_length=256)
    personality_axis: str = Field("balanced")
    personality_desc: str = Field("", max_length=256)
    backstory: str = Field("", max_length=256)
    lens_affinities: LensAffinitiesPayload = Field(
        default_factory=LensAffinitiesPayload
    )

    @field_validator("personality_axis")
    @classmethod
    def _validate_axis(cls, value: str) -> str:
        allowed = {"contrarian", "balanced", "supportive"}
        cleaned = (value or "").strip().lower()
        return cleaned if cleaned in allowed else "balanced"


class CrewPersonaAssignment(BaseModel):
    """Mapping of one crew seat_role to a Persona for project creation."""

    seat_role: str = Field(..., pattern=r"^crew_[1-4]$")
    persona: PersonaPayload


MIN_AI_CREW = 1
MAX_AI_CREW = 4


# Phase 28:可切換的三模式輪流規則。
ALLOWED_TURN_POLICIES = ("cued", "round_robin", "open_floor")
DEFAULT_TURN_POLICY = "cued"


def _validate_turn_policy(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = (value or "").strip().lower()
    if cleaned not in ALLOWED_TURN_POLICIES:
        raise ValueError(
            f"turn_policy 必須為 {ALLOWED_TURN_POLICIES} 其中之一，收到 {value!r}"
        )
    return cleaned


def _expected_crew_slots(ai_crew_count: int) -> tuple[str, ...]:
    return tuple(f"crew_{i}" for i in range(1, ai_crew_count + 1))


class StakeholderSelectionPayload(BaseModel):
    """Phase 27：使用者從 AI 建議的利害關係人地圖中勾選的一位。"""

    id: str = Field("", max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    role: str = Field(..., min_length=1, max_length=128)
    relevance: str = Field("", max_length=128)


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    constraints: str | None = None
    # Phase 27：建立時使用者勾選的利害關係人（長度必須 == ai_crew_count）。
    stakeholders: list[StakeholderSelectionPayload] = Field(
        default_factory=list,
        max_length=MAX_AI_CREW,
        description="Phase 27 open brief 三步驟 wizard Step 2 勾選結果",
    )
    ai_contribution: str = "medium"
    # Phase 21: 教師可自訂 AI 組員人數（1..4），預設 3。
    ai_crew_count: int = Field(default=3, ge=MIN_AI_CREW, le=MAX_AI_CREW)
    personas: list[CrewPersonaAssignment] = Field(
        ..., min_length=MIN_AI_CREW, max_length=MAX_AI_CREW
    )
    # ：建立者必須明確選擇 timer preset / 自訂 macro budget。
    # 未來開放學生自助建專案後，這個必填確保不會出現「沒人啟用 timer」的狀況。
    timer_config: "TimerConfig" = Field(..., description="必填：建立者選的 preset 或自訂配置")
    # Phase 22：學生建立活動時可選填教師的 signature_code 直接列管
    teacher_signature_code: str | None = Field(default=None, max_length=8)
    # Phase 28：建立時的 turn-taking policy；未填則由 DB server_default 補 'cued'。
    turn_policy: str | None = Field(default=None, description="cued / round_robin / open_floor")

    @field_validator("turn_policy")
    @classmethod
    def _validate_turn_policy_field(cls, value: str | None) -> str | None:
        return _validate_turn_policy(value)

    @model_validator(mode="after")
    def _validate_personas_match_crew_count(self) -> "ProjectCreateRequest":
        expected = _expected_crew_slots(self.ai_crew_count)
        if len(self.personas) != len(expected):
            raise ValueError(
                f"personas: 需要 {len(expected)} 位 (與 ai_crew_count={self.ai_crew_count} 一致)，"
                f"但收到 {len(self.personas)} 位"
            )
        seen = {item.seat_role for item in self.personas}
        if len(seen) != len(self.personas):
            raise ValueError("personas: seat_role 不可重複")
        missing = set(expected) - seen
        if missing:
            raise ValueError(
                f"personas: 缺少 {sorted(missing)}，必須覆蓋 {list(expected)}"
            )
        extra = seen - set(expected)
        if extra:
            raise ValueError(
                f"personas: 多出 {sorted(extra)}，僅允許 {list(expected)}"
            )
        # Phase 27：stakeholders 若提供，數量必須與 ai_crew_count 對齊。
        # 為了向下相容（v1.x 舊客戶端可能沒帶 stakeholders），允許空陣列
        # 並由 service 層補 task_brief_kind='legacy'。
        if self.stakeholders and len(self.stakeholders) != self.ai_crew_count:
            raise ValueError(
                f"stakeholders: 提供時長度需 == ai_crew_count={self.ai_crew_count}，"
                f"但收到 {len(self.stakeholders)} 位"
            )
        return self


class ProjectTimerInitRequest(BaseModel):
    """為舊專案補 timer 的 payload。config=None 走 DEFAULT_PRESET（90 分）。"""

    config: "TimerConfig | None" = None


class SeatResponse(BaseModel):
    seat_role: str
    occupant_type: str
    user_id: UUID | None = None
    agent_id: str | None = None
    display_name: str | None = None
    persona: dict[str, Any] | None = None
    # Phase 21: 在第一位真人入座前 AI 為 "dormant"——前端據此顯示「待加入」。
    is_active: bool = True
    # Phase 22：席位識別色（首次出聲後鎖定；前端聊天氣泡＋便利貼預設色）
    sticky_color: str | None = None

    model_config = {"from_attributes": True}


class LinkedTeacherInfo(BaseModel):
    id: UUID
    display_name: str

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    constraints: str | None = None
    # Phase 27：建立時使用者勾選的利害關係人；舊 project 為 []
    stakeholders: list[dict[str, Any]] = Field(default_factory=list)
    task_brief_kind: str = "legacy"
    current_stage: str
    ai_contribution: str
    status: str
    creator_id: UUID
    seats: list[SeatResponse] = []
    created_at: datetime
    # Phase 22
    invite_code: str | None = None
    linked_teacher: LinkedTeacherInfo | None = None
    # Phase 28：當前輪流規則
    turn_policy: str = DEFAULT_TURN_POLICY
    # Phase 30：DEMO 導覽完成記錄（{user_id: ISO8601}）。前端用此 map 決定是否顯示 0.1 tour。
    tour_acknowledged_by: dict[str, str] = Field(default_factory=dict)
    # 當前 viewer 對此專案的角色：creator（可入座）/ observer（列管老師、admin，只能旁觀）/ None。
    # 由 service 依 current_user 計算；前端據此決定顯示入座鈕或觀察者入口。
    viewer_role: str | None = None

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    current_stage: str
    status: str
    creator_id: UUID
    seat_summary: dict[str, int]
    created_at: datetime
    updated_at: datetime
    # Phase 22
    invite_code: str | None = None
    linked_teacher: LinkedTeacherInfo | None = None
    # Phase 28：當前輪流規則
    turn_policy: str = DEFAULT_TURN_POLICY

    model_config = {"from_attributes": True}


class LinkTeacherRequest(BaseModel):
    signature_code: str = Field(..., min_length=4, max_length=8)


class TrackByInviteCodeRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=8)


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    constraints: str | None = None
    ai_contribution: str | None = None
    # Phase 28：creator 也可在 update 時順手調整 turn_policy（教師另有 PATCH /turn-policy 專用 endpoint）。
    turn_policy: str | None = None

    @field_validator("turn_policy")
    @classmethod
    def _validate_turn_policy_field(cls, value: str | None) -> str | None:
        return _validate_turn_policy(value)


class TurnPolicyUpdateRequest(BaseModel):
    """Phase 28：教師或 admin 切換專案輪流規則。

    詳 ``。
    """

    policy: str

    @field_validator("policy")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = _validate_turn_policy(value)
        if cleaned is None:
            raise ValueError("policy 不可為 null")
        return cleaned


class TurnPolicyResponse(BaseModel):
    policy: str
    applied_at: datetime


class TourAcknowledgeResponse(BaseModel):
    """Phase 30 (spec/22 §2.1)：0.1 DEMO 導覽完成 ack 回應。

    tour_acknowledged_by 為 ``{user_id: ISO8601 timestamp}`` 字典。
    """

    tour_acknowledged_by: dict[str, str]


# TemplateSuggestRequest / TemplateSuggestResponse 已隨 AI 起稿 endpoint 下架移除
# （Phase 42 補正 R3／P1-6 ARCHIVE，spec 23 v2.2；模組本體留 app/agents/template_suggest/）。


class JoinRequest(BaseModel):
    seat_role: str


class JoinResponse(BaseModel):
    seat: SeatResponse
    workspace_url: str


class CanvasNoteResponse(BaseModel):
    id: str
    content: str
    color: str
    author: str = ""
    group_name: str | None = None
    # Spec 27 (Phase 36) §10 / spec 06 delta：接話式便條欄位。
    kind: str = "content"            # "content" | "label"
    group_id: str | None = None
    # Phase 42 C0 (spec 06 v4.25)：引用鏈與 time-box 強推標記。
    cites: list[str] = []
    time_box_forced: bool = False


class CanvasGroupResponse(BaseModel):
    name: str
    notes: list[str]


class CanvasStateResponse(BaseModel):
    total_notes: int
    groups: list[CanvasGroupResponse]
    ungrouped: list[str]
    notes: list[CanvasNoteResponse]


class ProjectSummaryResponse(BaseModel):
    summary: str
    topics: list[str]
    current_focus: str
    blind_spots: list[str]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Persona API schemas (Phase 19)
# ---------------------------------------------------------------------------


class PersonaGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    constraints: str | None = Field(default=None, max_length=2048)
    num_personas: int = Field(default=4, ge=1, le=8)
    # Phase 27：使用者於 Step 2 勾選的利害關係人；若提供則跳過內部 stakeholder mapping
    stakeholders: list[StakeholderSelectionPayload] | None = None


class PersonaGenerateResponse(BaseModel):
    personas: list[PersonaPayload]


class SeatPersonaUpdateRequest(BaseModel):
    persona: PersonaPayload


# ---------------------------------------------------------------------------
# Phase 27: Draft endpoints (Open Brief 三步驟 wizard)
# ---------------------------------------------------------------------------


class SuggestConstraintsRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field("", max_length=2048)


class SuggestConstraintsResponse(BaseModel):
    budget_hints: list[str] = Field(default_factory=list)
    audience_hints: list[str] = Field(default_factory=list)
    venue_hints: list[str] = Field(default_factory=list)
    other_hints: list[str] = Field(default_factory=list)


class SuggestStakeholdersRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    constraints: str | None = Field(default=None, max_length=2048)
    existing_names: list[str] | None = Field(
        default=None,
        max_length=20,  # avoid runaway prompt injection
        description="若使用者按「再請 AI 建議幾位」追加，傳入既有名單以避免重複",
    )

    @field_validator("existing_names")
    @classmethod
    def _cap_existing_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        capped: list[str] = []
        for name in value:
            if not isinstance(name, str):
                continue
            # strip newlines (prompt-injection hardening) + bound length
            cleaned = name.replace("\n", " ").replace("\r", " ").strip()
            if cleaned:
                capped.append(cleaned[:64])
        return capped


class StakeholderSuggestionPayload(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    role: str = Field(..., min_length=1, max_length=128)
    relevance: str = Field("", max_length=128)


class SuggestStakeholdersResponse(BaseModel):
    suggestions: list[StakeholderSuggestionPayload]
