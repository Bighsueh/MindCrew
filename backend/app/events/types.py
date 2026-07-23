from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatMessageEvent:
    # spec/13-personal-chat.md §6.3：新增 ``chat_id`` 欄位以支援個人聊天路由。
    # ``chat_id is None`` 視為 group（向下相容既有 caller）。
    project_id: UUID
    sender_id: str
    sender_type: str
    sender_name: str
    content: str
    chat_id: str | None = None
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
                # 個人聊天透過 WS forwarder 依 chat_id 過濾收件人；
                # 群組訊息保持 chat_id=None（前端視為 group）。
                "chat_id": self.chat_id,
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


# ArtifactGateRejectedEvent 已廢除（spec 25 v2.1 §4，Phase 42 補正 R2）：
# Phase 33 起前端從未實作 handler（死事件），payload 帶機器層模板鍵名（#29 風險）。
# 拒絕回饋走組長代言（reasons_zh 素材）＋ advance 結果字串兩條活路徑。


@dataclass
class FirstDiamondCompletedEvent:
    """Phase 29 (2026-05-26)：第一鑽石終局事件。

    當 ``advance_stage`` 將 ``current_stage`` 推進至 ``completed`` 時，緊接
    ``StageChangedEvent`` 之後 publish。Phase 34 的 closing ritual 會訂閱此
    事件，由 supervisor 主持結業匯報並寫入 ``project.first_diamond_output``。

    payload 目前只含 project_id / triggered_by；Phase 34 將擴充 chosen_hmw /
    chosen_problem_statement / personas 等欄位（或由 closing ritual 從 DB 補
    撈，view 端訂閱完整 payload 由 banner 元件決定）。
    """

    project_id: UUID
    triggered_by: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "first_diamond_completed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "triggered_by": self.triggered_by,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class MicroPhaseChangedEvent:
    project_id: UUID
    from_phase: str
    to_phase: str
    transition_type: str
    triggered_by: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "micro_phase_changed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "from_phase": self.from_phase,
                "to_phase": self.to_phase,
                "transition_type": self.transition_type,
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
    # 前端以 current.user_id 判定真人席是否空置（None → vacant → 顯示入座鈕）。
    # 預設 None 維持既有行為；assign/release 真人席時明確帶入。
    current_user_id: str | None = None
    current_agent_id: str | None = None
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
                    "user_id": self.current_user_id,
                    "agent_id": self.current_agent_id,
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


@dataclass
class CueEvent:
    """Phase 28：supervisor 用 set_directive 點名某 crew 時廣播。

    前端依此觸發 useCueNotification (banner + ChatInput 邊框閃爍 + 桌面通知)。
    """

    project_id: UUID
    target_seat_role: str
    from_seat_role: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "cue"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "target_seat_id": self.target_seat_role,
                "from_seat_id": self.from_seat_role,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class TurnStateEvent:
    """Phase 28：Round-Robin 模式下，next_speaker 變動時廣播。

    其他 policy 下 next_speaker 沒有強制次序 (Open-Floor) 或為自己 (Cued
    supervisor)，所以這個事件主要服務 RR。
    """

    project_id: UUID
    policy: str
    next_speaker: str | None
    allowed_actions: tuple[str, ...]
    # Phase 42 補正 R4（A-P2，spec 06 additive）：發布者標記——"round_lock"＝回合鎖
    # 解鎖/清除路徑；"policy"＝輪替政策層。前端只在 round_lock 來源時清「等待真人」列，
    # 修復「任何 turn_state 都清 waiting」被政策層事件提前清掉且 waitpub NX 不重發的洞。
    source: str = "policy"
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "turn_state"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "policy": self.policy,
                "next_speaker": self.next_speaker,
                "allowed_actions": list(self.allowed_actions),
                "source": self.source,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class TurnPolicyChangedEvent:
    """Phase 28:teacher 切換 turn_policy 時廣播。

    Agent decision loop 每次 ASSESS 都會重讀 project.turn_policy，所以此 event 主要
    給前端與觀察者用（更新 UI、調整 ChatInput 條件式按鈕）。
    """

    project_id: UUID
    policy: str
    changed_by: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "turn_policy_changed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "policy": self.policy,
                "changed_by": self.changed_by,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class CueTimeoutEvent:
    """Phase 28: 人類被 cue 後單次倒數結束（可能即將 retry 也可能 abandon）。

    每個 retry cycle 都會 publish 一次。前端用來顯示 observer 狀態 B1（紅框 3-5 秒
    「正在再次邀請」）。`will_retry=False` 之後緊接 CueAbandonedEvent。
    """

    project_id: UUID
    target_seat_role: str
    from_seat_role: str
    timeout_seconds: int
    retry_count: int       # 已 retry 過幾次（0=首次 timeout）
    max_retries: int
    will_retry: bool       # True=接下來會 reminder；False=已達上限即將 abandon
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "cue_timeout"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "target_seat_role": self.target_seat_role,
                "from_seat_role": self.from_seat_role,
                "timeout_seconds": self.timeout_seconds,
                "retry_count": self.retry_count,
                "max_retries": self.max_retries,
                "will_retry": self.will_retry,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class CueAbandonedEvent:
    """Phase 28: 達 retry 上限後 supervisor 完全放棄、進入 pivot 模式。

    前端用來顯示 observer 狀態 B2（紅框 30 秒「AI 接手」後淡出回 idle）。
    """

    project_id: UUID
    target_seat_role: str
    from_seat_role: str
    total_attempts: int        # 總共 cue 過幾次（= cue_max_retries + 1）
    elapsed_seconds: int       # 首次 cue 到 abandon 的總秒數
    cooldown_seconds: int      # 後續禁邀請秒數（預設 300）
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "cue_abandoned"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "target_seat_role": self.target_seat_role,
                "from_seat_role": self.from_seat_role,
                "total_attempts": self.total_attempts,
                "elapsed_seconds": self.elapsed_seconds,
                "cooldown_seconds": self.cooldown_seconds,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class WaitingForHumanEvent:
    """Phase 42 A2 (spec 20 v2.0 §5.6 / §11)：回合鎖凍結，等待真人有效輸入。

    前端據此顯示「等待真人輸入中」**顯式狀態**（不可只靠聊天流暗示）。``required``
    含型態旗標與組合語意 ``mode``（"all"=全部都要、"any"=擇一）；解鎖判定一律在後端，
    前端僅據此渲染提示文案。解鎖 / 推進後以 ``turn_state`` 回復正常狀態。
    """

    project_id: UUID
    sub_phase: str
    round: int
    required: dict  # {note, chat, move, confirm: bool, mode: "all"|"any"}
    target_user_id: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "waiting_for_human"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "sub_phase": self.sub_phase,
                "round": self.round,
                "required": self.required,
                "target_user_id": self.target_user_id,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class InputBouncedEvent:
    """Phase 42 A2 (spec 20 v2.0 §5.7 / §12)：真人輸入未過實質檢核的即時退回提示。

    訊息照常顯示於聊天流，被退回的只是「解鎖效力」。``reason_zh`` / ``hint_zh`` 為
    內容層中文白話（退回原因＋「怎樣才算」教練式提示），**不得**含 gate / 檢核 /
    規則名等內部機制詞（#29）。
    """

    project_id: UUID
    user_id: str
    reason_zh: str
    hint_zh: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "input_bounced"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "user_id": self.user_id,
                "reason_zh": self.reason_zh,
                "hint_zh": self.hint_zh,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class UserTaskEvent:
    """Phase 42 A3 (spec 05 Flow 12 / 04-06 §5.10)：「你的任務」釘住 banner。

    非聊天流訊息——後到事件覆蓋前一個 banner；``task_text=None`` 視為清除。
    ``action_kind=confirm`` 時前端按鈕化，且啟用 spec 20 §12.4 短確認白名單。
    ``anchor_note_ids`` 有值時前端連動便條高亮（同 note_highlight 機制）。
    """

    project_id: UUID
    task_text: str | None
    sub_phase: str
    action_kind: str  # chat | note | move | confirm
    anchor_note_ids: list[str] | None = None
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "user_task"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "task_text": self.task_text,
                "sub_phase": self.sub_phase,
                "action_kind": self.action_kind,
                "anchor_note_ids": self.anchor_note_ids,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class NoteHighlightEvent:
    """Phase 42 A3 (spec 04-06 §5.10，#34)：組長指認便條的高亮事件。

    便條色＝作者色、語意不得用顏色表達——指認一律用高亮（搭配內容／作者描述）。
    ``ttl``＝高亮持續秒數，前端到期自動解除。
    """

    project_id: UUID
    note_ids: list[str]
    by_seat: str
    ttl: int
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "note_highlight"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "note_ids": self.note_ids,
                "by_seat": self.by_seat,
                "ttl": self.ttl,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class AgentTypingEvent:
    """Phase 42 D2 (spec 06 §3.1 / 04-06 §5.10 / 13 §6.4，WP9 #9)：AI 發話前置指示。

    AI（supervisor／crew）在「決定要發話／操作白板」與「實際送出」之間發
    ``state="start"``、輸出落地（或放棄）發 ``state="stop"``，消除 AI 訊息
    憑空蹦出的突兀感。``kind="chat"`` → 前端「{display_name} 正在輸入…」；
    ``kind="canvas"`` →「{display_name} 正在白板上寫…」。payload 無 ``chat_id``
    → WS forwarder 走 None 分支廣播給全房（**僅群組 channel**；個人 channel
    的 DT 教練不發、前端不顯示，見 spec 13 §3.2／§6.4）。
    """

    project_id: UUID
    seat_id: str
    display_name: str
    kind: str  # "chat" | "canvas"
    state: str  # "start" | "stop"
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "agent_typing"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "seat_id": self.seat_id,
                "display_name": self.display_name,
                "kind": self.kind,
                "state": self.state,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class RoomPausedEvent:
    """Phase 42 D5 (G14 / #35, spec 20 §13.3)：全房暫停事件。

    ``reason``＝"llm_down"（LLM 服務中斷 fail-stop）／"teacher"（老師手動）。
    payload 無 ``chat_id`` → WS forwarder 走 None 分支廣播給全房，前端據 reason
    顯示 banner。
    """

    project_id: UUID
    reason: str
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "room_paused"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "reason": self.reason,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class RoomResumedEvent:
    """Phase 42 D5 (G14 / #35, spec 20 §13.4)：全房恢復事件（清 banner）。"""

    project_id: UUID
    timestamp: str = field(default_factory=_now_iso)

    @property
    def type(self) -> str:
        return "room_resumed"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": {
                "project_id": str(self.project_id),
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


AnyEvent = (
    ChatMessageEvent
    | TypingEvent
    | StageChangedEvent
    | MicroPhaseChangedEvent
    | SeatChangedEvent
    | SystemMessageEvent
    | ProjectUpdateEvent
    | TurnPolicyChangedEvent
    | CueEvent
    | TurnStateEvent
    | CueTimeoutEvent
    | CueAbandonedEvent
    | WaitingForHumanEvent
    | InputBouncedEvent
    | UserTaskEvent
    | NoteHighlightEvent
    | AgentTypingEvent
    | RoomPausedEvent
    | RoomResumedEvent
)
