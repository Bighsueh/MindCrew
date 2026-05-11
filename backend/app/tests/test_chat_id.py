"""``app.chat.chat_id`` 的 pytest 單元測試。

涵蓋 spec 13-personal-chat §4.3.3（格式）+ §8.1（RBAC）邊界。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.chat.chat_id import (
    GROUP_SUFFIX,
    PERSONAL_INFIX,
    is_group,
    is_personal,
    make_group_chat_id,
    make_personal_chat_id,
    normalize_for_query,
    personal_owner_of,
)


# ---------- 固定樣本 ----------

PROJECT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
USER_ID = UUID("00000000-0000-0000-0000-0000000000b2")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-0000000000c3")


# ---------- make_* ----------


@pytest.mark.unit
def test_make_group_chat_id_format_with_uuid() -> None:
    """``make_group_chat_id`` 對 UUID 輸入應輸出 ``{uuid}:group``。"""
    result = make_group_chat_id(PROJECT_ID)
    assert result == f"{PROJECT_ID}{GROUP_SUFFIX}"
    assert result.endswith(":group")


@pytest.mark.unit
def test_make_group_chat_id_format_with_str() -> None:
    """``make_group_chat_id`` 接受 str project_id。"""
    result = make_group_chat_id("abc-123")
    assert result == "abc-123:group"


@pytest.mark.unit
def test_make_personal_chat_id_format_with_uuid() -> None:
    """``make_personal_chat_id`` 對兩個 UUID 應輸出 ``{pid}:personal:{uid}``。"""
    result = make_personal_chat_id(PROJECT_ID, USER_ID)
    assert result == f"{PROJECT_ID}{PERSONAL_INFIX}{USER_ID}"


@pytest.mark.unit
def test_make_personal_chat_id_format_with_str() -> None:
    """``make_personal_chat_id`` 接受 str 輸入。"""
    result = make_personal_chat_id("pid", "uid")
    assert result == "pid:personal:uid"


# ---------- is_group / is_personal ----------


@pytest.mark.unit
def test_is_group_handles_none() -> None:
    """None 視為 group（向下相容既有 row）。"""
    assert is_group(None) is True
    assert is_personal(None) is False


@pytest.mark.unit
def test_is_group_handles_suffix() -> None:
    """``{pid}:group`` 視為 group。"""
    chat_id = make_group_chat_id(PROJECT_ID)
    assert is_group(chat_id) is True
    assert is_personal(chat_id) is False


@pytest.mark.unit
def test_is_personal_handles_personal_string() -> None:
    """``{pid}:personal:{uid}`` 視為 personal、不視為 group。"""
    chat_id = make_personal_chat_id(PROJECT_ID, USER_ID)
    assert is_personal(chat_id) is True
    assert is_group(chat_id) is False


@pytest.mark.unit
def test_is_personal_rejects_dirty_strings() -> None:
    """缺 owner / 缺中段標記 / 空字串皆非 personal。"""
    assert is_personal("") is False
    assert is_personal("foobar") is False
    assert is_personal(f"{PROJECT_ID}{PERSONAL_INFIX}") is False  # 缺 owner
    assert is_personal(f"{PROJECT_ID}:group") is False


# ---------- personal_owner_of ----------


@pytest.mark.unit
def test_personal_owner_of_returns_user_id() -> None:
    """合法 personal chat_id 應回傳 owner 字串。"""
    chat_id = make_personal_chat_id(PROJECT_ID, USER_ID)
    assert personal_owner_of(chat_id) == str(USER_ID)


@pytest.mark.unit
def test_personal_owner_of_non_personal_returns_none() -> None:
    """group / None / 未知格式皆回 None。"""
    assert personal_owner_of(None) is None
    assert personal_owner_of(make_group_chat_id(PROJECT_ID)) is None
    assert personal_owner_of("garbage") is None


@pytest.mark.unit
def test_personal_owner_of_empty_owner_returns_none() -> None:
    """``{pid}:personal:`` 結尾無 owner 應回 None。"""
    assert personal_owner_of(f"{PROJECT_ID}{PERSONAL_INFIX}") is None


# ---------- normalize_for_query：合法路徑 ----------


@pytest.mark.unit
def test_normalize_none_defaults_to_group() -> None:
    """raw=None → ('group', None)。"""
    kind, full = normalize_for_query(None, PROJECT_ID, USER_ID)
    assert kind == "group"
    assert full is None


@pytest.mark.unit
def test_normalize_empty_string_defaults_to_group() -> None:
    """raw='' → ('group', None)。"""
    kind, full = normalize_for_query("", PROJECT_ID, USER_ID)
    assert kind == "group"
    assert full is None


@pytest.mark.unit
def test_normalize_group_alias() -> None:
    """raw='group' → ('group', None)。"""
    kind, full = normalize_for_query("group", PROJECT_ID, USER_ID)
    assert kind == "group"
    assert full is None


@pytest.mark.unit
def test_normalize_full_group_string() -> None:
    """raw='{pid}:group' → ('group', None)。"""
    raw = make_group_chat_id(PROJECT_ID)
    kind, full = normalize_for_query(raw, PROJECT_ID, USER_ID)
    assert kind == "group"
    assert full is None


@pytest.mark.unit
def test_normalize_personal_alias() -> None:
    """raw='personal' → ('personal', '{pid}:personal:{cur}')。"""
    kind, full = normalize_for_query("personal", PROJECT_ID, USER_ID)
    assert kind == "personal"
    assert full == make_personal_chat_id(PROJECT_ID, USER_ID)


@pytest.mark.unit
def test_normalize_full_personal_self() -> None:
    """raw 為自己的完整 personal → ('personal', 同字串)。"""
    raw = make_personal_chat_id(PROJECT_ID, USER_ID)
    kind, full = normalize_for_query(raw, PROJECT_ID, USER_ID)
    assert kind == "personal"
    assert full == raw


# ---------- normalize_for_query：違規路徑 ----------


@pytest.mark.unit
def test_normalize_personal_of_other_user_raises() -> None:
    """raw 指向別人的 personal → ValueError（router 翻 403）。"""
    raw = make_personal_chat_id(PROJECT_ID, OTHER_USER_ID)
    with pytest.raises(ValueError, match="RBAC 違規"):
        normalize_for_query(raw, PROJECT_ID, USER_ID)


@pytest.mark.unit
def test_normalize_personal_of_other_project_raises() -> None:
    """raw 為別 project 的 personal → ValueError（router 翻 400）。"""
    other_project = uuid4()
    raw = make_personal_chat_id(other_project, USER_ID)
    with pytest.raises(ValueError, match="不屬於本專案"):
        normalize_for_query(raw, PROJECT_ID, USER_ID)


@pytest.mark.unit
def test_normalize_group_of_other_project_raises() -> None:
    """raw 為別 project 的 group 完整字串 → ValueError。"""
    other_project = uuid4()
    raw = make_group_chat_id(other_project)
    with pytest.raises(ValueError, match="不屬於本專案"):
        normalize_for_query(raw, PROJECT_ID, USER_ID)


@pytest.mark.unit
def test_normalize_unknown_format_raises() -> None:
    """raw 為未知格式 → ValueError（router 翻 400）。"""
    with pytest.raises(ValueError, match="未知 chat_id 格式"):
        normalize_for_query("foo:bar:baz", PROJECT_ID, USER_ID)


@pytest.mark.unit
def test_normalize_personal_missing_owner_raises() -> None:
    """raw 為 ``{pid}:personal:``（缺 owner）→ ValueError。"""
    raw = f"{PROJECT_ID}{PERSONAL_INFIX}"
    with pytest.raises(ValueError, match="缺 owner"):
        normalize_for_query(raw, PROJECT_ID, USER_ID)
