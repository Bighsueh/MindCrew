"""WebSocket forwarder RBAC 純函數測試。

涵蓋 spec 13-personal-chat.md §6.2 / §8.4 的 ``should_deliver`` 表格：
non-chat（None） / group / personal-self / personal-other / 未知格式
與缺 owner 等邊界。

對應 spec：
  - `specs/13-personal-chat.md` §6.2 ``should_deliver``
  - `specs/13-personal-chat.md` §8.4 WS forward RBAC
  - `prompts/phases/phase-20.md` Step 17.5
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.chat.chat_id import (
    PERSONAL_INFIX,
    make_group_chat_id,
    make_personal_chat_id,
)
from app.ws.delivery_filter import should_deliver_chat_event


# ---------- 固定樣本 ----------

PROJECT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
USER_A = "00000000-0000-0000-0000-0000000000b2"
USER_B = "00000000-0000-0000-0000-0000000000c3"


# ---------- 必須廣播（True 表格）----------


@pytest.mark.unit
def test_should_deliver_none_chat_id_returns_true() -> None:
    """non-chat event payload 沒有 chat_id（None）→ 全送。

    對應 spec 13 §6.2：seat_changed / stage_changed / system_message
    等 event 走 None 分支。
    """
    assert should_deliver_chat_event(None, USER_A) is True


@pytest.mark.unit
def test_should_deliver_group_alias_returns_true() -> None:
    """``{pid}:group`` chat_id → 群組訊息全送。"""
    chat_id = make_group_chat_id(PROJECT_ID)
    assert should_deliver_chat_event(chat_id, USER_A) is True


@pytest.mark.unit
def test_should_deliver_personal_self_returns_true() -> None:
    """``{pid}:personal:<self>`` → 屬主自己應收到。"""
    chat_id = make_personal_chat_id(PROJECT_ID, USER_A)
    assert should_deliver_chat_event(chat_id, USER_A) is True


@pytest.mark.unit
def test_should_deliver_group_for_any_viewer() -> None:
    """group chat 對任何 viewer 都應該送（含 user_id 為非 UUID 字串的場景）。"""
    chat_id = make_group_chat_id(PROJECT_ID)
    assert should_deliver_chat_event(chat_id, "anyone") is True


# ---------- 必須丟棄（False 表格）----------


@pytest.mark.unit
def test_should_deliver_personal_other_returns_false() -> None:
    """``{pid}:personal:<other>`` → 不可送給非屬主。"""
    chat_id = make_personal_chat_id(PROJECT_ID, USER_B)
    assert should_deliver_chat_event(chat_id, USER_A) is False


@pytest.mark.unit
def test_should_deliver_unknown_format_returns_false() -> None:
    """完全無法辨識的字串 → 安全預設不送。"""
    assert should_deliver_chat_event("garbage", USER_A) is False


@pytest.mark.unit
def test_should_deliver_personal_missing_owner_returns_false() -> None:
    """``{pid}:personal:``（中段標記後無 owner）→ 視為非法、不送。"""
    bad = f"{PROJECT_ID}{PERSONAL_INFIX}"
    assert should_deliver_chat_event(bad, USER_A) is False


@pytest.mark.unit
def test_should_deliver_empty_string_returns_false() -> None:
    """空字串非合法 chat_id → 不送。"""
    # 空字串不是 None，會走到「未知格式」分支。
    assert should_deliver_chat_event("", USER_A) is False


# ---------- 交叉驗證 ----------


@pytest.mark.unit
def test_should_deliver_personal_self_vs_other_symmetry() -> None:
    """同一條 personal chat_id 對 A 應送、對 B 不送。"""
    chat_id = make_personal_chat_id(PROJECT_ID, USER_A)
    assert should_deliver_chat_event(chat_id, USER_A) is True
    assert should_deliver_chat_event(chat_id, USER_B) is False
