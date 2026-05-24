"""Persona data structures.

A ``Persona`` represents one AI crew member's identity in a specific
project. Personas live on ``seat.persona`` (JSONB) and are not shared
across projects in this MVP.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from app.agents.personas.lens import CognitiveLens, LENS_VALUES


class PersonalityAxis(str, Enum):
    """Whether the persona tends to push back or go along with the group."""

    CONTRARIAN = "contrarian"
    BALANCED = "balanced"
    SUPPORTIVE = "supportive"


@dataclass(frozen=True)
class LensAffinities:
    """How strongly a persona leans toward each cognitive lens (0..1)."""

    empathy: float = 0.5
    structure: float = 0.5
    creativity: float = 0.5
    feasibility: float = 0.5

    def get(self, lens: CognitiveLens) -> float:
        return float(getattr(self, lens.value, 0.0))

    def as_dict(self) -> dict[str, float]:
        return {
            "empathy": self.empathy,
            "structure": self.structure,
            "creativity": self.creativity,
            "feasibility": self.feasibility,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LensAffinities":
        if not data:
            return cls()
        clamp = lambda v: max(0.0, min(1.0, float(v)))  # noqa: E731
        return cls(
            empathy=clamp(data.get("empathy", 0.5)),
            structure=clamp(data.get("structure", 0.5)),
            creativity=clamp(data.get("creativity", 0.5)),
            feasibility=clamp(data.get("feasibility", 0.5)),
        )


@dataclass(frozen=True)
class Persona:
    """Concrete AI crew member identity.

    Attributes:
        name: 顯示名稱 (中文，具體姓名)
        role: 20 字內的職稱/身份描述
        expertise: 30 字內的專長範圍 (列 2-3 個具體面向)
        personality_axis: contrarian | balanced | supportive
        personality_desc: 個性特質短語清單，以頓號或逗號分隔（如「開朗樂觀、明察秋毫、思考跳躍」）
        backstory: 30 字內背景說明
        lens_affinities: 對四種認知透鏡的傾向分數
    """

    name: str
    role: str
    expertise: str
    personality_axis: PersonalityAxis = PersonalityAxis.BALANCED
    personality_desc: str = ""
    backstory: str = ""
    lens_affinities: LensAffinities = field(default_factory=LensAffinities)

    def dominant_lens(self) -> CognitiveLens:
        """Return the lens with the highest affinity (tie-breaks by enum order)."""
        affinities = self.lens_affinities
        best_lens = CognitiveLens.EMPATHY
        best_score = -1.0
        for lens in CognitiveLens:
            score = affinities.get(lens)
            if score > best_score:
                best_score = score
                best_lens = lens
        return best_lens


def persona_to_dict(persona: Persona) -> dict[str, Any]:
    """Serialize a Persona for JSONB storage."""
    data = asdict(persona)
    # Enum → str for JSON compatibility
    data["personality_axis"] = persona.personality_axis.value
    data["lens_affinities"] = persona.lens_affinities.as_dict()
    return data


def persona_from_dict(data: dict[str, Any] | None) -> Persona | None:
    """Deserialize a Persona from JSONB storage. Returns None if invalid."""
    if not data:
        return None
    try:
        name = str(data.get("name", "")).strip()
        role = str(data.get("role", "")).strip()
        expertise = str(data.get("expertise", "")).strip()
        if not name or not role:
            return None
        axis_raw = str(data.get("personality_axis", "balanced")).strip().lower()
        try:
            axis = PersonalityAxis(axis_raw)
        except ValueError:
            axis = PersonalityAxis.BALANCED
        return Persona(
            name=name,
            role=role,
            expertise=expertise,
            personality_axis=axis,
            personality_desc=str(data.get("personality_desc", "")),
            backstory=str(data.get("backstory", "")),
            lens_affinities=LensAffinities.from_dict(data.get("lens_affinities")),
        )
    except (TypeError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Fallback personas (legacy capability-style — used when persona is NULL)
# ---------------------------------------------------------------------------

_FALLBACK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "crew_1": {
        "name": "AI 同理心專家",
        "role": "使用者研究員",
        "expertise": "使用者觀察、情緒洞察、需求挖掘",
        "personality_axis": "supportive",
        "personality_desc": "細膩敏感、情緒共感力強、傾聽優先",
        "backstory": "預設角色，當未指定具體人設時啟用",
        "lens_affinities": {
            "empathy": 0.9,
            "structure": 0.3,
            "creativity": 0.4,
            "feasibility": 0.4,
        },
    },
    "crew_2": {
        "name": "AI 結構化專家",
        "role": "系統思考者",
        "expertise": "資訊整理、模式識別、邏輯框架",
        "personality_axis": "balanced",
        "personality_desc": "邏輯清晰、有系統觀、善歸納",
        "backstory": "預設角色，當未指定具體人設時啟用",
        "lens_affinities": {
            "empathy": 0.3,
            "structure": 0.9,
            "creativity": 0.4,
            "feasibility": 0.5,
        },
    },
    "crew_3": {
        "name": "AI 創意專家",
        "role": "跨界發想者",
        "expertise": "類比聯想、反向思考、跳脫框架",
        "personality_axis": "contrarian",
        "personality_desc": "思考跳躍、好奇求新、敢挑戰前提",
        "backstory": "預設角色，當未指定具體人設時啟用",
        "lens_affinities": {
            "empathy": 0.4,
            "structure": 0.3,
            "creativity": 0.9,
            "feasibility": 0.3,
        },
    },
    "crew_4": {
        "name": "AI 可行性專家",
        "role": "落地策略師",
        "expertise": "資源評估、技術約束、實施路徑",
        "personality_axis": "balanced",
        "personality_desc": "務實穩健、目標導向、執行力強",
        "backstory": "預設角色，當未指定具體人設時啟用",
        "lens_affinities": {
            "empathy": 0.3,
            "structure": 0.5,
            "creativity": 0.3,
            "feasibility": 0.9,
        },
    },
}


def build_fallback_personas() -> dict[str, Persona]:
    """Return the legacy 4-capability personas keyed by seat_role.

    Used when ``seat.persona`` is NULL (backward compatibility).
    """
    return {
        seat_role: persona_from_dict(payload)
        for seat_role, payload in _FALLBACK_DEFINITIONS.items()
        if persona_from_dict(payload) is not None
    }


def fallback_persona_for(seat_role: str) -> Persona | None:
    """Return the legacy fallback persona for a given seat_role, if any."""
    payload = _FALLBACK_DEFINITIONS.get(seat_role)
    return persona_from_dict(payload) if payload else None


# ---------------------------------------------------------------------------
# Phase 27: StakeholderSuggestion — concrete people the user picks from
# (see specs/17-dynamic-persona-system.md §3.0.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StakeholderSuggestion:
    """One AI-suggested potential stakeholder for the user to pick from.

    These are concrete people (not abstract categories). The user picks N of
    them, which then seed the persona instantiation stage and persist into
    ``project.stakeholders``.
    """

    id: str          # uuid; frontend tracks selection across requests
    name: str        # 中文短稱，如「林阿嬤」
    role: str        # 一行身份，如「獨居山區的 78 歲農婦」
    relevance: str   # < 40 字說明為何相關


def stakeholder_suggestion_to_dict(s: StakeholderSuggestion) -> dict[str, str]:
    return {"id": s.id, "name": s.name, "role": s.role, "relevance": s.relevance}


def stakeholder_suggestion_from_dict(
    data: dict[str, Any] | None,
) -> StakeholderSuggestion | None:
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    role = str(data.get("role", "")).strip()
    if not name or not role:
        return None
    return StakeholderSuggestion(
        id=str(data.get("id", "")).strip(),
        name=name,
        role=role,
        relevance=str(data.get("relevance", "")).strip(),
    )


__all__ = [
    "LENS_VALUES",
    "Persona",
    "PersonalityAxis",
    "LensAffinities",
    "StakeholderSuggestion",
    "persona_to_dict",
    "persona_from_dict",
    "stakeholder_suggestion_to_dict",
    "stakeholder_suggestion_from_dict",
    "build_fallback_personas",
    "fallback_persona_for",
]
