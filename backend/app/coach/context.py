"""DT 教練的 context builder：產生「團隊群組摘要」供 prompt 插值。
  - **絕對不可** 把 group raw messages 直接餵給 Coach LLM，否則 Coach
    可能引用某句具體的話打破 RBAC（Coach 應該只「知道大方向」，不該
    引用具體訊息逐字回覆）。
  - 本模組僅回傳「總長度限 200 字內」的摘要文字。
  - 取訊息**強制**透過 ``MessageRepository.list_for_agents``——只回 group
    + 向下相容 NULL，絕不會混入任何 personal 訊息（spec §9.1）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.repository import MessageRepository

logger = logging.getLogger(__name__)


#: 摘要總長度上限（中文字元數）。超過會 truncate 並以「…」結尾。
_SUMMARY_MAX_CHARS = 200

#: 取最近幾條 group 訊息來組摘要。
_SUMMARY_RECENT_LIMIT = 5

#: 單則訊息在摘要中最多保留幾個中文字（避免單一長訊息吃掉整個摘要）。
_PER_MESSAGE_MAX_CHARS = 40


def _truncate(text: str, limit: int) -> str:
    """把 ``text`` 截至 ``limit`` 個字元，超過時補上「…」。"""
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)] + "…"


async def build_group_topic_summary(
    session: AsyncSession,
    project_id: UUID,
) -> str:
    """產生團隊群組摘要文字（≤ 200 字）供 DT 教練 prompt 插值。

    步驟：
      1. 透過 ``MessageRepository.list_for_agents`` 取最近 ``_SUMMARY_RECENT_LIMIT``
         條 group 訊息——同時保證**不**會回到任何 personal 訊息。
      2. 對每條訊息只取 ``sender_name: content_前幾字`` 的精簡格式。
      3. 串接後再 truncate 到 ``_SUMMARY_MAX_CHARS`` 為止。

    Args:
        session: 已開啟的 AsyncSession（caller 負責生命週期）。
        project_id: 目標專案。

    Returns:
        摘要字串；若無 group 訊息或讀取失敗則回傳空字串（由 prompts 自行
        替換為「（暫無）」）。
    """
    try:
        repo = MessageRepository(session)
        messages = await repo.list_for_agents(
            project_id, limit=_SUMMARY_RECENT_LIMIT
        )
    except Exception as exc:  # noqa: BLE001 — 摘要失敗不該擋住 Coach 回覆。
        logger.warning(
            "build_group_topic_summary 取訊息失敗 project=%s err=%s",
            project_id,
            exc,
        )
        return ""

    if not messages:
        return ""

    lines: list[str] = []
    for msg in messages:
        if not msg.content:
            continue
        body = _truncate(msg.content, _PER_MESSAGE_MAX_CHARS)
        # 用「-」前綴 + sender_name 標示；不引用 sender_id 細節。
        lines.append(f"- {msg.sender_name}：{body}")

    if not lines:
        return ""

    summary = "\n".join(lines)
    return _truncate(summary, _SUMMARY_MAX_CHARS)
