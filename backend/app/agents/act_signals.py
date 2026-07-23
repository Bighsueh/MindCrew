"""使用者導向訊號 action handlers（Phase 42 A3，WP7）。

兩個 supervisor-only action（act.py dispatch 過來）：
- `set_user_task`：組長對使用者發要求時同步的任務提示（spec 04-03 §2.3.2.1 守則 8
  ／§3.0.4）→ 後端補 sub_phase、publish `user_task` WS 事件＋寫 user_task_state
  （confirm 白名單權威來源，spec 20 §12.4）。`task_text=None` 或空字串＝清除 banner。
- `note_highlight`：組長指認便條（spec 04-03 §3.0.7，#34 不可用顏色）→ publish
  `note_highlight` WS 事件，前端高亮、ttl 到期自動退場。

依 A1 act_progression.py 先例獨立成模組（act.py 不再增肥）。全部 best-effort：
事件失敗不擋組長的聊天輸出。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.agents.user_task_state import VALID_ACTION_KINDS

logger = logging.getLogger(__name__)

# 高亮持續秒數（spec 未量化；A3 裁定 12s ≈ 讀一句組長訊息＋找到便條的時間，
# 記錄於 progress.md；前端到期自動退場）。
NOTE_HIGHLIGHT_TTL_SECONDS = 12

_MAX_HIGHLIGHT_IDS = 8  # 防 LLM 一次圈整面牆


async def execute_set_user_task(
    *, project_id: UUID, action: dict, sub_phase: str | None
) -> None:
    """處理 set_user_task action：驗欄位 → 寫狀態 → publish user_task 事件。"""
    raw_text = action.get("task_text")
    task_text = str(raw_text).strip() if raw_text is not None else None
    if task_text == "":
        task_text = None  # 空字串視同清除

    action_kind = str(action.get("action_kind") or "chat").strip().lower()
    if action_kind not in VALID_ACTION_KINDS:
        action_kind = "chat"

    anchor_raw = action.get("anchor_note_ids")
    anchor_note_ids = (
        [str(n) for n in anchor_raw if n][:_MAX_HIGHLIGHT_IDS]
        if isinstance(anchor_raw, list)
        else None
    ) or None

    effective_sub_phase = (sub_phase or "").strip()

    from app.agents import user_task_state

    await user_task_state.set_current(
        project_id,
        task_text=task_text,
        sub_phase=effective_sub_phase,
        action_kind=action_kind,
    )

    try:
        from app.events.bus import event_bus
        from app.events.types import UserTaskEvent

        await event_bus.publish(
            UserTaskEvent(
                project_id=project_id,
                task_text=task_text,
                sub_phase=effective_sub_phase,
                action_kind=action_kind,
                anchor_note_ids=anchor_note_ids,
            )
        )
    except Exception:
        logger.debug("publish user_task failed project=%s", project_id, exc_info=True)


async def execute_note_highlight(
    *, project_id: UUID, action: dict, seat_role: str
) -> None:
    """處理 note_highlight action：過濾 note_ids → publish note_highlight 事件。

    id 真偽不在此驗（前端對不上的 id 直接忽略，與 cites 寫入過濾同精神）。
    """
    raw_ids = action.get("note_ids")
    if not isinstance(raw_ids, list):
        return
    note_ids = [str(n).strip() for n in raw_ids if n and str(n).strip()]
    note_ids = note_ids[:_MAX_HIGHLIGHT_IDS]
    if not note_ids:
        return

    try:
        from app.events.bus import event_bus
        from app.events.types import NoteHighlightEvent

        await event_bus.publish(
            NoteHighlightEvent(
                project_id=project_id,
                note_ids=note_ids,
                by_seat=seat_role,
                ttl=NOTE_HIGHLIGHT_TTL_SECONDS,
            )
        )
    except Exception:
        logger.debug("publish note_highlight failed project=%s", project_id, exc_info=True)


async def emit_agent_typing(
    *,
    project_id: UUID,
    seat_id: str,
    display_name: str,
    kind: str,
    state: str,
) -> None:
    """publish `agent_typing` 事件（Phase 42 D2，WP9 #9；spec 06 §3.1）。

    `kind∈{chat,canvas}`、`state∈{start,stop}`。AI 於 think→act 之間發 start、
    輸出落地（或放棄）發 stop；payload 無 `chat_id` → 群組 channel 廣播。
    best-effort：typing 事件失敗絕不擋 agent 的真正輸出（act.py 以 try/finally 包覆）。
    """
    try:
        from app.events.bus import event_bus
        from app.events.types import AgentTypingEvent

        await event_bus.publish(
            AgentTypingEvent(
                project_id=project_id,
                seat_id=seat_id,
                display_name=display_name,
                kind=kind,
                state=state,
            )
        )
    except Exception:
        logger.debug(
            "publish agent_typing failed project=%s seat=%s kind=%s state=%s",
            project_id,
            seat_id,
            kind,
            state,
            exc_info=True,
        )
