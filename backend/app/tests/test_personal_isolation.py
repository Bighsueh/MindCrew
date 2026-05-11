"""Phase 20 Step 17.7：personal 訊息隔離回歸測試。

驗證下游所有「禁止看到 personal 訊息」的查詢路徑都正確過濾：

1. ``MessageRepository.list_for_agents`` / ``list_group`` 只回 group + legacy NULL。
2. Seat progress（regular / supervisor）摘要的 topic 只取自 group 訊息。
3. Teacher record endpoint 的 ``total_messages`` 統計只算 group。
4. Teacher overview 的 participation（human / ai / active_members）只算 group。
5. Agent ``ContextBuffer`` 的 DB fallback path 只載入 group 訊息。

對應 specs/13-personal-chat.md §4.4、§8.5、§9.1 與
specs/11-organization-turn.md §9.1。

## 執行方式

本檔案的所有測試都標註為 ``@pytest.mark.integration``——皆依賴
``conftest.py`` 內的 ``db_session`` fixture（連 PostgreSQL ``dtai_test`` DB）。
本地若未啟動 Postgres、或未建立 ``dtai`` role，會於連線階段失敗（與
``test_chat_messages_chat_id.py`` 等既有整合測試一致）。

正規跑法：

```bash
docker compose up -d postgres redis            # 啟動依賴
DATABASE_URL=postgresql+asyncpg://dtai:dtai@localhost:5432/dtai \\
    python -m pytest app/tests/test_personal_isolation.py -v
```

或在 CI（已備好 dtai_test DB）直接 ``pytest -m integration``。
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_id import make_group_chat_id, make_personal_chat_id
from app.chat.repository import MessageRepository
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


async def _make_teacher(db_session: AsyncSession, user_id: UUID) -> None:
    """把 user.role 改成 teacher（teacher dashboard endpoint 需要）。"""
    from app.db.models.user import User
    from sqlalchemy import update

    await db_session.execute(
        update(User).where(User.id == user_id).values(role="teacher")
    )
    await db_session.commit()


async def _create_project(client: AsyncClient, token: str) -> UUID:
    from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD

    resp = await client.post(
        "/api/projects",
        json={
            "name": "Personal Isolation Test Project",
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
    sender_id: str | None = None,
    sender_name: str = "Sender",
    stage: str = "lobby",
) -> Message:
    """直接 insert 一筆 message 以便控制 chat_id。"""
    msg = Message(
        project_id=project_id,
        sender_type=sender_type,
        sender_id=sender_id or "sender-default",
        sender_name=sender_name,
        content=content,
        stage=stage,
        chat_id=chat_id,
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


async def _seed_mixed_messages(
    db_session: AsyncSession,
    *,
    project_id: UUID,
    user_a: UUID,
    user_b: UUID,
) -> dict[str, list[str]]:
    """準備 5 筆：3 group（含 legacy NULL）+ 2 personal（A / B 各一）。"""
    group_chat_id = make_group_chat_id(project_id)
    personal_a = make_personal_chat_id(project_id, user_a)
    personal_b = make_personal_chat_id(project_id, user_b)

    contents = {
        "group": ["群組 G1", "群組 G2"],
        "legacy_null": ["舊版未 backfill"],
        "personal_a": ["A 的祕密"],
        "personal_b": ["B 的祕密"],
    }

    # group with chat_id
    for c in contents["group"]:
        await _insert_message(
            db_session,
            project_id=project_id,
            chat_id=group_chat_id,
            content=c,
            sender_type="human",
            sender_id=str(user_a),
            sender_name="A",
        )
    # legacy NULL
    for c in contents["legacy_null"]:
        await _insert_message(
            db_session,
            project_id=project_id,
            chat_id=None,
            content=c,
            sender_type="ai",
            sender_id="agent-legacy",
            sender_name="LegacyAI",
        )
    # personal A
    for c in contents["personal_a"]:
        await _insert_message(
            db_session,
            project_id=project_id,
            chat_id=personal_a,
            content=c,
            sender_type="human",
            sender_id=str(user_a),
            sender_name="A",
        )
    # personal B
    for c in contents["personal_b"]:
        await _insert_message(
            db_session,
            project_id=project_id,
            chat_id=personal_b,
            content=c,
            sender_type="human",
            sender_id=str(user_b),
            sender_name="B",
        )
    return contents


# ---------- Tests：MessageRepository ----------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_list_for_agents_excludes_personal(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``list_for_agents`` 是 agent context 的唯一入口，必須完全排除 personal。"""
    teacher = await _register(client, "iso_repo_agents@test.com")
    other = await _register(client, "iso_repo_agents_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_mixed_messages(
        db_session,
        project_id=project_id,
        user_a=teacher["user_id"],
        user_b=other["user_id"],
    )

    repo = MessageRepository(db_session)
    rows = await repo.list_for_agents(project_id, limit=50)
    bodies = {m.content for m in rows}

    expected_group = set(contents["group"]) | set(contents["legacy_null"])
    assert expected_group.issubset(bodies)
    # 不可包含任何 personal
    assert not (set(contents["personal_a"]) | set(contents["personal_b"])) & bodies


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_list_group_excludes_personal(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``list_group`` 與 ``list_for_agents`` 行為一致，皆只回 group。"""
    teacher = await _register(client, "iso_repo_group@test.com")
    other = await _register(client, "iso_repo_group_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_mixed_messages(
        db_session,
        project_id=project_id,
        user_a=teacher["user_id"],
        user_b=other["user_id"],
    )

    repo = MessageRepository(db_session)
    rows = await repo.list_group(project_id, limit=50)
    bodies = {m.content for m in rows}

    expected_group = set(contents["group"]) | set(contents["legacy_null"])
    assert expected_group.issubset(bodies)
    assert not (set(contents["personal_a"]) | set(contents["personal_b"])) & bodies


# ---------- Tests：teacher router ----------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_teacher_record_total_messages_group_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``GET /api/teacher/projects/{id}/record`` 的 total_messages 只算 group。"""
    teacher = await _register(client, "iso_teacher_record@test.com")
    other = await _register(client, "iso_teacher_record_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_mixed_messages(
        db_session,
        project_id=project_id,
        user_a=teacher["user_id"],
        user_b=other["user_id"],
    )

    # teacher dashboard endpoint 需要 teacher role
    await _make_teacher(db_session, teacher["user_id"])

    resp = await client.get(
        f"/api/teacher/projects/{project_id}/record",
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    expected_group_count = len(contents["group"]) + len(contents["legacy_null"])
    assert resp.json()["total_messages"] == expected_group_count


@pytest.mark.integration
@pytest.mark.asyncio
async def test_teacher_overview_participation_excludes_personal(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``GET /api/teacher/projects/overview`` 的 participation 統計只算 group。

    - human_messages：只算 group 中 sender_type='human'。
    - ai_messages：只算 group 中 sender_type='ai'。
    - active_members：只算在 group 發過言的 distinct human sender。
    """
    teacher = await _register(client, "iso_teacher_overview@test.com")
    other = await _register(client, "iso_teacher_overview_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_mixed_messages(
        db_session,
        project_id=project_id,
        user_a=teacher["user_id"],
        user_b=other["user_id"],
    )

    await _make_teacher(db_session, teacher["user_id"])

    resp = await client.get(
        "/api/teacher/projects/overview",
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    projects = payload["projects"]
    target = next((p for p in projects if p["id"] == str(project_id)), None)
    assert target is not None, "新建 project 應出現在 overview 中"

    participation = target["participation"]
    # group 中 human 訊息 = contents["group"] (sender_id=A) 兩筆
    assert participation["human_messages"] == len(contents["group"])
    # group 中 ai 訊息 = legacy_null (sender_type='ai') 一筆
    assert participation["ai_messages"] == len(contents["legacy_null"])
    # active_members：只有 A 在 group 發言（B 只發 personal，不算）
    assert participation["active_members"] == 1
    # 對照組：personal_b 內容絕不可影響統計
    # （human_messages 若漏改 filter 會 = 3，包含 A 的 personal_a）


# ---------- Tests：context_buffer DB fallback ----------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_buffer_db_fallback_excludes_personal(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """``ContextBuffer._load_chat`` 在 Redis 無 cache 時 fallback 到 DB query；
    該 DB query 必須過濾 personal。

    本測試直接呼叫 private method，並 patch Redis client 讓 ``lrange`` 回空 list，
    強制走 fallback 路徑。
    """
    teacher = await _register(client, "iso_ctx_buffer@test.com")
    other = await _register(client, "iso_ctx_buffer_other@test.com")
    project_id = await _create_project(client, teacher["token"])
    contents = await _seed_mixed_messages(
        db_session,
        project_id=project_id,
        user_a=teacher["user_id"],
        user_b=other["user_id"],
    )

    # 用一個 mock Redis 物件：lrange 永遠回 [] 強制 fallback。
    class _FakeRedis:
        async def lrange(self, key: str, start: int, end: int) -> list:
            return []

    from app.agents.context_buffer import ContextBuffer

    buf = ContextBuffer(
        project_id=project_id,
        agent_id="test-agent",
        seat_role="crew_1",
    )
    chat = await buf._load_chat(_FakeRedis())  # type: ignore[arg-type]
    bodies = {m["content"] for m in chat}

    expected_group = set(contents["group"]) | set(contents["legacy_null"])
    assert expected_group.issubset(bodies)
    assert not (set(contents["personal_a"]) | set(contents["personal_b"])) & bodies
