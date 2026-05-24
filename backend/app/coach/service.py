"""DT 教練 service：背景任務寫 DB + 廣播個人聊天訊息（Phase 20 重寫）。

依 specs/13-personal-chat.md §7：
  - ``reply_to_personal_message`` 由 router / WS handler 用
    ``asyncio.create_task`` 排程；本 service 不做 RBAC 與 user_message
    持久化（那兩件事在觸發點已完成）。
  - 失敗時寫一筆 ``sender_type='system'`` 錯誤訊息並廣播，前端顯示提示。
  - **不可** 使用 router 傳入的 session（已關閉）；必須自建新的
    ``async_session_factory()`` session。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.chat.chat_id import make_personal_chat_id
from app.chat.repository import MessageRepository
from app.chinese.converter import chinese_converter
from app.coach.canvas_context import build_canvas_topic_summary
from app.coach.context import build_group_topic_summary
from app.coach.prompts import build_messages
from app.coach.time_context import build_time_budget_summary
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent
from app.llm.factory import LLMProviderFactory
from sqlalchemy import select

logger = logging.getLogger(__name__)


# 失敗時送回給 user 的 fallback 訊息文字（spec §7.3）。
_COACH_FALLBACK_ERROR_MESSAGE = "[錯誤] DT 教練暫時無法回應，請稍後再試。"

# 個人 channel 取最近幾條訊息作為 LLM context。
_PERSONAL_HISTORY_LIMIT = 10

# DT 教練固定的 sender 識別。
_COACH_SENDER_ID = "dt-coach"
_COACH_SENDER_NAME = "DT 教練"


class DTCoachService:
    """個人聊天教練 service。

    觸發方式：使用者透過 POST /dt-coach/ask 或 WS chat_message（kind=personal）
    送出訊息；router/WS handler 已寫好 user message + publish。本 service 只
    負責「在背景產生 Coach reply 並寫回 DB + 廣播」。

    生命週期注意（spec §7.3）：
      - 背景任務不能使用 request 的 session（已 commit/close）；
      - 一律從 ``async_session_factory()`` 自建 session。
    """

    async def reply_to_personal_message(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        user_display_name: str,
        stage: str,
        micro_phase: str,
        user_message_content: str,
    ) -> None:
        """背景任務：取 context → LLM → OpenCC → 寫 DB + publish。

        - 成功路徑：寫 ``sender_type='ai'`` 一筆 + publish。
        - 失敗路徑：寫 ``sender_type='system'`` 一筆錯誤訊息 + publish。
          （DB 失敗時改僅 publish system_message 給前端顯示 toast。）

        Args:
            project_id: 目標專案。
            user_id: 個人聊天屬主 user。
            user_display_name: 使用者顯示名稱（給 prompt 插值用）。
            stage: 觸發當下的 stage（spec §5.2 由 client 帶入）。
            micro_phase: 觸發當下的 micro phase。
            user_message_content: 使用者剛送出的訊息內容（已寫入 DB；本 service
                會再取一次 personal_history 取得完整對話脈絡）。
        """
        personal_chat_id = make_personal_chat_id(project_id, user_id)
        current_stage = stage  # fallback；若取得 project 會以最新值覆寫。

        try:
            async with async_session_factory() as session:
                # 1) 取 project（為了用最新的 current_stage 寫入訊息）。
                p_result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = p_result.scalar_one_or_none()
                if project is not None:
                    current_stage = project.current_stage

                # 2) 取個人聊天最近 N 條（含本人 + Coach）作為 conversation history。
                repo = MessageRepository(session)
                personal_history = await repo.list_personal(
                    project_id, user_id, limit=_PERSONAL_HISTORY_LIMIT
                )

                # 3) 取 group topic 摘要（≤200 字；spec §7.4，不洩漏逐字訊息）。
                group_summary = await build_group_topic_summary(
                    session, project_id
                )

                # 3b) 取 canvas 摘要（≤300 字；只談分群/密度/卡點，不引用便條紙逐字）。
                canvas_summary = await build_canvas_topic_summary(
                    project_id, micro_phase
                )

                # 3c) 取時間預算摘要（≤120 字；spec 16 §6.5.6）。
                time_budget = await build_time_budget_summary(
                    project_id, micro_phase
                )

                # 4) 組 messages。注意：personal_history 已含「使用者剛送出的訊息」，
                # 因此 build_messages 內把它當作最後一筆 user turn 即可；為了
                # 避免重複，我們把 history 截到「不含本輪訊息」再加最末 user。
                history_for_prompt = self._trim_trailing_user_turn(
                    personal_history, user_message_content
                )
                messages = build_messages(
                    stage=stage,
                    micro_phase=micro_phase,
                    user_display_name=user_display_name,
                    group_summary_text=group_summary,
                    canvas_summary_text=canvas_summary,
                    time_budget_text=time_budget,
                    personal_history=history_for_prompt,
                    current_user_message=user_message_content,
                )

                # 5) 呼叫 LLM（單獨 try/except 以區分 LLM 失敗與 DB 失敗）。
                try:
                    llm = LLMProviderFactory.get_service()
                    response = await llm.chat_completion(
                        messages=messages,
                        temperature=0.7,
                        max_tokens=512,
                        caller="dt_coach",
                        owning_user_id=user_id,
                        triggered_by_user_id=user_id,
                        project_id=project_id,
                    )
                    reply_text = chinese_converter.convert(response.content)
                    sender_type = "ai"
                    content = reply_text
                except Exception as exc:  # noqa: BLE001 — fallback 也要落地。
                    logger.warning(
                        "DT Coach LLM 失敗 project=%s user=%s err=%s",
                        project_id,
                        user_id,
                        exc,
                    )
                    sender_type = "system"
                    content = _COACH_FALLBACK_ERROR_MESSAGE

                # 6) 寫 DB（Coach reply 或 system 錯誤訊息皆 chat_id=personal）。
                msg = Message(
                    project_id=project_id,
                    sender_type=sender_type,
                    sender_id=_COACH_SENDER_ID,
                    sender_name=_COACH_SENDER_NAME,
                    content=content,
                    stage=current_stage,
                    chat_id=personal_chat_id,
                )
                await repo.create(msg)
                await session.commit()

                # 7) Publish ChatMessageEvent（chat_id=personal，forwarder 會
                # RBAC 過濾，只送回該 user 的 socket）。
                event = ChatMessageEvent(
                    project_id=project_id,
                    sender_id=_COACH_SENDER_ID,
                    sender_type=sender_type,
                    sender_name=_COACH_SENDER_NAME,
                    content=content,
                    chat_id=personal_chat_id,
                )
                try:
                    await event_bus.publish(event)
                except Exception as pub_exc:  # noqa: BLE001
                    logger.warning(
                        "DT Coach publish 失敗 project=%s err=%s",
                        project_id,
                        pub_exc,
                    )

        except Exception:
            # DB 失敗（連線、commit 等）：log + 嘗試 publish system fallback。
            logger.exception(
                "DT Coach 背景任務失敗 project=%s user=%s",
                project_id,
                user_id,
            )
            await self._publish_fallback_only(
                project_id=project_id,
                personal_chat_id=personal_chat_id,
            )

    # ------------------------------------------------------------------
    # 內部 helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trim_trailing_user_turn(
        personal_history: list[Message],
        current_user_message: str,
    ) -> list[Message]:
        """若 personal_history 最末一筆已是本輪 user 訊息，移除以避免重複。

        spec §7.2：router/WS handler 會先寫一筆 user message，再排程本背景
        任務。當 background task 啟動並讀 personal channel 時，最末一筆很
        可能就是剛剛那筆 user 訊息。``build_messages`` 會在最末追加當前
        user content，因此這裡先 trim 掉以免 LLM 看到重複。
        """
        if not personal_history:
            return []
        last = personal_history[-1]
        if (
            last.sender_type == "human"
            and last.content == current_user_message
        ):
            return personal_history[:-1]
        return list(personal_history)

    @staticmethod
    async def _publish_fallback_only(
        *, project_id: UUID, personal_chat_id: str
    ) -> None:
        """DB 寫入失敗時，至少把錯誤訊息 publish 出去讓前端顯示 toast。

        不寫 DB，只送 chat_message event；payload 為 sender_type='system'。
        """
        event = ChatMessageEvent(
            project_id=project_id,
            sender_id=_COACH_SENDER_ID,
            sender_type="system",
            sender_name=_COACH_SENDER_NAME,
            content=_COACH_FALLBACK_ERROR_MESSAGE,
            chat_id=personal_chat_id,
        )
        try:
            await event_bus.publish(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DT Coach fallback publish 也失敗 project=%s err=%s",
                project_id,
                exc,
            )


# Module-level singleton（無共用可變狀態，可安全跨 request 重用）。
dt_coach_service = DTCoachService()
