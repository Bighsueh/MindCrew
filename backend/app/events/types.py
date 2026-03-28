from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatMessageEvent:
    project_id: UUID
    sender_id: str
    sender_type: str
    sender_name: str
    content: str
    timestamp: str = field(default_factory=_now_iso)
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def type(self) -> str:
        return "chat_message"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "id": self.id,
                "sender_id": self.sender_id,
                "sender_type": self.sender_type,
                "sender_name": self.sender_name,
                "content": self.content,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class TypingEvent:
    project_id: UUID
    user_name: str
    is_typing: bool

    @property
    def type(self) -> str:
        return "typing_indicator"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "user_name": self.user_name,
                "is_typing": self.is_typing,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class StageChangedEvent:
    project_id: UUID
    from_stage: str
    to: str
    triggered_by: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "stage_changed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "from": self.from_stage,
                "to": self.to,
                "triggered_by": self.triggered_by,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class SeatChangedEvent:
    project_id: UUID
    seat_role: str
    previous_occupant_type: str
    previous_display_name: str
    current_occupant_type: str
    current_display_name: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "seat_changed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "seat_role": self.seat_role,
                "previous": {
                    "occupant_type": self.previous_occupant_type,
                    "display_name": self.previous_display_name,
                },
                "current": {
                    "occupant_type": self.current_occupant_type,
                    "display_name": self.current_display_name,
                },
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class SystemMessageEvent:
    project_id: UUID
    content: str
    level: str = "info"
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "system_message"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "content": self.content,
                "level": self.level,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class ProjectUpdateEvent:
    """Used on the teacher channel to notify teacher of project activity."""

    project_id: UUID
    current_stage: str
    note_count: int
    human_count: int
    last_activity: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "project_update"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "current_stage": self.current_stage,
                "note_count": self.note_count,
                "human_count": self.human_count,
                "last_activity": self.last_activity,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


AnyEvent = (
    ChatMessageEvent
    | TypingEvent
    | StageChangedEvent
    | SeatChangedEvent
    | SystemMessageEvent
    | ProjectUpdateEvent
)
