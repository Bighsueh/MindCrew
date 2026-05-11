"""ChatMessageEvent chat_id 欄位 + handle_chat_message Redis cache 隔離測試。

對應 spec/13-personal-chat.md §6.3 與 §9.2、phase-20 Step 17.5 / 17.7。

驗證重點：
1. ``ChatMessageEvent`` 不傳 ``chat_id`` 仍能建構（向下相容），``to_dict()`` 內
   ``payload.chat_id`` 為 ``None``。
2. 傳 group / personal chat_id 時，``to_dict()`` 正確帶出該字串。
3. ``handle_chat_message`` 收到 personal chat_id → 不寫 Redis chat cache，
   只觸發 conversation state；group / None → 維持既有寫入路徑。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.chat.chat_id import make_group_chat_id, make_personal_chat_id
from app.events.handlers import handle_chat_message
from app.events.types import ChatMessageEvent


# ---------- ChatMessageEvent dataclass ----------


def test_chat_message_event_default_chat_id_is_none():
    """不傳 chat_id 時，預設為 None（向下相容既有 caller）。"""
    pid = uuid4()
    event = ChatMessageEvent(
        project_id=pid,
        sender_id="user-1",
        sender_type="human",
        sender_name="Alice",
        content="hello",
    )

    assert event.chat_id is None
    payload = event.to_dict()["payload"]
    assert payload["chat_id"] is None
    # 既有欄位 100% 保留
    assert payload["sender_id"] == "user-1"
    assert payload["sender_type"] == "human"
    assert payload["sender_name"] == "Alice"
    assert payload["content"] == "hello"


def test_chat_message_event_group_chat_id_propagates():
    """傳入完整 group chat_id 時，payload 帶出該字串。"""
    pid = uuid4()
    group_id = make_group_chat_id(pid)

    event = ChatMessageEvent(
        project_id=pid,
        sender_id="user-2",
        sender_type="human",
        sender_name="Bob",
        content="團隊訊息",
        chat_id=group_id,
    )

    assert event.chat_id == group_id
    assert event.to_dict()["payload"]["chat_id"] == group_id


def test_chat_message_event_personal_chat_id_propagates():
    """傳入 personal chat_id 時，payload 帶出該字串以利 WS forwarder RBAC 過濾。"""
    pid = uuid4()
    uid = uuid4()
    personal_id = make_personal_chat_id(pid, uid)

    event = ChatMessageEvent(
        project_id=pid,
        sender_id=str(uid),
        sender_type="human",
        sender_name="Carol",
        content="我有個困惑",
        chat_id=personal_id,
    )

    assert event.chat_id == personal_id
    assert event.to_dict()["payload"]["chat_id"] == personal_id


def test_chat_message_event_to_dict_event_type():
    """to_dict() 的 type 欄位固定為 ``chat_message``。"""
    event = ChatMessageEvent(
        project_id=uuid4(),
        sender_id="x",
        sender_type="human",
        sender_name="X",
        content="c",
    )
    assert event.to_dict()["type"] == "chat_message"


# ---------- handle_chat_message Redis cache 隔離 ----------


@pytest.mark.asyncio
async def test_handle_chat_message_writes_redis_for_group_chat_id():
    """group chat_id（含完整 ``{pid}:group``）→ 寫入 Redis chat cache。"""
    pid = uuid4()
    redis_mock = AsyncMock()
    redis_mock.rpush = AsyncMock()
    redis_mock.ltrim = AsyncMock()
    redis_mock.set = AsyncMock()
    redis_mock.aclose = AsyncMock()

    with patch(
        "redis.asyncio.from_url", MagicMock(return_value=redis_mock)
    ), patch(
        "app.agents.conversation_state.ConversationStateTracker"
    ) as tracker_cls, patch(
        "app.agents.utils.load_seat_roles", AsyncMock(return_value={})
    ):
        tracker_inst = tracker_cls.return_value
        tracker_inst.update_on_message = AsyncMock()

        await handle_chat_message(
            project_id=pid,
            sender_id="u1",
            content="group msg",
            sender_name="Alice",
            sender_type="human",
            chat_id=make_group_chat_id(pid),
        )

    # group 訊息：rpush 必須被呼叫
    redis_mock.rpush.assert_awaited_once()
    redis_mock.ltrim.assert_awaited_once()
    redis_mock.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_chat_message_writes_redis_for_none_chat_id():
    """None chat_id（向下相容）→ 仍寫入 Redis chat cache。"""
    pid = uuid4()
    redis_mock = AsyncMock()
    redis_mock.rpush = AsyncMock()
    redis_mock.ltrim = AsyncMock()
    redis_mock.set = AsyncMock()
    redis_mock.aclose = AsyncMock()

    with patch(
        "redis.asyncio.from_url", MagicMock(return_value=redis_mock)
    ), patch(
        "app.agents.conversation_state.ConversationStateTracker"
    ) as tracker_cls, patch(
        "app.agents.utils.load_seat_roles", AsyncMock(return_value={})
    ):
        tracker_cls.return_value.update_on_message = AsyncMock()

        await handle_chat_message(
            project_id=pid,
            sender_id="u1",
            content="legacy msg",
            sender_name="Alice",
            sender_type="human",
            # 不傳 chat_id（既有 caller 路徑）
        )

    redis_mock.rpush.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_chat_message_skips_redis_for_personal_chat_id():
    """personal chat_id → **不**寫 Redis chat cache（spec §9.2）。"""
    pid = uuid4()
    uid = uuid4()
    redis_from_url = MagicMock()

    with patch(
        "redis.asyncio.from_url", redis_from_url
    ), patch(
        "app.agents.conversation_state.ConversationStateTracker"
    ) as tracker_cls, patch(
        "app.agents.utils.load_seat_roles", AsyncMock(return_value={})
    ):
        tracker_inst = tracker_cls.return_value
        tracker_inst.update_on_message = AsyncMock()

        await handle_chat_message(
            project_id=pid,
            sender_id=str(uid),
            content="個人訊息",
            sender_name="Carol",
            sender_type="human",
            chat_id=make_personal_chat_id(pid, uid),
        )

    # 關鍵：personal 訊息**完全不**呼叫 Redis from_url
    redis_from_url.assert_not_called()
    # conversation state 仍然要更新（屬該 user 自己的對話狀態）
    tracker_inst.update_on_message.assert_awaited_once()
