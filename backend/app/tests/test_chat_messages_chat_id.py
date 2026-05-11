"""GET /api/projects/{id}/messages 帶 chat_id query 的 RBAC 整合測試。

涵蓋 specs/13-personal-chat.md §5.1、§8.1：

1. 不帶 chat_id → fallback group（向下相容）
2. chat_id=group → 只回 group 訊息
3. chat_id=personal → 只回自己的 personal 訊息
4. 完整 ``{pid}:group`` → 同 group
5. 完整 ``{pid}:personal:{self}`` → 同 personal
6. 完整 ``{pid}:personal:{other}`` → 403
7. 未知格式 → 400
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_id import make_group_chat_id, make_personal_chat_id
from app.db.models.message import Message


# ---------- 共用 helpers ----------


async def _register(client: AsyncClient, email: str, name: str = "User") -> dict:
    """註冊一個 user 並回 {token, user_id}。"""
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "pass", "display_name": name},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "token": data["access_token"],
        "user_id": UUID(data["user"]["id"]),
        "display_name": name,
    }


async def _create_project(client: AsyncClient, token: str) -> UUID:
    """以 teacher 身分建一個 project，回傳 project_id。"""
    from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD

    resp = await client.post(
        "/api/projects",
        json={
            "name": "Chat ID Test Project",
            "personas": VALID_PERSONAS_PAYLOAD,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


async def _insert_message(
    db_session: AsyncSession,
    *,
    project_id: UUID,
    chat_id: str | None,
    content: str,
    sender_type: str = "human",
    sender_id: str = "sender",
    sender_name: str = "Sender",
    stage: str = "lobby",
) -> Message:
    """直接 insert 一筆 message（繞過 WS / API）以便控制 chat_id。"""
    msg = Message(
        project_id=project_id,
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        stage=stage,
        chat_id=chat_id,
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


async def _seed_messages(
    db_session: AsyncSession,
    *,
    project_id: UUID,
    self_user_id: UUID,
    other_user_id: UUID,
) -> dict[str, list[str]]:
    """準備 fixture：group/self-personal/other-personal/legacy-null 各兩筆。

    Returns:
        dict 包含每類訊息的 content 清單（給 assert 用）。
    """
    group_chat_id = make_group_chat_id(project_id)
    self_personal = make_personal_chat_id(project_id, self_user_id)
    other_personal = make_personal_chat_id(project_id, other_user_id)

    contents = {
        "group": ["群組訊息 1", "群組訊息 2"],
        "legacy_null": ["舊版未 backfill 訊息"],
        "self_personal": ["自己的 personal 1", "自己的 personal 2"],
        "other_personal": ["別人的 personal 1"],
    }

    for c in contents["group"]:
        await _insert_message(
            db_session, project_id=project_id, chat_id=group_chat_id, content=c
        )
    for c in contents["legacy_null"]:
        await _insert_message(
            db_session, project_id=project_id, chat_id=None, content=c
        )
    for c in contents["self_personal"]:
        await _insert_message(
            db_session, project_id=project_id, chat_id=self_personal, content=c
        )
    for c in contents["other_personal"]:
        await _insert_message(
            db_session, project_id=project_id, chat_id=other_personal, content=c
        )

    return contents


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_get_messages_without_chat_id_returns_group_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """既有 client 不帶 chat_id 仍只看到 group 訊息（含 legacy NULL），不含 personal。"""
    teacher = await _register(client, "chatid_default@test.com")
    other = await _register(client, "chatid_default_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    msgs = resp.json()["messages"]
    bodies = {m["content"] for m in msgs}

    # 應包含 group + legacy NULL
    assert set(contents["group"]).issubset(bodies)
    assert set(contents["legacy_null"]).issubset(bodies)
    # 不該包含任何 personal
    assert not set(contents["self_personal"]) & bodies
    assert not set(contents["other_personal"]) & bodies


@pytest.mark.asyncio
async def test_get_messages_with_chat_id_group_returns_group_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``chat_id=group`` 別名行為等同預設。"""
    teacher = await _register(client, "chatid_group_alias@test.com")
    other = await _register(client, "chatid_group_alias_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": "group"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    bodies = {m["content"] for m in resp.json()["messages"]}
    assert set(contents["group"]).issubset(bodies)
    assert not set(contents["self_personal"]) & bodies
    assert not set(contents["other_personal"]) & bodies


@pytest.mark.asyncio
async def test_get_messages_with_chat_id_personal_returns_self_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``chat_id=personal`` 別名只回自己的 personal，不含別人、不含 group。"""
    teacher = await _register(client, "chatid_personal@test.com")
    other = await _register(client, "chatid_personal_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": "personal"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    bodies = {m["content"] for m in resp.json()["messages"]}

    assert bodies == set(contents["self_personal"])
    # 同時驗證 response 的 chat_id 欄位有帶回 personal 字串
    expected_chat_id = make_personal_chat_id(project_id, teacher["user_id"])
    assert all(m["chat_id"] == expected_chat_id for m in resp.json()["messages"])


@pytest.mark.asyncio
async def test_get_messages_full_group_chat_id_same_as_group(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """傳 ``{pid}:group`` 完整字串等同 group。"""
    teacher = await _register(client, "chatid_full_group@test.com")
    other = await _register(client, "chatid_full_group_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": make_group_chat_id(project_id)},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    bodies = {m["content"] for m in resp.json()["messages"]}
    assert set(contents["group"]).issubset(bodies)
    assert not set(contents["self_personal"]) & bodies


@pytest.mark.asyncio
async def test_get_messages_full_self_personal_returns_self_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """傳完整 ``{pid}:personal:{self}`` 等同 personal 別名。"""
    teacher = await _register(client, "chatid_full_self@test.com")
    other = await _register(client, "chatid_full_self_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    self_personal = make_personal_chat_id(project_id, teacher["user_id"])
    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": self_personal},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    bodies = {m["content"] for m in resp.json()["messages"]}
    assert bodies == set(contents["self_personal"])


@pytest.mark.asyncio
async def test_get_messages_other_user_personal_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """指向別人的 personal chat_id → 403 Forbidden（spec §8.1）。"""
    teacher = await _register(client, "chatid_403@test.com")
    other = await _register(client, "chatid_403_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    await _seed_messages(
        db_session,
        project_id=project_id,
        self_user_id=teacher["user_id"],
        other_user_id=other["user_id"],
    )

    other_personal = make_personal_chat_id(project_id, other["user_id"])
    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": other_personal},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 403, resp.text
    assert "RBAC" in resp.json()["detail"] or "personal" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_messages_unknown_chat_id_format_returns_400(
    client: AsyncClient,
) -> None:
    """未知格式（非 group / 非 personal）→ 400 Bad Request。"""
    teacher = await _register(client, "chatid_400@test.com")
    project_id = await _create_project(client, teacher["token"])

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": "foo:bar:baz"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_get_messages_other_project_chat_id_returns_400(
    client: AsyncClient,
) -> None:
    """傳別 project 的 group/personal 完整字串 → 400（不屬於本專案）。"""
    teacher = await _register(client, "chatid_400_otherproj@test.com")
    project_id = await _create_project(client, teacher["token"])

    # 用 hardcoded 假 UUID 假裝別 project
    fake_project = UUID("00000000-0000-0000-0000-0000000000ff")
    other_proj_chat_id = make_group_chat_id(fake_project)

    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": other_proj_chat_id},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 400, resp.text
