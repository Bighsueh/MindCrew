"""WebSocket forwarder 的純函數 RBAC 過濾器。

依 spec 13-personal-chat.md §6.2 與 §8.4：
forwarder 在送 event 給某 viewer 之前，必須先用 ``chat_id`` 判斷是否
應該送出。本模組僅看 chat_id，不看 event type；non-chat event
（payload 沒有 chat_id）視為 ``None`` → 預設廣播。

設計理由：
1. 純函數、無 I/O，可大量單元測試。
2. 收斂 RBAC 規則到單一檔案，避免散落在 chat_ws.py。
3. 配合 ``app.chat.chat_id`` helper，前後端共享一份 chat_id 契約。
"""

from __future__ import annotations

from app.chat.chat_id import GROUP_SUFFIX, PERSONAL_INFIX, personal_owner_of


def should_deliver_chat_event(
    chat_id: str | None,
    viewer_user_id: str,
) -> bool:
    """判斷是否應把帶有 ``chat_id`` 的 event 送給該 viewer。

    規則（與 spec 13 §6.2 ``should_deliver`` 一致）：

    +----------------------------------------+-----------------+
    | chat_id 形式                            | 回傳             |
    +========================================+=================+
    | ``None``                                | ``True``        |
    | ``"...:group"``                         | ``True``        |
    | ``"...:personal:<viewer>"``             | ``True``        |
    | ``"...:personal:<other>"``              | ``False``       |
    | 其他未知格式                             | ``False``       |
    +----------------------------------------+-----------------+

    Args:
        chat_id: event payload 中的 chat_id 欄位（可能 ``None``，
            代表 non-chat event 或向下相容的舊 row）。
        viewer_user_id: 該 WS 連線所屬 user 的字串 id。

    Returns:
        ``True`` 表示 forwarder 應呼叫 ``ws.send_json``；
        ``False`` 表示靜默丟棄該訊息。

    Notes:
        本函式**只看 chat_id**，不檢查 event type。所以
        ``seat_changed`` / ``stage_changed`` / ``system_message`` 等
        payload 沒有 chat_id 的 event 會走 ``None`` 分支 → ``True``，
        等同對全 project 廣播。這是預期行為。
    """
    # 未指明 chat_id（含 non-chat event 與舊 row）→ 視為 group，全送。
    if chat_id is None:
        return True

    # 群組訊息：以 :group 結尾即可。
    if chat_id.endswith(GROUP_SUFFIX):
        return True

    # 個人訊息：必須是 viewer 自己的。
    if PERSONAL_INFIX in chat_id:
        owner = personal_owner_of(chat_id)
        if owner is None:
            # 缺 owner（``...:personal:``）視為不合法 → 不送。
            return False
        return owner == str(viewer_user_id)

    # 未知格式 → 安全預設：不送。
    return False
