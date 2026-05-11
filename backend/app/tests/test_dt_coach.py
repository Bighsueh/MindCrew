"""DT 教練 endpoint 測試（Phase 20 Step 17.6：非同步重寫）。

涵蓋 specs/13-personal-chat.md §5.2、§7、§8.2：

1. 201 happy path：寫 user message + 排程 Coach 回覆 + Coach reply 落地
2. 401 未帶 JWT
3. 404 project 不存在
4. 422 schema 驗證錯誤（缺欄位、空字串、超長）
5. LLM 失敗 → 仍回 201；背景任務寫 system 錯誤訊息
6. P3 跨 session 持久化：訊息真的留在 DB
7. P4 RBAC（GET /messages 別人的 personal → 403）
8. P5 cross-user isolation（WS forwarder 過濾函式）
9. P6 Phase 16 isolation：``list_for_agents`` 不回 personal

DB-bound 測試標 `@pytest.mark.integration`，與 ``test_personal_isolation.py``
等其他 integration 測試一致。Helpers 抽到 ``_dt_coach_helpers.py``，本檔案
維持 < 500 行以符合 CLAUDE.md 行數規範。
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_id import make_personal_chat_id
from app.tests._dt_coach_helpers import (
    _FailingLLM,
    _FakeLLM,
    ask_coach,
    create_project,
    patch_llm,
    register_user,
    wait_for_messages,
)


# --------- tests -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_happy_path_persists_user_and_coach_reply(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """201 happy path：立即 ack + 背景寫 Coach reply + OpenCC 轉繁。"""
    teacher = await register_user(client, "coach_happy@test.com")
    project_id = await create_project(client, teacher["token"])

    fake = _FakeLLM(content="你好，让我们一起讨论这个项目的用户体验。")
    patch_llm(monkeypatch, fake)

    resp = await ask_coach(
        client,
        project_id,
        teacher["token"],
        content="我卡在 empathize 階段，怎麼辦？",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["coach_reply_scheduled"] is True

    personal_chat_id = make_personal_chat_id(project_id, teacher["user_id"])
    user_msg = body["user_message"]
    assert user_msg["content"] == "我卡在 empathize 階段，怎麼辦？"
    assert user_msg["chat_id"] == personal_chat_id
    assert user_msg["id"]

    rows = await wait_for_messages(
        db_session,
        project_id=project_id,
        chat_id=personal_chat_id,
        expected=2,
    )
    assert len(rows) == 2, f"預期 user + coach 兩筆，實得 {len(rows)} 筆"

    user_row, ai_row = rows[0], rows[1]
    assert user_row.sender_type == "human"
    assert user_row.sender_id == str(teacher["user_id"])
    assert user_row.chat_id == personal_chat_id

    assert ai_row.sender_type == "ai"
    assert ai_row.sender_id == "dt-coach"
    assert ai_row.sender_name == "DT 教練"
    assert ai_row.chat_id == personal_chat_id
    # OpenCC + 客製化 overrides → 簡中字應轉為繁中。
    assert "專案" in ai_row.content
    assert "使用者" in ai_row.content
    assert "项目" not in ai_row.content
    assert "用户" not in ai_row.content

    # LLM 被叫一次，且帶正確 max_tokens / temperature。
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["temperature"] == 0.7
    assert call["max_tokens"] == 512
    msgs = call["messages"]
    assert msgs[0]["role"] == "system"
    assert "DT 教練" in msgs[0]["content"]
    assert "Tester" in msgs[0]["content"]
    assert msgs[-1] == {
        "role": "user",
        "content": "我卡在 empathize 階段，怎麼辦？",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_without_jwt_returns_401(client: AsyncClient) -> None:
    """未帶 Authorization header → 401 或 403。"""
    resp = await client.post(
        f"/api/projects/{uuid4()}/dt-coach/ask",
        json={"content": "hi", "stage": "discover", "micro_phase": "empathize"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_project_not_found_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project_id 不存在於 DB → 404，且 LLM 不被呼叫。"""
    teacher = await register_user(client, "coach_404@test.com")
    fake = _FakeLLM(content="不應被呼叫")
    patch_llm(monkeypatch, fake)

    resp = await ask_coach(client, uuid4(), teacher["token"], content="hello")
    assert resp.status_code == 404
    # 給背景任務一點時間（即便會跑也應該不會跑——因 404 直接 return）。
    await asyncio.sleep(0.1)
    assert fake.calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_invalid_uuid_returns_422(client: AsyncClient) -> None:
    """project_id 不是合法 UUID → 422。"""
    teacher = await register_user(client, "coach_baduuid@test.com")
    resp = await client.post(
        "/api/projects/not-a-uuid/dt-coach/ask",
        json={"content": "hi", "stage": "discover", "micro_phase": "empathize"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_missing_content_returns_422(client: AsyncClient) -> None:
    """缺 content 欄位 → 422。"""
    teacher = await register_user(client, "coach_missing@test.com")
    project_id = await create_project(client, teacher["token"])
    resp = await client.post(
        f"/api/projects/{project_id}/dt-coach/ask",
        json={"stage": "discover", "micro_phase": "empathize"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_empty_content_returns_422(client: AsyncClient) -> None:
    """空字串 content（min_length=1）→ 422。"""
    teacher = await register_user(client, "coach_empty@test.com")
    project_id = await create_project(client, teacher["token"])
    resp = await ask_coach(client, project_id, teacher["token"], content="")
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_content_too_long_returns_422(client: AsyncClient) -> None:
    """content 超過 2000 字元 → 422。"""
    teacher = await register_user(client, "coach_long@test.com")
    project_id = await create_project(client, teacher["token"])
    resp = await ask_coach(
        client, project_id, teacher["token"], content="a" * 2001
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_llm_failure_writes_system_message_but_still_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 全 fail → 仍回 201；背景任務寫 sender_type='system' 錯誤訊息。

    spec §5.2：本 endpoint 不再回 503——LLM 失敗於背景處理。
    """
    teacher = await register_user(client, "coach_503@test.com")
    project_id = await create_project(client, teacher["token"])
    patch_llm(monkeypatch, _FailingLLM())

    resp = await ask_coach(client, project_id, teacher["token"], content="幫我")
    assert resp.status_code == 201, resp.text

    personal_chat_id = make_personal_chat_id(project_id, teacher["user_id"])
    rows = await wait_for_messages(
        db_session,
        project_id=project_id,
        chat_id=personal_chat_id,
        expected=2,
    )
    assert len(rows) == 2

    user_row, system_row = rows[0], rows[1]
    assert user_row.sender_type == "human"
    assert system_row.sender_type == "system"
    assert system_row.sender_id == "dt-coach"
    assert "暫時無法回應" in system_row.content


# --------- 新增測試（P3 / P4 / P5 / P6） ----------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_messages_persist_across_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P3：寫完訊息後重新 GET personal channel，仍可看到歷史（真的寫進 DB）。"""
    teacher = await register_user(client, "coach_persist@test.com")
    project_id = await create_project(client, teacher["token"])
    patch_llm(monkeypatch, _FakeLLM(content="收到，我們一起想想。"))

    resp = await ask_coach(
        client, project_id, teacher["token"], content="我有個想法"
    )
    assert resp.status_code == 201

    personal_chat_id = make_personal_chat_id(project_id, teacher["user_id"])
    await wait_for_messages(
        db_session,
        project_id=project_id,
        chat_id=personal_chat_id,
        expected=2,
    )

    get_resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": "personal"},
        headers={"Authorization": f"Bearer {teacher['token']}"},
    )
    assert get_resp.status_code == 200, get_resp.text
    bodies = {m["content"] for m in get_resp.json()["messages"]}
    assert "我有個想法" in bodies
    assert any("收到" in b for b in bodies)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rbac_other_user_personal_returns_403(
    client: AsyncClient,
) -> None:
    """P4：user A 嘗試 GET user B 的 personal chat_id → 403（spec §8.1）。"""
    user_a = await register_user(client, "coach_rbac_a@test.com", name="A")
    user_b = await register_user(client, "coach_rbac_b@test.com", name="B")
    project_id = await create_project(client, user_a["token"])

    other_personal = make_personal_chat_id(project_id, user_b["user_id"])
    resp = await client.get(
        f"/api/projects/{project_id}/messages",
        params={"chat_id": other_personal},
        headers={"Authorization": f"Bearer {user_a['token']}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cross_user_isolation_via_forwarder_filter() -> None:
    """P5：WS forwarder 純函數 RBAC filter 不會把 user A personal 送給 user B。

    這個測試**不依賴 DB**，只測 ``should_deliver_chat_event``——確保
    Coach reply 廣播時其他 user 的 forwarder 視角會丟棄該訊息。
    """
    from app.ws.delivery_filter import should_deliver_chat_event

    project_id = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    personal_a = make_personal_chat_id(project_id, user_a)

    assert should_deliver_chat_event(personal_a, str(user_a)) is True
    assert should_deliver_chat_event(personal_a, str(user_b)) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_phase16_agents_dont_see_personal_messages(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P6：寫 personal 後，``list_for_agents`` 不會包含 personal（spec §9.1）。"""
    teacher = await register_user(client, "coach_phase16@test.com")
    project_id = await create_project(client, teacher["token"])
    patch_llm(monkeypatch, _FakeLLM(content="OK。"))

    resp = await ask_coach(
        client,
        project_id,
        teacher["token"],
        content="個人聊天內容，agent 不該看到",
    )
    assert resp.status_code == 201

    personal_chat_id = make_personal_chat_id(project_id, teacher["user_id"])
    await wait_for_messages(
        db_session,
        project_id=project_id,
        chat_id=personal_chat_id,
        expected=2,
    )

    from app.chat.repository import MessageRepository

    repo = MessageRepository(db_session)
    rows = await repo.list_for_agents(project_id, limit=50)
    bodies = {m.content for m in rows}
    assert "個人聊天內容，agent 不該看到" not in bodies
    assert not any("OK" in b for b in bodies)
