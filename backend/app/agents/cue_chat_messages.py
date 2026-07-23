"""Phase 28 B7：cue retry / abandon 階段的模板化 chat 訊息。

從 cue_timeout_watcher 拆出，遵守 500 行限制與單一職責——watcher 負責
計時 state machine、本檔負責訊息措辭與 chat publish。

未來可升級為 LLM-generated 訊息（讓 supervisor LLM 動態生成措辭），
本檔提供 MVP 模板版本。
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB lookup helper
# ---------------------------------------------------------------------------


async def resolve_seat_display_name(
    project_id: UUID, seat_role: str
) -> str:
    """撈該席位的顯示名稱；失敗 fallback 為 seat_role 本身。

    `Seat` 沒有 `display_name` 欄位（修正前查它會永遠走 except → 回 seat_role，
    導致 cue 提醒把學員顯示成「crew_1」而非真名）。正確來源：
      - 人類席位（有 user_id）→ `User.display_name`
      - AI 席位 → `seat.persona["name"]`
    與 supervisor 在群組 chat 點名時用的名稱（人類帳號 display_name）一致。
    """
    try:
        from sqlalchemy import select

        from app.db.models.seat import Seat
        from app.db.models.user import User
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            seat = (
                await session.execute(
                    select(Seat).where(
                        Seat.project_id == project_id,
                        Seat.seat_role == seat_role,
                    )
                )
            ).scalar_one_or_none()
            if seat is None:
                return seat_role
            if seat.user_id is not None:
                name = (
                    await session.execute(
                        select(User.display_name).where(User.id == seat.user_id)
                    )
                ).scalar_one_or_none()
                if name:
                    return name
            persona = seat.persona if isinstance(seat.persona, dict) else None
            if persona and persona.get("name"):
                return str(persona["name"])
            return seat_role
    except Exception:
        logger.debug("resolve_seat_display_name failed", exc_info=True)
        return seat_role


# ---------------------------------------------------------------------------
# Chat publishing
# ---------------------------------------------------------------------------


async def _publish_chat_message(
    *,
    project_id: UUID,
    sender_seat_role: str,
    content: str,
) -> None:
    """以指定 seat 名義 publish 一筆群組 chat message。"""
    try:
        from app.events.bus import event_bus
        from app.events.types import ChatMessageEvent

        sender_name = await resolve_seat_display_name(project_id, sender_seat_role)
        await event_bus.publish(
            ChatMessageEvent(
                project_id=project_id,
                sender_id=f"agent_{sender_seat_role}",
                sender_type="ai",
                sender_name=sender_name,
                content=content,
                chat_id=None,  # group chat
            )
        )
    except Exception:
        logger.debug("_publish_chat_message failed", exc_info=True)


# ---------------------------------------------------------------------------
# B7 templates
# ---------------------------------------------------------------------------


def build_reminder_content(
    *,
    human_name: str,
    retry_count: int,
    max_retries: int,
    elapsed_minutes: int,
) -> str:
    """retry cycle 內 supervisor reminder 模板。

    措辭隨 retry 次數遞進：早期偏鼓勵、晚期給台階下。
    """
    attempt_num = retry_count + 2  # 第 2 / 3 / ... 次提醒（第 1 次是初始 cue）
    if retry_count == 0:
        return (
            f"@{human_name},等你回應 {elapsed_minutes} 分鐘了,"
            f"沒事的,慢慢想就好。想說點什麼或先 pass 一下都可以。"
        )
    if retry_count >= max_retries - 1:
        return (
            f"@{human_name},這是最後一次邀請({attempt_num}/{max_retries + 1})。"
            f"如果不方便就先 pass,我會接手話題不用緊張。"
        )
    return (
        f"@{human_name},再邀請一次({attempt_num}/{max_retries + 1})。"
        f"你的想法很重要;不方便回應的話 pass 也完全 OK。"
    )


def build_pivot_content(*, human_name: str, total_attempts: int) -> str:
    """abandon 後 supervisor pivot 模板（多人房；單人房改走 build_awaiting_hold_content）。"""
    return (
        f"{human_name} 暫時沒有回應(已嘗試 {total_attempts} 次),"
        f"我們先繼續往下走,等他/她有想法時隨時可以加入。"
    )


def build_awaiting_hold_content(*, human_name: str) -> str:
    """Phase 43（spec 20 §3/§11.7）：單人房 cue 逾時 → 改「在這裡等你」休眠模板，
    取代 build_pivot_content 的「先繼續往下走」。措辭溫和、強調不推進、回來原地續跑。"""
    return (
        f"{human_name},我先在這裡等你,不急——"
        f"活動會先暫停,等你準備好回個訊息,我們就從這裡繼續。"
    )


async def publish_reminder_chat(
    *,
    project_id: UUID,
    from_seat_role: str,
    human_name: str,
    retry_count: int,
    max_retries: int,
    elapsed_minutes: int,
) -> None:
    """retry cycle 內 supervisor 重發 reminder。"""
    content = build_reminder_content(
        human_name=human_name,
        retry_count=retry_count,
        max_retries=max_retries,
        elapsed_minutes=elapsed_minutes,
    )
    await _publish_chat_message(
        project_id=project_id,
        sender_seat_role=from_seat_role,
        content=content,
    )


async def publish_pivot_chat(
    *,
    project_id: UUID,
    from_seat_role: str,
    human_name: str,
    total_attempts: int,
) -> None:
    """abandon 後 supervisor pivot 訊息。"""
    content = build_pivot_content(
        human_name=human_name, total_attempts=total_attempts
    )
    await _publish_chat_message(
        project_id=project_id,
        sender_seat_role=from_seat_role,
        content=content,
    )


async def publish_awaiting_hold_chat(
    *,
    project_id: UUID,
    from_seat_role: str,
    human_name: str,
) -> None:
    """Phase 43：單人房 cue 逾時 → supervisor 貼「在這裡等你」訊息（全房休眠前）。"""
    content = build_awaiting_hold_content(human_name=human_name)
    await _publish_chat_message(
        project_id=project_id,
        sender_seat_role=from_seat_role,
        content=content,
    )
