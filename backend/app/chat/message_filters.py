"""Message query 共用 filter。

依 specs/13-personal-chat.md §4.4 與 §9.1，所有「禁止看到個人訊息」的
查詢場景（agent context_buffer、teacher dashboard 統計與紀錄等）必須統一透過
``group_only_filter()`` 加入 where 條件，避免散落各處
重複寫 ``chat_id IS NULL OR chat_id LIKE '%:group'`` 拼接字串、導致
typo 或漏改造成個人訊息洩漏。

本模組為 thin helper 模組，僅回傳 SQLAlchemy where 條件，不直接執行 query。
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.chat.chat_id import GROUP_SUFFIX
from app.db.models.message import Message


def group_only_filter() -> ColumnElement[bool]:
    """回傳「只看 group 訊息」的 SQLAlchemy where 條件。

    語意對應 specs/13-personal-chat.md §4.3.3 的「向下相容」規則：
      - ``chat_id IS NULL``：既有 Phase 16 之前未 backfill 的 row，視為 group。
      - ``chat_id LIKE '%:group'``：Phase 20 之後新寫入的 group 訊息。

    凡是禁止看到個人訊息的查詢，都應 ``.where(group_only_filter())`` 套上本條件。

    Returns:
        SQLAlchemy ColumnElement，可直接傳入 ``select(...).where(...)``。
    """
    return or_(
        Message.chat_id.is_(None),
        Message.chat_id.like(f"%{GROUP_SUFFIX}"),
    )
