"""Chat ID 字串組裝與解析。

格式（對應 frontend/src/lib/chatId.ts 與 specs/13-personal-chat.md §4.3.3）：
  - 群組：``{project_id}:group`` 或 NULL（向下相容）
  - 個人：``{project_id}:personal:{user_id}``

本模組為純函式 helper，所有 RBAC / DB query 收斂於此。
任何 chat_id 字串組裝必須走這裡，禁止 inline f-string 拼接。
"""

from __future__ import annotations

from typing import Literal, Tuple
from uuid import UUID

# ---------- 常數 ----------

#: 群組 chat_id 後綴。
GROUP_SUFFIX: str = ":group"

#: 個人 chat_id 中段標記（前後分別接 project_id 與 user_id）。
PERSONAL_INFIX: str = ":personal:"

#: 「raw」query 參數可接受的別名。
_RAW_GROUP_ALIAS = "group"
_RAW_PERSONAL_ALIAS = "personal"

#: ``normalize_for_query`` 回傳的 kind 字面值。
ChatKind = Literal["group", "personal"]


# ---------- 內部 util ----------


def _to_str(value: str | UUID) -> str:
    """把 UUID 或 str 統一轉成純小寫字串（與 frontend 對齊）。

    UUID 物件 ``str()`` 的結果已是 lower-case dashed 形式，可直接使用。
    """
    if isinstance(value, UUID):
        return str(value)
    return str(value)


# ---------- 組裝 ----------


def make_group_chat_id(project_id: str | UUID) -> str:
    """組出群組 chat_id 字串，格式 ``{project_id}:group``。

    Args:
        project_id: 專案 UUID 或字串。

    Returns:
        例如 ``"dfe...:group"``。
    """
    return f"{_to_str(project_id)}{GROUP_SUFFIX}"


def make_personal_chat_id(project_id: str | UUID, user_id: str | UUID) -> str:
    """組出個人 chat_id 字串，格式 ``{project_id}:personal:{user_id}``。

    Args:
        project_id: 專案 UUID 或字串。
        user_id: 該個人聊天屬主 user 的 UUID 或字串。

    Returns:
        例如 ``"dfe...:personal:9a8..."``。
    """
    return f"{_to_str(project_id)}{PERSONAL_INFIX}{_to_str(user_id)}"


# ---------- 判別 ----------


def is_group(chat_id: str | None) -> bool:
    """判斷是否為群組 chat_id。

    依 spec §4.3.3 與 §6.2 的「向下相容」規則：
      - ``None`` 視為 group（既有未 backfill 的 row）。
      - 以 ``:group`` 結尾視為 group。
      - 其餘皆非 group。
    """
    if chat_id is None:
        return True
    return chat_id.endswith(GROUP_SUFFIX)


def is_personal(chat_id: str | None) -> bool:
    """判斷是否為個人 chat_id。

    必須同時滿足：
      - 非 None
      - 含有 ``:personal:`` 中段標記
      - 中段標記後仍有 user_id 片段（非空字串）

    僅檢查格式，不檢查 user_id 是否合法 UUID（由 RBAC 層另行驗證）。
    """
    if chat_id is None:
        return False
    if PERSONAL_INFIX not in chat_id:
        return False
    owner = personal_owner_of(chat_id)
    return owner is not None and len(owner) > 0


def personal_owner_of(chat_id: str | None) -> str | None:
    """從 personal chat_id 取出屬主 user_id 字串。

    Args:
        chat_id: 完整 chat_id 字串。

    Returns:
        - 若是 personal chat_id → user_id 字串。
        - 若非 personal（含 None、group、未知格式）→ None。
    """
    if chat_id is None:
        return None
    if PERSONAL_INFIX not in chat_id:
        return None
    # 取最後一段，避免未來 chat_id 內含 project_id 出現 ":personal:" 子字串時誤判。
    tail = chat_id.rsplit(PERSONAL_INFIX, 1)[-1]
    if not tail:
        return None
    return tail


# ---------- Query normalization（RBAC 核心）----------


def normalize_for_query(
    raw: str | None,
    project_id: str | UUID,
    current_user_id: str | UUID,
) -> Tuple[ChatKind, str | None]:
    """把 client 傳入的 raw 解析為 (kind, full_chat_id_or_None)。

    依 spec §8.1 RBAC 規則：

    | 輸入 raw                                       | 輸出                                       | 說明                                |
    |-----------------------------------------------|-------------------------------------------|------------------------------------|
    | ``None`` / ``""``                              | ``("group", None)``                       | 預設為 group                         |
    | ``"group"``                                    | ``("group", None)``                       | group 查詢用 NULL OR :group 條件      |
    | ``"{pid}:group"``                              | ``("group", None)``                       | 同上                                |
    | ``"personal"``                                 | ``("personal", "{pid}:personal:{cur}")``  | 屬主隱含為 current_user_id            |
    | ``"{pid}:personal:{cur}"``                     | ``("personal", "{pid}:personal:{cur}")``  | 自己的 personal                      |
    | ``"{pid}:personal:{other}"``（other != cur）    | ``ValueError``                            | 由 router 翻成 403                   |
    | 其他未知格式                                    | ``ValueError``                            | 由 router 翻成 400                   |

    Args:
        raw: 來自 query string 的原始 chat_id 值。
        project_id: 當前 request 目標 project。
        current_user_id: 當前 JWT 主體 user。

    Returns:
        Tuple ``(kind, full_chat_id_or_None)``。
          - ``kind == "group"`` → 第二元素為 ``None``，repository 應用
            ``chat_id IS NULL OR chat_id LIKE '%:group'`` 條件。
          - ``kind == "personal"`` → 第二元素為完整 chat_id 字串，
            repository 應用 ``chat_id = :full`` 精確比對。

    Raises:
        ValueError: raw 指向別人的 personal chat_id（router 翻 403），
            或 raw 為未知格式（router 翻 400）。
    """
    pid = _to_str(project_id)
    cur = _to_str(current_user_id)

    # 預設或別名：group
    if raw is None or raw == "" or raw == _RAW_GROUP_ALIAS:
        return ("group", None)

    # 個人別名：隱含 current_user
    if raw == _RAW_PERSONAL_ALIAS:
        return ("personal", make_personal_chat_id(pid, cur))

    # 完整 group：必須是「本 project 的 group」才接受
    if raw.endswith(GROUP_SUFFIX):
        expected_group = make_group_chat_id(pid)
        if raw == expected_group:
            return ("group", None)
        raise ValueError(
            f"未知 chat_id 格式（group 字串不屬於本專案）：{raw!r}"
        )

    # 完整 personal：必須是「本 project + 本 user」才接受
    if PERSONAL_INFIX in raw:
        # 前綴必須是 ``{pid}:personal:``，避免別 project 的 chat_id 滲入。
        expected_prefix = f"{pid}{PERSONAL_INFIX}"
        if not raw.startswith(expected_prefix):
            raise ValueError(
                f"未知 chat_id 格式（personal 字串不屬於本專案）：{raw!r}"
            )
        owner = personal_owner_of(raw)
        if owner is None or owner == "":
            raise ValueError(f"未知 chat_id 格式（personal 缺 owner）：{raw!r}")
        if owner != cur:
            # spec §8.1：指向別人的 personal → router 翻 403
            raise ValueError(
                f"RBAC 違規：chat_id 指向其他 user 的 personal 聊天：{raw!r}"
            )
        return ("personal", make_personal_chat_id(pid, cur))

    # 其他未知格式
    raise ValueError(f"未知 chat_id 格式：{raw!r}")
